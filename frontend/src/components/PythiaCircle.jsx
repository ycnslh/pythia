import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas stipple ring with a layered wave/disk composition.
 *
 * Layers from back to front:
 *   1. Spike cloud   — stochastic dots scattered in a polar zone around the
 *                      ring. Their angular distribution is biased toward the
 *                      emission angle; their radial reach grows with the wave
 *                      amplitude. Most of the cloud is masked by the disk;
 *                      only spikes that grow past the rim become visible,
 *                      forming the finger-like silhouette.
 *   2. Disk mask     — destination-out fill of radius baseR-1, erases
 *                      everything inside the rim back to transparency.
 *   3. Rim           — stipple ring drawn last; lives on top of the disk.
 *                      Slightly perturbed by the wave so the spike base feels
 *                      attached to the rim rather than floating.
 *
 * Props:
 *   state            — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality      — 1–10, drives wave amplitude
 *   queueSize        — adds a softer counter-arc on the opposite side
 *   emissionAngle    — radians, center of the deformed arc
 *   onReturnComplete — fired once the "returning" animation finishes
 */

const N_RING = 720;
const N_SPIKE_SAMPLES = 520; // stochastic samples per frame
const RETURN_DUR = 2.5;

function initRing() {
  const dots = [];
  for (let i = 0; i < N_RING; i++) {
    const halo = Math.random() > 0.78;
    dots.push({
      baseAngle: (i / N_RING) * Math.PI * 2 + (Math.random() - 0.5) * 0.006,
      jitter: halo
        ? (Math.random() - 0.5) * 6
        : (Math.random() - 0.5) * 2.0,
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
    halfWidth: 0.32 + (criticality / 10) * 0.38,
    strength: 0.55 + (criticality / 10) * 0.55,
    seed: Math.random() * 10,
  };
}

// Wave amplitude at a given angle, in pixels of outward radial reach.
// Mostly stationary spike pattern (indexed by da + seed) with a slow
// temporal wobble — feels like frozen crystals that breathe rather than
// like flowing water.
function waveAt(angle, t, em, baseR, amp) {
  if (!em || amp <= 0) return 0;

  let da = angle - em.angle;
  while (da > Math.PI) da -= Math.PI * 2;
  while (da < -Math.PI) da += Math.PI * 2;

  const env = Math.exp(-(da * da) / (2 * em.halfWidth * em.halfWidth));
  if (env < 0.015) return 0;

  // Spatial spike pattern — stationary across time so the shape is recognizable
  const seed = em.seed;
  const w1 = Math.sin(da * 13 + seed * 17);
  const w2 = Math.sin(da * 27 + seed * 31) * 0.55;
  const w3 = Math.sin(da * 51 + seed * 43) * 0.32;
  const wobble = 0.85 + Math.sin(t * 0.45 + seed) * 0.15;

  const composite = (w1 * 0.65 + w2 + w3) * wobble;
  // Outward bias — only positive lobes produce visible spikes
  const shaped = composite > 0 ? Math.pow(composite, 1.25) : 0;

  return env * shaped * amp * em.strength * baseR * 0.55;
}

// Sample an angle biased toward em.angle with roughly Gaussian density —
// avoids wasting samples on zones where the envelope is essentially zero.
function sampleEmissionAngle(em) {
  const u = Math.random() + Math.random() - 1; // triangular ~ Gaussian
  return em.angle + u * em.halfWidth * 1.6;
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
        halfWidth: 0.55,
        strength: 0.32,
        seed: Math.random() * 10,
      };
    } else if (state === "divergence") {
      if (!emissionRef.current) emissionRef.current = makeEmission(criticality, emissionAngle);
      counterRef.current = {
        angle: emissionRef.current.angle + Math.PI,
        halfWidth: 0.55,
        strength: 0.32,
        seed: Math.random() * 10,
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

      // ── Layer 1 — spike cloud (additive) ──────────────────────────────────
      // Most of these dots land inside the disk and will be masked away.
      // The fraction that lands beyond the rim forms the visible spikes.
      if (waveAmp > 0 || counterAmp > 0) {
        ctx.globalCompositeOperation = "lighter";

        const drawSpikeSamples = (em, amp, n) => {
          if (!em || amp <= 0) return;
          for (let i = 0; i < n; i++) {
            const angle = sampleEmissionAngle(em);
            const reach = waveAt(angle, totalT, em, baseR, amp);
            if (reach <= 0) continue;

            // Radial position: from slightly inside the rim to the spike tip.
            // pow bias concentrates dots near the base (denser there).
            const u = Math.pow(Math.random(), 1.4);
            const inset = Math.random() * 8;
            const radialOffset = -inset + (reach + inset) * u;
            const r = baseR + radialOffset;

            // Small angular jitter so spikes look watercolor-feathery
            const aJitter = (Math.random() - 0.5) * 0.05;
            const x = cx + Math.cos(angle + aJitter) * r;
            const y = cy + Math.sin(angle + aJitter) * r;

            // Tip taper — opacity and size decrease toward the tip
            const tipFrac = u; // 0 at base, 1 at tip
            const alpha = (1 - tipFrac * 0.7) * 0.55;
            const size = (1 - tipFrac * 0.55) * 0.55 + 0.22;

            ctx.beginPath();
            ctx.arc(x, y, size, 0, Math.PI * 2);
            ctx.fillStyle = `rgba(255,255,255,${alpha})`;
            ctx.fill();
          }
        };

        drawSpikeSamples(emissionRef.current, waveAmp, N_SPIKE_SAMPLES);
        drawSpikeSamples(counterRef.current, counterAmp, Math.floor(N_SPIKE_SAMPLES * 0.4));
      }

      // ── Layer 2 — disk mask ───────────────────────────────────────────────
      // Erases the inner region back to transparency, hiding the inward part
      // of the spike cloud. The body's black bg shows through.
      ctx.globalCompositeOperation = "destination-out";
      ctx.beginPath();
      ctx.arc(cx, cy, baseR - 1, 0, Math.PI * 2);
      ctx.fill();

      // ── Layer 3 — rim ─────────────────────────────────────────────────────
      ctx.globalCompositeOperation = "lighter";

      const breatheAmp = s === "idle" ? 1.3 : 0.65;
      const ringAlpha = s === "idle" ? 0.55 : 0.85;

      for (const dot of ringRef.current) {
        const breathe = Math.sin(totalT * 0.45 + dot.phase) * breatheAmp;
        // Subtle rim displacement so spike bases feel anchored to the rim
        const rimWave =
          waveAt(dot.baseAngle, totalT, emissionRef.current, baseR, waveAmp) * 0.18 +
          waveAt(dot.baseAngle, totalT, counterRef.current, baseR, counterAmp) * 0.18;

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
