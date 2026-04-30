import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas stipple ring inspired by the Rehoboam structure: a flat disk in
 * the foreground with a textured "crater" of fibers behind it. Most of the
 * crater is hidden by the disk silhouette; only formations that grow past
 * the rim become visible — broad fluffy bases and 1–3 sharp daggers per
 * divergence.
 *
 * Layer order (back → front):
 *   1. Frost halo     — always-on per-frame cloud hugging the rim. Suggests
 *                       the back of the crater leaking around the disk.
 *   2. Spike cloud    — wave-driven bursts at the emission angle, plus
 *                       narrow "dagger" sub-emissions for dramatic outliers.
 *   3. Disk mask      — destination-out fill, erases the inner area.
 *   4. Rim            — stipple boundary on top of the disk, slightly
 *                       perturbed so the spike base feels anchored.
 *
 * Props:
 *   state            — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality      — 1–10, drives wave amplitude
 *   queueSize        — adds a softer counter-arc on the opposite side
 *   emissionAngle    — radians, center of the deformed arc
 *   onReturnComplete — fired once the "returning" animation finishes
 */

const N_RING = 600;
const N_FROST = 220; // ambient rim halo, every frame
const N_SPIKE = 700; // spike cloud, every frame when active
const RETURN_DUR = 2.5;

function initRing() {
  const dots = [];
  for (let i = 0; i < N_RING; i++) {
    dots.push({
      baseAngle: (i / N_RING) * Math.PI * 2 + (Math.random() - 0.5) * 0.005,
      jitter: (Math.random() - 0.5) * 1.8,
      phase: Math.random() * Math.PI * 2,
      size: Math.random() * 0.65 + 0.45,
      baseOpacity: Math.random() * 0.18 + 0.72,
    });
  }
  return dots;
}

function makeEmission(criticality, angle = null) {
  const baseAngle = angle ?? Math.random() * Math.PI * 2;
  const halfWidth = 0.34 + (criticality / 10) * 0.36;

  // 1-3 daggers — narrow, sharp sub-emissions inside the main envelope
  const nDaggers = 1 + Math.floor(Math.random() * 3);
  const daggers = [];
  for (let i = 0; i < nDaggers; i++) {
    daggers.push({
      angle: baseAngle + (Math.random() - 0.5) * halfWidth * 1.3,
      halfWidth: 0.025 + Math.random() * 0.04,
      reachMul: 1.4 + Math.random() * 1.1, // 1.4× to 2.5× of the broad reach
      seed: Math.random() * 10,
    });
  }

  return {
    angle: baseAngle,
    halfWidth,
    strength: 0.55 + (criticality / 10) * 0.55,
    seed: Math.random() * 10,
    daggers,
  };
}

// Broad fluffy base of the spike formation.
function broadWaveAt(angle, t, em, baseR, amp) {
  let da = angle - em.angle;
  while (da > Math.PI) da -= Math.PI * 2;
  while (da < -Math.PI) da += Math.PI * 2;

  const env = Math.exp(-(da * da) / (2 * em.halfWidth * em.halfWidth));
  if (env < 0.015) return 0;

  const seed = em.seed;
  const w1 = Math.sin(da * 11 + seed * 17);
  const w2 = Math.sin(da * 26 + seed * 31) * 0.6;
  const w3 = Math.sin(da * 49 + seed * 43) * 0.32;
  const wobble = 0.85 + Math.sin(t * 0.45 + seed) * 0.15;

  const composite = (w1 * 0.7 + w2 + w3) * wobble;
  const shaped = composite > 0 ? Math.pow(composite, 1.25) : 0;

  return env * shaped * amp * em.strength * baseR * 0.42;
}

// Dagger contribution — narrow, sharp, longer reach.
function daggerWaveAt(angle, t, em, baseR, amp) {
  if (!em.daggers) return 0;
  let total = 0;
  for (const d of em.daggers) {
    let da = angle - d.angle;
    while (da > Math.PI) da -= Math.PI * 2;
    while (da < -Math.PI) da += Math.PI * 2;

    const env = Math.exp(-(da * da) / (2 * d.halfWidth * d.halfWidth));
    if (env < 0.02) continue;

    const wobble = 0.88 + Math.sin(t * 0.7 + d.seed * 3) * 0.12;
    total += env * wobble * amp * em.strength * baseR * 0.32 * d.reachMul;
  }
  return total;
}

function waveAt(angle, t, em, baseR, amp) {
  if (!em || amp <= 0) return 0;
  return broadWaveAt(angle, t, em, baseR, amp) + daggerWaveAt(angle, t, em, baseR, amp);
}

// Triangular sampling around em.angle — concentrates samples where the envelope matters
function sampleEmissionAngle(em) {
  const u = Math.random() + Math.random() - 1;
  return em.angle + u * em.halfWidth * 1.7;
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
  const stateRef = useRef(state);
  const critRef = useRef(criticality);
  const queueRef = useRef(queueSize);
  const frameRef = useRef(null);
  const ringRef = useRef(null);
  const emissionRef = useRef(null);
  const counterRef = useRef(null);
  const returnNotifiedRef = useRef(false);

  stateRef.current = state;
  critRef.current = criticality;
  queueRef.current = queueSize;

  useEffect(() => {
    startRef.current = performance.now();
    returnNotifiedRef.current = false;

    if (state === "analyzing") {
      emissionRef.current = makeEmission(criticality, emissionAngle);
      counterRef.current = makeCounter(emissionRef.current.angle);
    } else if (state === "divergence") {
      if (!emissionRef.current) emissionRef.current = makeEmission(criticality, emissionAngle);
      counterRef.current = makeCounter(emissionRef.current.angle);
    } else if (state === "idle") {
      emissionRef.current = null;
      counterRef.current = null;
    }
  }, [state, criticality, emissionAngle]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!ringRef.current) ringRef.current = initRing();

    const ctx = canvas.getContext("2d");

    const handleResize = () => {
      const size = Math.min(window.innerWidth, window.innerHeight) * 0.6;
      canvas.width = size;
      canvas.height = size;
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    const loop = (timestamp) => {
      const totalT = (timestamp - mountRef.current) / 1000;
      const stateT = (timestamp - startRef.current) / 1000;

      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const baseR = W * 0.38;

      const s = stateRef.current;
      const queue = queueRef.current;

      ctx.clearRect(0, 0, W, H);

      // ── Wave amplitudes per state ─────────────────────────────────────────
      let waveAmp = 0;
      if (s === "analyzing") {
        waveAmp = Math.min(stateT / 2.3, 1) * 0.45;
      } else if (s === "divergence") {
        waveAmp = 1.0;
      } else if (s === "returning") {
        const prog = Math.min(stateT / RETURN_DUR, 1);
        waveAmp = Math.pow(1 - prog, 1.6);
      }

      const counterAmp =
        queue > 0 && waveAmp > 0 ? Math.min(queue / 3, 1) * 0.45 * waveAmp : 0;

      ctx.globalCompositeOperation = "lighter";

      // ── Layer 1 — frost halo (always on) ──────────────────────────────────
      // Suggests the back of the crater visible around the disk silhouette.
      // Slightly modulated by the breathing phase and brightened during events.
      const frostBoost = 1 + waveAmp * 0.4;
      const frostAlpha = 0.16 * frostBoost;
      for (let i = 0; i < N_FROST; i++) {
        const a = Math.random() * Math.PI * 2;
        const u = Math.pow(Math.random(), 1.7);
        const radialOffset = -2 + 9 * u;
        const r = baseR + radialOffset;
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        const alpha = (1 - u) * frostAlpha;
        const size = 0.25 + Math.random() * 0.35;
        ctx.beginPath();
        ctx.arc(x, y, size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${alpha})`;
        ctx.fill();
      }

      // ── Layer 2 — spike cloud + daggers ───────────────────────────────────
      const drawSpikeSamples = (em, amp, n) => {
        if (!em || amp <= 0) return;
        for (let i = 0; i < n; i++) {
          const angle = sampleEmissionAngle(em);
          const reach = waveAt(angle, totalT, em, baseR, amp);
          if (reach <= 0) continue;

          const u = Math.pow(Math.random(), 1.5);
          const inset = Math.random() * 8;
          const radialOffset = -inset + (reach + inset) * u;
          const r = baseR + radialOffset;

          const aJitter = (Math.random() - 0.5) * 0.045;
          const x = cx + Math.cos(angle + aJitter) * r;
          const y = cy + Math.sin(angle + aJitter) * r;

          // Bright base, faded tip — but not zero, so daggers stay legible
          const tipFrac = u;
          const alpha = (1 - tipFrac * 0.7) * 0.5;
          const size = (1 - tipFrac * 0.55) * 0.5 + 0.18;

          ctx.beginPath();
          ctx.arc(x, y, size, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255,255,255,${alpha})`;
          ctx.fill();
        }
      };

      drawSpikeSamples(emissionRef.current, waveAmp, N_SPIKE);
      drawSpikeSamples(counterRef.current, counterAmp, Math.floor(N_SPIKE * 0.35));

      // ── Layer 3 — disk mask ───────────────────────────────────────────────
      ctx.globalCompositeOperation = "destination-out";
      ctx.beginPath();
      ctx.arc(cx, cy, baseR - 1, 0, Math.PI * 2);
      ctx.fill();

      // ── Layer 4 — rim ─────────────────────────────────────────────────────
      ctx.globalCompositeOperation = "lighter";

      const breatheAmp = s === "idle" ? 1.2 : 0.6;
      const ringAlpha = s === "idle" ? 0.6 : 0.9;

      for (const dot of ringRef.current) {
        const breathe = Math.sin(totalT * 0.45 + dot.phase) * breatheAmp;
        const rimWave =
          waveAt(dot.baseAngle, totalT, emissionRef.current, baseR, waveAmp) * 0.15 +
          waveAt(dot.baseAngle, totalT, counterRef.current, baseR, counterAmp) * 0.15;

        const r = baseR + dot.jitter + breathe + rimWave;
        const x = cx + Math.cos(dot.baseAngle) * r;
        const y = cy + Math.sin(dot.baseAngle) * r;

        const a = Math.min(dot.baseOpacity * ringAlpha, 1);

        ctx.beginPath();
        ctx.arc(x, y, dot.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${a})`;
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

function makeCounter(mainAngle) {
  return {
    angle: mainAngle + Math.PI,
    halfWidth: 0.55,
    strength: 0.32,
    seed: Math.random() * 10,
    daggers: [], // counter-arc has no daggers
  };
}
