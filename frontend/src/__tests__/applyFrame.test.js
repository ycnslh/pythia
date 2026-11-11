import { describe, it, expect } from "vitest";
import { applyFrame } from "src/hooks/useWebSocket";

const ev = (title) => ({ title, criticality: 5, category: "ELEVATED SCRUTINY", timestamp: "t" });
const empty = { lastEvent: null, eventHistory: [] };

describe("applyFrame", () => {
  it("history fills the list newest first without touching lastEvent", () => {
    const next = applyFrame(empty, { type: "history", events: [ev("old"), ev("new")] });
    expect(next.eventHistory.map((e) => e.title)).toEqual(["new", "old"]);
    expect(next.lastEvent).toBeNull(); // /display must not replay history
  });

  it("history replaces the list, so a reconnect does not duplicate events", () => {
    const frame = { type: "history", events: [ev("a"), ev("b")] };
    const once = applyFrame(empty, frame);
    const twice = applyFrame(once, frame);
    expect(twice.eventHistory).toHaveLength(2);
  });

  it("a live event sets lastEvent and is prepended", () => {
    const base = applyFrame(empty, { type: "history", events: [ev("old")] });
    const next = applyFrame(base, { type: "event", event: ev("live") });
    expect(next.lastEvent.title).toBe("live");
    expect(next.eventHistory.map((e) => e.title)).toEqual(["live", "old"]);
  });

  it("caps the list at 100 entries", () => {
    const events = Array.from({ length: 150 }, (_, i) => ev(`e${i}`));
    const next = applyFrame(empty, { type: "history", events });
    expect(next.eventHistory).toHaveLength(100);
    expect(next.eventHistory[0].title).toBe("e149");
  });

  it("ignores unknown or malformed frames", () => {
    expect(applyFrame(empty, { type: "nope" })).toBe(empty);
    expect(applyFrame(empty, null)).toBe(empty);
  });
});
