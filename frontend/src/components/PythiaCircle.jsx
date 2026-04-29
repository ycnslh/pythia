import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas stipple ring with localized wave deformation.
 *
 * The ring is a circle of stipple dots. Events deform the radius along a
 * narrow arc, producing outward "spike" formations rather than emitting
 * particles — Rehoboam-inspired monochrome silhouette on a black background.
 *
 * Props:
 *   state            — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality      — 1–10, drives wave amplitude
 *   queueSize        — adds a softer counter-arc on the opposite side
 *   emissionAngle    — radians, center of the deformed arc
 *   onReturnComplete — fired once the "returning" animation finishes
 */

const N_RING = 720;
const RETURN_DUR = 2.5;

function initRing() {
  const dots = [];
  for (let i = 0; i < N_RING; i++) {
    const halo = Math.random() > 0.78;
    dots.push({
      baseAngle: (i / N_RING) * Math.PI * 2 + (Math.random() - 0.5) * 0.006,
      jitter: halo
        ? (Math.random() - 0.5) * 7
        : (Math.random() - 0.5) * 2.2,
      phase: Math.random() * Math.PI * 2,
      size: Math.random() * 0.7 + 0.45,
      baseOpacity: Math.random() * 0.18 + 0.72,
    });
  }
  return dots;
}

function makeEmission(criticality, angle = null) {
  return {
    angle: angle ?? Math.random() * Math.PI * 2,
    halfWidth: 0.30 + (criticality / 10) * 0.45,
    strength: 0.45 + (criticality / 10) * 0.65,
  };
}

// Radial displacement at `angle`, in pixels.
// Localized by a Gaussian envelope around em.angle; combined harmonics
// give the silhouette its finger-like outward spikes.
function waveAt(angle, t, em, baseR, amp) {
  if (!em || amp <= 0) return 0;

  let da = angle - em.angle;
  while (da > Math.PI) da -= Math.PI * 2;
  while (da < -Math.PI) da += Math.PI * 2;

  const sigma = em.halfWidth;
  const env = Math.exp(-(da * da) / (2 * sigma * sigma));
  if (env < 0.015) return 0;

  const slow = Math.sin(angle * 6 + t * 0.55);
  const fast = Math.sin(angle * 19 + t * 1.6 + slow);
  const finger = Math.sin(angle * 35 + t * 2.2) * 0.4;
  const composite = slow * 0.55 + fast * 0.55 + finger;

  // Strong outward bias — small inward tail keeps the ring from feeling rigid
  const shaped = composite > 0 ? Math.pow(composite, 1.2) : composite * 0.18;

  const maxAmp = baseR * 0.45;
  return env * shaped * amp * em.strength * maxAmp;
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
      counterRef.current = {
        angle: emissionRef.current.angle + Math.PI,
        halfWidth: 0.7,
        strength: 0.35,
      };
    } else if (state === "divergence") {
      if (!emissionRef.current) emissionRef.current = makeEmission(criticality, emissionAngle);
      counterRef.current = {
        angle: emissionRef.current.angle + Math.PI,
        halfWidth: 0.7,
        strength: 0.35,
      };
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

      let waveAmp = 0;
      if (s === "analyzing") {
        waveAmp = Math.min(stateT / 2.5, 1) * 0.35;
      } else if (s === "divergence") {
        waveAmp = 1.0;
      } else if (s === "returning") {
        const prog = Math.min(stateT / RETURN_DUR, 1);
        waveAmp = Math.pow(1 - prog, 1.6);
      }

      const counterAmp = queue > 0 ? Math.min(queue / 3, 1) * 0.55 * waveAmp : 0;

      // Additive blending — overlapping dots brighten the spike tips
      ctx.globalCompositeOperation = "lighter";

      const breatheAmp = s === "idle" ? 1.3 : 0.65;
      const ringAlpha = s === "idle" ? 0.55 : 0.85;

      for (const dot of ringRef.current) {
        const breathe = Math.sin(totalT * 0.45 + dot.phase) * breatheAmp;
        const wave =
          waveAt(dot.baseAngle, totalT, emissionRef.current, baseR, waveAmp) +
          waveAt(dot.baseAngle, totalT, counterRef.current, baseR, counterAmp);

        const r = baseR + dot.jitter + breathe + wave;
        const x = cx + Math.cos(dot.baseAngle) * r;
        const y = cy + Math.sin(dot.baseAngle) * r;

        const tipBoost = wave > 0 ? Math.min(wave / (baseR * 0.25), 1) * 0.3 : 0;
        const a = Math.min(dot.baseOpacity * ringAlpha + tipBoost, 1);

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
