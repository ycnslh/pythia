import { describe, it, expect } from "vitest";
import { isDisplayable, pruneExpired, enqueue, dequeue } from "src/lib/displayQueue";

const ev = (title, criticality) => ({ title, criticality });
const opts = { max: 3, maxAgeMs: 10_000 };

describe("isDisplayable", () => {
  it("applies the threshold inclusively", () => {
    expect(isDisplayable(ev("a", 4), 4)).toBe(true);
    expect(isDisplayable(ev("a", 3.9), 4)).toBe(false);
  });
  it("rejects malformed events", () => {
    expect(isDisplayable(null, 4)).toBe(false);
    expect(isDisplayable({ criticality: "9" }, 4)).toBe(false);
  });
});

describe("enqueue", () => {
  it("orders by criticality, highest first", () => {
    let q = [];
    q = enqueue(q, ev("low", 4), 0, opts);
    q = enqueue(q, ev("high", 9), 1, opts);
    q = enqueue(q, ev("mid", 6), 2, opts);
    expect(q.map((e) => e.event.title)).toEqual(["high", "mid", "low"]);
  });

  it("keeps arrival order among equal criticality", () => {
    let q = [];
    q = enqueue(q, ev("first", 5), 0, opts);
    q = enqueue(q, ev("second", 5), 1, opts);
    expect(q.map((e) => e.event.title)).toEqual(["first", "second"]);
  });

  it("evicts the least critical entries when over capacity", () => {
    let q = [];
    for (const [t, c] of [["a", 5], ["b", 4], ["c", 6], ["d", 9]]) {
      q = enqueue(q, ev(t, c), 0, opts);
    }
    expect(q.map((e) => e.event.title)).toEqual(["d", "c", "a"]); // "b" evicted
  });

  it("a flood of minor events cannot push out a major one", () => {
    let q = enqueue([], ev("major", 9), 0, opts);
    for (let i = 0; i < 20; i++) q = enqueue(q, ev(`minor${i}`, 4), i, opts);
    expect(q[0].event.title).toBe("major");
    expect(q).toHaveLength(3);
  });

  it("drops expired entries on the way", () => {
    let q = enqueue([], ev("old", 9), 0, opts);
    q = enqueue(q, ev("new", 4), 20_000, opts);
    expect(q.map((e) => e.event.title)).toEqual(["new"]);
  });
});

describe("dequeue", () => {
  it("returns the most critical fresh event and the remainder", () => {
    let q = enqueue([], ev("a", 5), 0, opts);
    q = enqueue(q, ev("b", 8), 1, opts);
    const { next, rest } = dequeue(q, 2, opts.maxAgeMs);
    expect(next.title).toBe("b");
    expect(rest).toHaveLength(1);
  });

  it("skips events that expired while waiting", () => {
    const q = enqueue([], ev("stale", 9), 0, opts);
    const { next, rest } = dequeue(q, 60_000, opts.maxAgeMs);
    expect(next).toBeNull();
    expect(rest).toEqual([]);
  });
});

describe("pruneExpired", () => {
  it("keeps entries exactly at the age limit", () => {
    const q = [{ event: ev("x", 5), receivedAt: 0 }];
    expect(pruneExpired(q, 10_000, 10_000)).toHaveLength(1);
    expect(pruneExpired(q, 10_001, 10_000)).toHaveLength(0);
  });
});
