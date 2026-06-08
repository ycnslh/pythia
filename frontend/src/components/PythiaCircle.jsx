import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas 2D geodesic sphere inspired by the Incite "Rehoboam" hero asset.
 *
 * The Incite original is a pre-rendered video/image, so it cannot react to live
 * events. PYTHIA instead builds the sphere procedurally (a Fibonacci point set,
 * proximity edges, perspective projection) so it can deform per event: nodes are
 * pushed outward along their normals at the emission direction, exactly like the
 * old 2D rim wave but on a sphere.
 *
 * Stays in the existing Canvas 2D stack — no Three.js, no new dependency. The 3D
 * math is ~30 lines (rotateX/rotateY + perspective divide).
 *
 * Layer order (back → front, all additive on black):
 *   1. Charcoal dust — dense Fibonacci cloud, alpha by silhouette (rim = packed).
 *   2. Mesh edges    — proximity graph, depth-faded graphite lines with jitter.
 *   3. Mesh nodes    — subtle dots at vertices, depth-faded.
 *   4. Frost halo    — persistent 2D rim halo for the frayed edge.
 *
 * Geometry (nodes, edges, dust) is built once. Each frame only rotates,
 * displaces, and projects it; nothing stochastic is resampled per frame.
 *
 * Props (unchanged contract — Display.jsx needs no edits):
 *   state            — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality      — 1–10, drives wave amplitude / spike sharpness
 *   queueSize        — adds a softer counter-bulge on the opposite side
 *   emissionAngle    — radians, screen angle the spike is anchored under (HUD)
 *   onReturnComplete — fired once the "returning" animation finishes
 */

// ── Tunables ─────────────────────────────────────────────────────────────────
const N_NODE = 130; // mesh vertices
const N_DUST = 720; // charcoal shading cloud
const N_FROST = 260; // rim halo dots
const MAX_EDGE_DIST = 0.55; // unit-sphere chord threshold for an edge
const TILT = 0.45; // constant X tilt (radians) so the pole structure shows
const SPIN_IDLE = 0.07; // idle spin speed (rad/s)
const SPIN_EVENT = 0.004; // spin eased to ~0 during an event so spikes stay put
const SPIN_EASE = 0.5; // how fast spin speed approaches its target (per s). Kept
//                        low so the idle rotation glides to a near-stop over a
//                        few seconds instead of freezing abruptly — an abrupt
//                        freeze reads as a "cut" when an event appears.
const D = 3.2; // camera distance for perspective divide
const FRONT_Z = 0.6; // z of the screen target → spike lands near the rim
const EDGE_MIN = 0.06; // back-edge opacity
const EDGE_MAX = 0.5; // front-edge opacity
const DUST_ALPHA = 0.5; // base charcoal alpha
const RETURN_DUR = 3.5; // seconds for the returning decay
const RISE_DUR = 2.8; // seconds to grow from nominal to full deformation. A
//                       continuous clock spans analyzing+divergence so there is
//                       no step at their boundary — even growth to the end.
const AMP = 0.5; // global displacement scale (kept low — a 3D bulge inflates a
//                  whole spherical cap, far more volume than a 2D rim arc)
const GOLDEN = Math.PI * (3 - Math.sqrt(5));

// ── Small vector helpers ─────────────────────────────────────────────────────
function clamp(v, lo, hi) {
  return v < lo ? lo : v > hi ? hi : v;
}
function smoothstep(x) {
  const t = x < 0 ? 0 : x > 1 ? 1 : x;
  return t * t * (3 - 2 * t);
}
function rotateY(p, a) {
  const c = Math.cos(a),
    s = Math.sin(a);
  return { x: p.x * c + p.z * s, y: p.y, z: -p.x * s + p.z * c };
}
function rotateX(p, a) {
  const c = Math.cos(a),
    s = Math.sin(a);
  return { x: p.x, y: p.y * c - p.z * s, z: p.y * s + p.z * c };
}
function normalize(p) {
  const m = Math.hypot(p.x, p.y, p.z) || 1;
  return { x: p.x / m, y: p.y / m, z: p.z / m };
}
function cross(a, b) {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

// ── Geometry (built once) ────────────────────────────────────────────────────
function fibSphere(n) {
  const pts = [];
  for (let i = 0; i < n; i++) {
    const y = 1 - (i / (n - 1)) * 2; // 1 → -1
    const r = Math.sqrt(Math.max(0, 1 - y * y));
    const th = i * GOLDEN;
    pts.push({ x: Math.cos(th) * r, y, z: Math.sin(th) * r });
  }
  return pts;
}

function initNodes() {
  return fibSphere(N_NODE).map((p) => ({
    ...p,
    phase: Math.random() * Math.PI * 2, // shimmer phase
    jx: (Math.random() - 0.5) * 1.0, // persistent hand-drawn pixel jitter
    jy: (Math.random() - 0.5) * 1.0,
    size: 0.5 + Math.random() * 0.5,
  }));
}

function initDust() {
  return fibSphere(N_DUST).map((p) => ({
    ...p,
    phase: Math.random() * Math.PI * 2,
    size: 0.22 + Math.random() * 0.5,
    alpha: 0.55 + Math.random() * 0.45,
  }));
}

function buildEdges(nodes) {
  const edges = [];
  const md2 = MAX_EDGE_DIST * MAX_EDGE_DIST;
  for (let i = 0; i < nodes.length; i++)
    for (let j = i + 1; j < nodes.length; j++) {
      const dx = nodes[i].x - nodes[j].x;
      const dy = nodes[i].y - nodes[j].y;
      const dz = nodes[i].z - nodes[j].z;
      if (dx * dx + dy * dy + dz * dz < md2) edges.push([i, j]);
    }
  return edges;
}

function initFrost() {
  const dots = [];
  for (let i = 0; i < N_FROST; i++) {
    const u = Math.pow(Math.random(), 1.7);
    dots.push({
      angle: Math.random() * Math.PI * 2,
      radialOffset: -2 + 9 * u,
      size: 0.25 + Math.random() * 0.35,
      baseAlpha: (1 - u) * 0.18,
      phase: Math.random() * Math.PI * 2,
    });
  }
  return dots;
}

// ── Emission (3D port of the old wave math) ──────────────────────────────────
// `dir` is filled per frame (ed for the main bulge, -ed for the counter).
function makeEmission(criticality) {
  const sigma = 0.34 + (criticality / 10) * 0.36; // broad great-circle stddev
  const nDaggers = 1 + Math.floor(Math.random() * 3);
  const daggers = [];
  for (let i = 0; i < nDaggers; i++) {
    daggers.push({
      a: (Math.random() - 0.5) * sigma * 1.3, // tangent offset from ed
      b: (Math.random() - 0.5) * sigma * 1.3,
      sigma: 0.07 + Math.random() * 0.06, // sharp
      reachMul: 1.3 + Math.random() * 0.9,
      seed: Math.random() * 10,
    });
  }
  return {
    dir: null,
    sigma,
    strength: 0.55 + (criticality / 10) * 0.55,
    seed: Math.random() * 10,
    daggers,
    daggerDirs: [], // resolved per frame from dir + tangent basis
  };
}

function makeCounter() {
  return {
    dir: null,
    sigma: 0.55,
    strength: 0.32,
    seed: Math.random() * 10,
    daggers: [],
    daggerDirs: [],
  };
}

// Orthonormal tangent basis at a unit direction.
function tangentBasis(ed) {
  const up = Math.abs(ed.y) > 0.99 ? { x: 1, y: 0, z: 0 } : { x: 0, y: 1, z: 0 };
  const t1 = normalize(cross(ed, up));
  const t2 = cross(ed, t1);
  return [t1, t2];
}

// Resolve dagger world directions from the (frozen-this-frame) emission dir.
function resolveDaggers(em) {
  if (!em.dir || em.daggers.length === 0) {
    em.daggerDirs = [];
    return;
  }
  const [t1, t2] = tangentBasis(em.dir);
  em.daggerDirs = em.daggers.map((d) =>
    normalize({
      x: em.dir.x + d.a * t1.x + d.b * t2.x,
      y: em.dir.y + d.a * t1.y + d.b * t2.y,
      z: em.dir.z + d.a * t1.z + d.b * t2.z,
    }),
  );
}

// Fractional outward push at unit node v (strength already folded in).
function emissionPush(v, em, t) {
  if (!em.dir) return 0;
  // Broad fluffy base — great-circle Gaussian with multi-frequency texture.
  const cosB = v.x * em.dir.x + v.y * em.dir.y + v.z * em.dir.z;
  const ang = Math.acos(clamp(cosB, -1, 1));
  let push = 0;
  const env = Math.exp(-(ang * ang) / (2 * em.sigma * em.sigma));
  if (env >= 0.015) {
    const s = em.seed;
    const w1 = Math.sin(ang * 11 + s * 17);
    const w2 = Math.sin(ang * 26 + s * 31) * 0.6;
    const w3 = Math.sin(ang * 49 + s * 43) * 0.32;
    const wobble = 0.85 + Math.sin(t * 0.18 + s) * 0.15;
    const composite = (w1 * 0.7 + w2 + w3) * wobble;
    const shaped = composite > 0 ? Math.pow(composite, 1.25) : 0;
    push += env * shaped * em.strength * 0.42;
  }
  // 1–3 sharp daggers.
  for (let k = 0; k < em.daggerDirs.length; k++) {
    const dd = em.daggerDirs[k];
    const c = v.x * dd.x + v.y * dd.y + v.z * dd.z;
    const da = Math.acos(clamp(c, -1, 1));
    const d = em.daggers[k];
    const denv = Math.exp(-(da * da) / (2 * d.sigma * d.sigma));
    if (denv < 0.02) continue;
    const wob = 0.88 + Math.sin(t * 0.25 + d.seed * 3) * 0.12;
    push += denv * wob * em.strength * 0.32 * d.reachMul;
  }
  return push;
}

export default function PythiaCircle({
  state,
  criticality = 0,
  queueSize = 0,
  emissionAngle = null,
  onReturnComplete,
}) {
  const canvasRef = useRef(null);
  const mountRef = useRef(performance.now());
  const startRef = useRef(performance.now());
  const lastTsRef = useRef(performance.now());
  const stateRef = useRef(state);
  const critRef = useRef(criticality);
  const queueRef = useRef(queueSize);
  const angleRef = useRef(emissionAngle);
  const frameRef = useRef(null);

  const nodesRef = useRef(null);
  const edgesRef = useRef(null);
  const dustRef = useRef(null);
  const frostRef = useRef(null);
  const projRef = useRef(null); // { x, y, z, f } parallel arrays for node projection

  const emissionRef = useRef(null);
  const counterRef = useRef(null);
  const spinRef = useRef(0); // accumulated spin angle
  const spinSpeedRef = useRef(SPIN_IDLE);
  const riseRef = useRef(0); // 0→1 grow-in progress across analyzing+divergence
  const returnNotifiedRef = useRef(false);

  stateRef.current = state;
  critRef.current = criticality;
  queueRef.current = queueSize;
  angleRef.current = emissionAngle;

  // Build / clear emission objects on state change (mirrors the old structure).
  useEffect(() => {
    startRef.current = performance.now();
    returnNotifiedRef.current = false;

    if (state === "analyzing") {
      emissionRef.current = makeEmission(criticality);
      counterRef.current = makeCounter();
    } else if (state === "divergence") {
      if (!emissionRef.current) {
        emissionRef.current = makeEmission(criticality);
        counterRef.current = makeCounter();
      }
    } else if (state === "idle") {
      emissionRef.current = null;
      counterRef.current = null;
    }
  }, [state, criticality, emissionAngle]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!nodesRef.current) nodesRef.current = initNodes();
    if (!edgesRef.current) edgesRef.current = buildEdges(nodesRef.current);
    if (!dustRef.current) dustRef.current = initDust();
    if (!frostRef.current) frostRef.current = initFrost();
    if (!projRef.current) {
      projRef.current = {
        x: new Float32Array(N_NODE),
        y: new Float32Array(N_NODE),
        z: new Float32Array(N_NODE),
        f: new Float32Array(N_NODE),
      };
    }

    const ctx = canvas.getContext("2d");

    // Full-viewport canvas so displaced spikes have room to extend without
    // clipping. baseR/center are still derived from the viewport (below) so
    // they stay identical to HUDOverlay's circleR = min(w,h)*0.6*0.38.
    const handleResize = () => {
      canvas.width = window.innerWidth;
      canvas.height = window.innerHeight;
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    const loop = (timestamp) => {
      const totalT = (timestamp - mountRef.current) / 1000;
      const stateT = (timestamp - startRef.current) / 1000;
      const dt = Math.min((timestamp - lastTsRef.current) / 1000, 0.05);
      lastTsRef.current = timestamp;

      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      // Match HUDOverlay exactly: circleR = min(w,h) * 0.6 * 0.38.
      const baseR = Math.min(W, H) * 0.6 * 0.38;

      const s = stateRef.current;
      const queue = queueRef.current;
      const fg = "255,255,255";

      ctx.clearRect(0, 0, W, H);

      // ── Wave amplitude — continuous grow-in, then decay ─────────────────────
      // A single progress clock rises 0→1 at a constant rate the whole time the
      // event is active (analyzing AND divergence — no step at their boundary),
      // shaped by smoothstep for even, pop-free growth all the way to full.
      // Returning multiplies that by the decay curve so the way out stays smooth.
      let waveAmp = 0;
      if (s === "analyzing" || s === "divergence") {
        riseRef.current = Math.min(1, riseRef.current + dt / RISE_DUR);
        waveAmp = smoothstep(riseRef.current);
      } else if (s === "returning") {
        const prog = Math.min(stateT / RETURN_DUR, 1);
        waveAmp = smoothstep(riseRef.current) * Math.pow(1 - prog, 1.8);
      } else {
        riseRef.current = 0; // idle — reset so the next event grows from nominal
      }
      const counterAmp =
        queue > 0 && waveAmp > 0 ? Math.min(queue / 3, 1) * 0.45 * waveAmp : 0;

      // ── Spin (eased to ~0 during an event so the spike stays anchored) ──────
      const inEvent = s === "analyzing" || s === "divergence";
      const targetSpeed = inEvent ? SPIN_EVENT : SPIN_IDLE;
      spinSpeedRef.current +=
        (targetSpeed - spinSpeedRef.current) * Math.min(dt * SPIN_EASE, 1);
      spinRef.current += spinSpeedRef.current * dt;
      const spin = spinRef.current;

      // ── Emission direction in model space (under the HUD anchor) ────────────
      // Inverse-rotate the front-hemisphere screen target by the current
      // (eased) spin+tilt so the bulge sits exactly under the leader line.
      const ang = angleRef.current;
      const em = emissionRef.current;
      const counter = counterRef.current;
      if (em && ang != null && waveAmp > 0) {
        const target = normalize({
          x: Math.cos(ang),
          y: Math.sin(ang),
          z: FRONT_Z,
        });
        const ed = rotateY(rotateX(target, -TILT), -spin);
        em.dir = ed;
        resolveDaggers(em);
        if (counter) {
          counter.dir = { x: -ed.x, y: -ed.y, z: -ed.z };
        }
      } else if (em) {
        em.dir = null;
        if (counter) counter.dir = null;
      }

      // Idle global shimmer amplitude (faint normal jitter). Scaled continuously
      // by waveAmp so it fades from 0.014 (nominal) to 0.005 (full event) without
      // a step at the appearance boundary.
      const shimmerAmp = 0.014 - 0.009 * Math.min(waveAmp, 1);

      // ── Project nodes (displaced) ───────────────────────────────────────────
      const nodes = nodesRef.current;
      const proj = projRef.current;
      for (let i = 0; i < nodes.length; i++) {
        const v = nodes[i];
        let push = shimmerAmp * Math.sin(totalT * 0.5 + v.phase);
        if (em && em.dir && waveAmp > 0) push += waveAmp * emissionPush(v, em, totalT);
        if (counter && counter.dir && counterAmp > 0)
          push += counterAmp * emissionPush(v, counter, totalT);
        push *= AMP;

        const m = 1 + push;
        const dvec = { x: v.x * m, y: v.y * m, z: v.z * m };
        const rv = rotateX(rotateY(dvec, spin), TILT);
        const factor = D / (D - rv.z);
        proj.x[i] = cx + rv.x * factor * baseR + v.jx;
        proj.y[i] = cy + rv.y * factor * baseR + v.jy;
        proj.z[i] = rv.z;
        proj.f[i] = clamp((rv.z + 1) / 2, 0, 1); // front-ness for opacity
      }

      ctx.globalCompositeOperation = "lighter";

      // ── Layer 1 — charcoal dust (silhouette-weighted) ───────────────────────
      const dust = dustRef.current;
      const dustPulse = 0.9 + Math.sin(totalT * 0.22) * 0.1;
      for (let i = 0; i < dust.length; i++) {
        const v = dust[i];
        let push = shimmerAmp * 0.6 * Math.sin(totalT * 0.5 + v.phase);
        if (em && em.dir && waveAmp > 0) push += waveAmp * emissionPush(v, em, totalT);
        if (counter && counter.dir && counterAmp > 0)
          push += counterAmp * emissionPush(v, counter, totalT);
        push *= AMP;

        const m = 1 + push;
        const dvec = { x: v.x * m, y: v.y * m, z: v.z * m };
        const rv = rotateX(rotateY(dvec, spin), TILT);
        const factor = D / (D - rv.z);
        const sx = cx + rv.x * factor * baseR;
        const sy = cy + rv.y * factor * baseR;

        const sil = Math.hypot(rv.x, rv.y); // 0 center → ~1+ rim/spike
        const frontFade = clamp((rv.z + 1) / 2, 0, 1);
        const a = clamp(
          DUST_ALPHA * v.alpha * Math.pow(sil, 1.6) * frontFade * dustPulse,
          0,
          1,
        );
        if (a < 0.01) continue;
        ctx.beginPath();
        ctx.arc(sx, sy, v.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${fg},${a})`;
        ctx.fill();
      }

      // ── Layer 2 — mesh edges (depth-faded graphite) ─────────────────────────
      const edges = edgesRef.current;
      for (let e = 0; e < edges.length; e++) {
        const a = edges[e][0];
        const b = edges[e][1];
        const fAvg = (proj.f[a] + proj.f[b]) / 2;
        const alpha = EDGE_MIN + (EDGE_MAX - EDGE_MIN) * fAvg;
        ctx.beginPath();
        ctx.moveTo(proj.x[a], proj.y[a]);
        ctx.lineTo(proj.x[b], proj.y[b]);
        ctx.strokeStyle = `rgba(${fg},${alpha})`;
        ctx.lineWidth = 0.6;
        ctx.stroke();
      }

      // ── Layer 3 — mesh nodes (subtle dots) ──────────────────────────────────
      for (let i = 0; i < nodes.length; i++) {
        const a = 0.12 + 0.55 * proj.f[i];
        ctx.beginPath();
        ctx.arc(proj.x[i], proj.y[i], nodes[i].size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${fg},${a})`;
        ctx.fill();
      }

      // ── Layer 4 — frost halo (persistent rim, frayed edge) ──────────────────
      const frostBoost = 1 + waveAmp * 0.45;
      for (const dot of frostRef.current) {
        const pulse = 0.85 + Math.sin(totalT * 0.22 + dot.phase) * 0.15;
        const r = baseR + dot.radialOffset;
        const x = cx + Math.cos(dot.angle) * r;
        const y = cy + Math.sin(dot.angle) * r;
        const alpha = dot.baseAlpha * pulse * frostBoost;
        ctx.beginPath();
        ctx.arc(x, y, dot.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${fg},${alpha})`;
        ctx.fill();
      }

      ctx.globalCompositeOperation = "source-over";

      if (s === "returning" && stateT >= RETURN_DUR && !returnNotifiedRef.current) {
        returnNotifiedRef.current = true;
        onReturnComplete?.();
      }

      frameRef.current = requestAnimationFrame(loop);
    };

    frameRef.current = requestAnimationFrame(loop);
    return () => {
      cancelAnimationFrame(frameRef.current);
      window.removeEventListener("resize", handleResize);
    };
  }, [onReturnComplete]);

  return <canvas ref={canvasRef} className={styles.canvas} />;
}
