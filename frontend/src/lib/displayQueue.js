// Pending-event queue of the ambient display. Pure functions so the policy is
// testable: highest criticality first, bounded, and stale events are dropped.
//
// An entry is { event, receivedAt } (receivedAt in ms).

/** True if the event is important enough for the ambient display. */
export function isDisplayable(event, threshold) {
  return Number.isFinite(event?.criticality) && event.criticality >= threshold;
}

/** Drop entries older than `maxAgeMs`. */
export function pruneExpired(pending, now, maxAgeMs) {
  return pending.filter((entry) => now - entry.receivedAt <= maxAgeMs);
}

/**
 * Add an event, then re-apply the policy. When over capacity the LEAST critical
 * entries are evicted (oldest first among equals), so a flood of minor news
 * can never push out a major event.
 */
export function enqueue(pending, event, now, { max, maxAgeMs }) {
  const next = pruneExpired([...pending, { event, receivedAt: now }], now, maxAgeMs);
  // Stable sort: equal criticality keeps arrival order (oldest first)
  next.sort((a, b) => b.event.criticality - a.event.criticality);
  return next.slice(0, Math.max(1, max));
}

/** Take the next entry to display (most critical, still fresh). */
export function dequeue(pending, now, maxAgeMs) {
  const fresh = pruneExpired(pending, now, maxAgeMs);
  const [first, ...rest] = fresh;
  return { next: first ? first.event : null, rest };
}
