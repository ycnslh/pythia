// Runtime configuration. In production the backend injects `window.__PYTHIA__`
// into index.html (so one image serves any language / threshold without a rebuild).
// Under the Vite dev server nothing is injected: fall back to VITE_LANGUAGE / defaults.
const injected = (typeof window !== "undefined" && window.__PYTHIA__) || {};

export const config = {
  language: injected.language || import.meta.env?.VITE_LANGUAGE || "en",
  // Events below this criticality stay in /feed and never reach /display
  displayThreshold: injected.displayThreshold ?? 4,
  // Pending queue bounds for /display
  queueMax: injected.queueMax ?? 10,
  maxAgeS: injected.maxAgeS ?? 600,
};
