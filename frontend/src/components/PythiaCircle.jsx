import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas stipple ring inspired by the Rehoboam structure: a flat disk in
 * the foreground with a textured "crater" of fibers behind it. Most of the
 * crater is hidden by the disk silhouette; only formations that grow past
 * the rim become visible — broad fluffy bases and 1–3 sharp daggers per
 * divergence.
 *
 * All stochastic clouds are persistent (generated once, reused every frame)
 * so the silhouette breathes slowly instead of boiling. Per-frame stochastic
 * resampling produced a flicker that read as "too fast" even when the wave
 * function itself was slow.
 *
 * Layer order (back → front):
 *   1. Frost halo  — persistent rim halo, gently pulsed.
 *   2. Spike cloud — persistent dot field, regenerated only when an emission
 *                    starts. Each dot's visibility is gated by the wave reach
 *                    at its fixed angle, so the formation grows in place.
 *   3. Disk mask   — destination-out fill, erases the inner area.
 *   4. Rim         — stipple boundary on top of the disk.
 *
 * Props:
 *   state            — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality      — 1–10, drives wave amplitude
 *   queueSize        — adds a softer counter-arc on the opposite side
 *   emissionAngle    — radians, center of the deformed arc
 *   onReturnComplete — fired once the "returning" animation finishes
 */

const N_RING = 600;
const N_FROST = 260;
const N_SPIKE = 900;
const N_COUNTER = 320;
const RETURN_DUR = 3.5;

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

// Spike cloud — generated when an emission starts. Each dot stores a fixed
// position relative to the emission center; the wave reach at that angle
// gates visibility per frame.
function initSpikeCloud(n) {
  const dots = [];
  for (let i = 0; i < n; i++) {
    dots.push({
      angleU: Math.random() + Math.random() - 1, // triangular ~ Gaussian, -1..1
      radialU: Math.pow(Math.random(), 1.5),
      angleJitter: (Math.random() - 0.5) * 0.045,
      inset: Math.random() * 8,
      size: 0.18 + Math.random() * 0.5,
      alpha: 0.35 + Math.random() * 0.25,
    });
  }
  return dots;
}

function makeEmission(criticality, angle = null) {
  const baseAngle = angle ?? Math.random() * Math.PI * 2;
  const halfWidth = 0.34 + (criticality / 10) * 0.36;

  const nDaggers = 1 + Math.floor(Math.random() * 3);
  const daggers = [];
  for (let i = 0; i < nDaggers; i++) {
    daggers.push({
      angle: baseAngle + (Math.random() - 0.5) * halfWidth * 1.3,
      halfWidth: 0.025 + Math.random() * 0.04,
      reachMul: 1.4 + Math.random() * 1.1,
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

function makeCounter(mainAngle) {
  return {
    angle: mainAngle + Math.PI,
    halfWidth: 0.55,
    strength: 0.32,
    seed: Math.random() * 10,
    daggers: [],
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
  // Slow temporal wobble — was 0.45, now 0.18
  const wobble = 0.85 + Math.sin(t * 0.18 + seed) * 0.15;

  const composite = (w1 * 0.7 + w2 + w3) * wobble;
  const shaped = composite > 0 ? Math.pow(composite, 1.25) : 0;

  return env * shaped * amp * em.strength * baseR * 0.42;
}

function daggerWaveAt(angle, t, em, baseR, amp) {
  if (!em.daggers || em.daggers.length === 0) return 0;
  let total = 0;
  for (const d of em.daggers) {
    let da = angle - d.angle;
    while (da > Math.PI) da -= Math.PI * 2;
    while (da < -Math.PI) da += Math.PI * 2;

    const env = Math.exp(-(da * da) / (2 * d.halfWidth * d.halfWidth));
    if (env < 0.02) continue;

    // Was 0.7, now 0.25
    const wobble = 0.88 + Math.sin(t * 0.25 + d.seed * 3) * 0.12;
    total += env * wobble * amp * em.strength * baseR * 0.32 * d.reachMul;
  }
  return total;
}

function waveAt(angle, t, em, baseR, amp) {
  if (!em || amp <= 0) return 0;
  return broadWaveAt(angle, t, em, baseR, amp) + daggerWaveAt(angle, t, em, baseR, amp);
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
  const frostRef = useRef(null);
  const spikeRef = useRef(null);
  const counterCloudRef = useRef(null);
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
      spikeRef.current = initSpikeCloud(N_SPIKE);
      counterCloudRef.current = initSpikeCloud(N_COUNTER);
    } else if (state === "divergence") {
      if (!emissionRef.current) {
        emissionRef.current = makeEmission(criticality, emissionAngle);
        counterRef.current = makeCounter(emissionRef.current.angle);
        spikeRef.current = initSpikeCloud(N_SPIKE);
        counterCloudRef.current = initSpikeCloud(N_COUNTER);
      }
    } else if (state === "idle") {
      emissionRef.current = null;
      counterRef.current = null;
      spikeRef.current = null;
      counterCloudRef.current = null;
    }
  }, [state, criticality, emissionAngle]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!ringRef.current) ringRef.current = initRing();
    if (!frostRef.current) frostRef.current = initFrost();

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

      // ── Wave amplitudes per state — slowed envelopes ─────────────────────
      let waveAmp = 0;
      if (s === "analyzing") {
        // Was 2.3s, now 4s ramp
        waveAmp = Math.min(stateT / 4.0, 1) * 0.45;
      } else if (s === "divergence") {
        waveAmp = 1.0;
      } else if (s === "returning") {
        const prog = Math.min(stateT / RETURN_DUR, 1);
        waveAmp = Math.pow(1 - prog, 1.8);
      }

      const counterAmp =
        queue > 0 && waveAmp > 0 ? Math.min(queue / 3, 1) * 0.45 * waveAmp : 0;

      ctx.globalCompositeOperation = "lighter";

      // ── Layer 1 — frost halo (persistent) ─────────────────────────────────
      // Same dots every frame, gently pulsed by phase. Brightens during events.
      const frostBoost = 1 + waveAmp * 0.45;
      for (const dot of frostRef.current) {
        const pulse = 0.85 + Math.sin(totalT * 0.22 + dot.phase) * 0.15;
        const r = baseR + dot.radialOffset;
        const x = cx + Math.cos(dot.angle) * r;
        const y = cy + Math.sin(dot.angle) * r;
        const alpha = dot.baseAlpha * pulse * frostBoost;
        ctx.beginPath();
        ctx.arc(x, y, dot.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(255,255,255,${alpha})`;
        ctx.fill();
      }

      // ── Layer 2 — spike cloud (persistent, amplitude-gated) ───────────────
      const drawSpikeCloud = (em, cloud, amp) => {
        if (!em || !cloud || amp <= 0) return;
        const angularSpan = em.halfWidth * 1.7;
        for (const dot of cloud) {
          const angle = em.angle + dot.angleU * angularSpan;
          const reach = waveAt(angle, totalT, em, baseR, amp);
          if (reach <= 0) continue;

          const radialOffset = -dot.inset + (reach + dot.inset) * dot.radialU;
          const r = baseR + radialOffset;
          const x = cx + Math.cos(angle + dot.angleJitter) * r;
          const y = cy + Math.sin(angle + dot.angleJitter) * r;

          // Tip taper — fade and shrink toward the dot's radial fraction
          const tipFrac = dot.radialU;
          const a = dot.alpha * (1 - tipFrac * 0.65);
          const sz = dot.size * (1 - tipFrac * 0.45);

          ctx.beginPath();
          ctx.arc(x, y, sz, 0, Math.PI * 2);
          ctx.fillStyle = `rgba(255,255,255,${a})`;
          ctx.fill();
        }
      };

      drawSpikeCloud(emissionRef.current, spikeRef.current, waveAmp);
      drawSpikeCloud(counterRef.current, counterCloudRef.current, counterAmp);

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
        // Was 0.45, now 0.22
        const breathe = Math.sin(totalT * 0.22 + dot.phase) * breatheAmp;
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
