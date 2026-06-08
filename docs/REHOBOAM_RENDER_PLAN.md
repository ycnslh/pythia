# Incite "Rehoboam" Sphere — Implementation Plan

> Goal: replace PYTHIA's flat 2D canvas disk with a charcoal **geodesic sphere**
> inspired by the Incite Inc. landing page, while keeping the existing event
> pipeline, state machine, HUD, and monochrome charter. This document is written
> to be handed directly to Claude Code as the implementation brief.

---

## 1. Background & the decisive finding

The Incite hero sphere was reverse-engineered from the archived site
(`web.archive.org/web/20210325012708/https://inciteinc.com/`), its `main.js`,
and its `style.css`.

**It is a pre-rendered art asset, not a real-time generative animation.** `main.js`
toggles `<video>` layers (`.particles-video-full`, `.cu-normal`, `.cu-black`,
`.cu-zoom`) via GSAP opacity tweens and gates the intro on
`video.readyState === 4`. `style.css` backs the field with a rendered frame
`img/Dispersed_v01a0090_Black.png` on a `#f6f5f7` background. The `+` marks are
DOM elements (`.plus-0/1/4/5`) absolutely positioned around the sphere and
blinked in sequence by a `TimelineLite`. particles.js / GSAP / jQuery are loaded
but do **not** draw the sphere.

**Consequence for PYTHIA.** There is no algorithm to port for the exact look —
it is baked. A video cannot spike at an arbitrary `emissionAngle` with intensity
`criticality / 10` per live event, which is the entire point of PYTHIA. So a
pixel-exact match and reactivity are mutually exclusive. **PYTHIA takes the
procedural path:** a Canvas 2D sphere that *evokes* the Incite look and deforms
per event. Not identical, but reactive — and it stays in PYTHIA's existing
Canvas 2D stack with no new dependency.

---

## 2. Constraints (from `CLAUDE.md`) — must hold

- **No new heavy dependency.** Stay in Canvas 2D + hand-rolled
  `requestAnimationFrame`. No Three.js, no GSAP. The 3D math here is ~30 lines.
- **Component contract unchanged.** `PythiaCircle` keeps the exact same props so
  `Display.jsx` needs zero edits: `state`, `criticality`, `queueSize`,
  `emissionAngle`, `onReturnComplete`.
- **Sphere radius unchanged.** Keep canvas size `min(w,h) * 0.6` and
  `baseR = canvas.width * 0.38`. `HUDOverlay.jsx` independently computes
  `circleR = min(w,h) * 0.6 * 0.38` and centers on the viewport; the leader
  lines only stay anchored if the sphere keeps that exact radius and center.
- **`/display` stays non-interactive.** No drag/click/hover. Autonomous slow
  rotation only (Incite's drag-to-spin is dropped).
- **All animation logic lives in `PythiaCircle`.** No animation state leaks into
  `Display.jsx`.
- **Monochrome, opacity-only.** No hues. Criticality differentiated by intensity.

---

## 3. Values extracted from Incite `style.css`

- Light background `#f6f5f7`; dark variant `#080808`.
- Muted greys: `#9B9B9B`, `#979797`, `#6A6A6A`, `#BEBEBE`.
- Technical-label font `Source Code Pro` (mono) — a closer match than PYTHIA's
  current `Courier New`. Optional swap (see §9).
- `+` markers: circular plus glyph, inverting to white-glyph-on-black when
  active, blinked in sequence.

---

## 4. Color decision (pick one before building)

- **Option A — keep white-on-black (recommended).** PYTHIA stays the
  photographic negative of Incite: white charcoal on `#000`. Smallest change
  (no `index.css` edits), coherent with `/feed` and the HUD, still reads as
  Rehoboam. Charcoal density math just inverts (bright at rim instead of dark).
- **Option B — invert to dark-on-white to match Incite.** Set `--color-bg:
  #f6f5f7` and `--color-primary: #080808` in `index.css`, then re-check `/feed`,
  `HUDOverlay`, and the criticality bands (all alpha-based, so they invert
  cleanly but need a contrast pass). Bigger blast radius.

The rest of this plan assumes **Option A**; Option B only changes which end of
the alpha ramp is "dense".

---

## 5. Geometry & math (the core of the rewrite)

All of this lives inside the new `PythiaCircle.jsx`. Unit sphere, built once;
rotated, displaced, and projected per frame.

### 5.1 Point set — Fibonacci sphere (build once)

Even, organic spacing (the particles.js web feel) without a rigid lattice.

```js
const GOLDEN = Math.PI * (3 - Math.sqrt(5));
function fibSphere(n) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2;          // 1 → -1
    const r = Math.sqrt(1 - y * y);
    const th = i * GOLDEN;
    pts.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r }); // unit vector
  }
  return pts;
}
```

Suggested counts: `N_NODE ≈ 120` (mesh vertices), plus a denser
`N_DUST ≈ 700` separate cloud for the charcoal shading.

### 5.2 Edges by proximity (build once)

Topology is fixed (rotation/displacement don't change which nodes are
neighbours), so compute the edge list a single time from 3D distances on the
unit sphere:

```js
function buildEdges(nodes, maxDist = 0.55) {
  const edges = [];
  for (let i = 0; i < nodes.length; i++)
    for (let j = i + 1; j < nodes.length; j++) {
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dz = nodes[i].z - nodes[j].z;
      if (dx*dx + dy*dy + dz*dz < maxDist*maxDist) edges.push([i, j]);
    }
  return edges;
}
```

Tune `maxDist` for web density (more = busier mesh).

### 5.3 Rotation (per frame)

Slow spin around Y, fixed tilt around X so we see the pole structure:

```js
const TILT = 0.45;                       // radians, constant
const spin = totalT * SPIN_SPEED;        // SPIN_SPEED ≈ 0.07 rad/s (idle)
function rotateY(p, a){ const c=Math.cos(a),s=Math.sin(a);
  return { x:p.x*c + p.z*s, y:p.y, z:-p.x*s + p.z*c }; }
function rotateX(p, a){ const c=Math.cos(a),s=Math.sin(a);
  return { x:p.x, y:p.y*c - p.z*s, z:p.y*s + p.z*c }; }
// per node: rotateX(rotateY(displaced, spin), TILT)
```

### 5.4 Perspective projection

Camera on +z at distance `D`; `depth = z` after rotation (`+` = toward camera).

```js
const D = 3.2;
const factor = D / (D - zr);             // zr = rotated z
const sx = cx + xr * factor * baseR;
const sy = cy + yr * factor * baseR;
// front-ness for opacity: f = (zr + 1) / 2  ∈ [0,1]
```

`cx, cy` = canvas center; `baseR = canvas.width * 0.38` (unchanged).

### 5.5 Edge & node rendering (depth-faded "graphite")

```js
// edge opacity: front edges darker, back edges faint
const fAvg = ((zrA + zrB) / 2 + 1) / 2;          // 0..1
const alpha = EDGE_MIN + (EDGE_MAX - EDGE_MIN) * fAvg;   // e.g. 0.06 .. 0.5
// draw line (sxA,syA)->(sxB,syB) with rgba(fg, alpha)
// add tiny per-endpoint jitter (±0.5px, persistent seed) for the hand-drawn wobble
```

Nodes: small dots at projected positions, same depth fade. Keep them subtle —
the mesh lines carry the form.

### 5.6 Charcoal shading layer

Reuse the dust technique already in the current `PythiaCircle` (the frost/spike
clouds). Project the dense `N_DUST` Fibonacci cloud and modulate alpha by the
**silhouette factor** so the rim reads as packed charcoal and the center stays
bright:

```js
const sil = Math.sqrt(xr*xr + yr*yr);    // 0 center → ~1 rim (pre-projection)
// Option A (white on black): brighter at rim
const a = DUST_ALPHA * Math.pow(sil, 1.6) * frontFade;
```

Add the existing persistent rim "frost halo" for the frayed edge.

### 5.7 Event displacement (port the current wave math to 3D)

The existing `makeEmission` / `broadWaveAt` / `daggerWaveAt` logic transfers
directly — replace "push 2D rim point outward by radius" with "push sphere node
outward along its normal (= its unit position)".

```js
// emissionDir: unit vector for the event, derived from emissionAngle (see §5.8)
// per node v (unit), per frame:
const cosA = v.x*ed.x + v.y*ed.y + v.z*ed.z;
const ang  = Math.acos(clamp(cosA, -1, 1));        // great-circle angle 0..PI
const env  = Math.exp(-(ang*ang) / (2*sigma*sigma)); // sigma from criticality
let push = env * waveAmp * strength * AMP;          // broad fluffy base
push += daggerPush(v, ed, daggers, waveAmp);        // 1–3 sharp daggers
const displaced = { x: v.x*(1+push), y: v.y*(1+push), z: v.z*(1+push) };
```

`daggerPush` mirrors `daggerWaveAt`: a few fixed sub-directions near `ed` with a
much smaller `sigma` and a `reachMul`. `sigma`, `strength`, dagger count come
from `makeEmission(criticality, …)` exactly as today.

`waveAmp` per state is copied verbatim from the current component:
- `analyzing`: `min(stateT / 4.0, 1) * 0.45`
- `divergence`: `1.0`
- `returning`: `pow(1 - min(stateT/RETURN_DUR,1), 1.8)`, `RETURN_DUR = 3.5`
- `idle`: 0, plus a tiny global shimmer (low-amplitude normal jitter).

`queueSize` → a softer counter-bulge at `−ed` (opposite side), like the current
`makeCounter`, amplitude `min(queue/3,1)*0.45*waveAmp`.

### 5.8 Keeping the spike aligned with the HUD leader (important)

`HUDOverlay` anchors its hexagon + leader line at a **fixed screen angle**
(`anchorAngle === emissionAngle`) on the ring. The sphere rotates, so a bulge
locked to spinning material would drift away from that screen anchor.

**Recommended fix:** ease the spin toward ~0 during `analyzing` + `divergence`,
and restore it during `returning`/`idle`. Compute `emissionDir` once when the
event starts by inverse-rotating the screen target so the bulge sits exactly
under the HUD anchor:

```js
// screen target on the front hemisphere at angle emissionAngle:
const target = { x: Math.cos(emissionAngle), y: Math.sin(emissionAngle), z: 0.6 };
// normalize, then inverse-rotate by the current (frozen) spin+tilt to get ed in model space
```

With the spin eased to near-zero during the event, the material spike grows and
stays put under the leader line; rotation resumes afterward. (Alternative:
screen-locked hotspot that bulges whichever material crosses the anchor — looks
less "attached"; not recommended.)

---

## 6. State machine mapping (timings from `Display.jsx`)

`Display.jsx` drives: `analyzing` for 2000 ms → `divergence` for
`displayDuration(criticality) = (8 + (crit-1)*3) * 1000` ms → `returning` →
`onReturnComplete` (which advances the queue). The new component must honour the
same `onReturnComplete` contract.

| State | Sphere behavior |
|---|---|
| `idle` | Slow spin (`SPIN_SPEED`), faint global shimmer, frost rim. |
| `analyzing` | Spin eases toward 0; localized bulge at `emissionDir` ramps over ~4 s; dust intensifies locally. |
| `divergence` | Full amplitude; 1–3 daggers spike outward at `emissionDir`, intensity `criticality/10`. |
| `returning` | Bulge decays `pow(1-prog,1.8)` over `RETURN_DUR=3.5 s`; spin restores. Fire `onReturnComplete` **once** when `stateT >= RETURN_DUR` (reuse the `returnNotifiedRef` guard from the current code). |

Emission objects are (re)built in the `useEffect([state, criticality,
emissionAngle])`, mirroring the current structure (build on `analyzing`, keep on
`divergence`, clear on `idle`).

---

## 7. HUD crosshair marks (`HUDOverlay.jsx`)

Add Incite's blinking `+` registration marks as a decorative layer. These are
separate from the existing event hexagon/leader (which stays as-is).

- 3 marks at fixed screen offsets around the circle (mirror Incite's percentage
  placement, e.g. just outside `circleR` at ~30°, ~150°, ~270°).
- Render as small monochrome `+` (text `+` in the mono font, or a tiny SVG).
- Blink in sequence: a CSS `@keyframes` opacity cycle with staggered
  `animation-delay`, or a small `setInterval` toggling an `active` class. Keep
  amplitude subtle (e.g. opacity 0.25 ↔ 0.6) so `/display` stays calm.
- Pure CSS opacity, `pointer-events: none` (the HUD root already is).

No event data, no interactivity — ambiance only.

---

## 8. File-by-file changes

- `frontend/src/components/PythiaCircle.jsx` — **full rewrite** per §5–§6. Keep
  props, canvas size `min(w,h)*0.6`, `baseR = width*0.38`, the
  `useEffect([state,criticality,emissionAngle])` emission setup, the rAF loop
  with refs mirroring props, and the `returnNotifiedRef` → `onReturnComplete`
  guard.
- `frontend/src/components/PythiaCircle.module.css` — unchanged (canvas stays a
  centered block; size set in JS).
- `frontend/src/components/HUDOverlay.jsx` — add the crosshair marks layer (§7).
- `frontend/src/components/HUDOverlay.module.css` — crosshair styles + blink
  keyframes.
- `frontend/src/index.css` — only if **Option B** (color inversion) or the font
  swap (§9) is chosen.
- `frontend/index.html` — only if adding the Source Code Pro font (§9).

`Display.jsx`, `useWebSocket.js`, `App.jsx`, `Feed.jsx`, i18n, and the entire
backend are **untouched**.

---

## 9. Optional: font swap to Source Code Pro

Closer to the Incite technical label feel. If desired: add the Google Fonts link
in `index.html`, then set `--font-mono: "Source Code Pro", "Courier New",
monospace;` in `index.css`. Affects HUD + Feed globally. Optional and isolated —
do it last, or skip.

---

## 10. Build order (each milestone independently verifiable)

1. **Static mesh.** Replace the canvas with the Fibonacci sphere + proximity
   edges + depth fade + slow rotation. Ignore props for now. Verify: it reads as
   a see-through geodesic sphere, and the HUD hexagon/leader still anchor on the
   ring (radius/center unchanged).
2. **Charcoal + center.** Add the dust shading layer and frost rim; tune the
   bright center and frayed top. Lock in Option A vs B.
3. **Idle + analyzing.** Port the displacement math; wire the idle shimmer and
   the `analyzing` bulge with spin easing.
4. **Divergence + returning.** Daggers at full amplitude; decay envelope; fire
   `onReturnComplete` once. Verify a full cycle from a fake event and that the
   spike sits under the HUD leader.
5. **Queue.** Wire `queueSize` counter-bulge.
6. **Crosshairs + polish.** Add the blinking `+` marks; tune density, opacity,
   dagger sharpness, spin speed against a real event stream.

---

## 11. Verification

- **Drive the states.** Temporarily feed fake events (or a dev keypress) to walk
  `idle → analyzing → divergence → returning → idle` and confirm
  `onReturnComplete` advances the queue (no stuck states, no double-fire).
- **HUD coherence.** The spike must appear under the hexagon/leader for several
  `emissionAngle` values across all quadrants.
- **Radius/anchor regression.** Confirm `baseR` and center are unchanged so HUD
  placement still matches (compare against `circleR = min(w,h)*0.6*0.38`).
- **Performance.** Check the frame rate with `N_NODE`/`N_DUST`/edge counts on the
  target display machine; cap counts if needed (update typed arrays in place,
  don't rebuild geometry per frame).
- **Existing tests.** Keep `src/__tests__/i18n.test.js` green; no i18n keys
  removed.
- **Both color modes** (if Option B considered) checked on `/display` and
  `/feed`.

---

## 12. Risks

- **Spike/HUD drift** if rotation isn't eased during events — handle per §5.8.
- **Over-busy mesh** — keep `N_NODE` low and `maxDist` moderate; the charcoal
  dust, not the lines, should carry the volume.
- **Hand-drawn texture is the make-or-break detail** — lean on per-vertex
  jitter, faint multi-pass strokes, and dust density rather than clean
  single-pixel lines. It will evoke, not replicate, the baked Incite asset.
- **`#000` vs `#f6f5f7`** decided up front (§4) — changing midway means redoing
  every alpha ramp.

---

_Reference confirmed from the live archived page + `main.js` + `style.css`
(2021-03-25 capture). The Incite sphere is a pre-rendered video/image asset on a
`#f6f5f7` background with blinking DOM `+` markers; PYTHIA recreates the look
procedurally in Canvas 2D so it can react to live events._
