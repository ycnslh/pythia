import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas-based stipple ring animation.
 *
 * Props:
 *   state          — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality    — number 1–10
 *   queueSize      — number of pending events (adds compound distortion)
 *   onReturnComplete — called when the "returning" animation finishes
 */

const N_DOTS = 720;
const RETURN_DUR = 2.5;

function initDots() {
  const dots = [];
  for (let i = 0; i < N_DOTS; i++) {
    // Triangle distribution: two randoms summed → peak at 0, range [-1, 1]
    const sf = Math.random() - Math.random();
    dots.push({
      // Slight angular jitter so the ring doesn't look perfectly quantized
      baseAngle: (i / N_DOTS) * Math.PI * 2 + (Math.random() - 0.5) * 0.009,
      spreadFactor: sf,                           // radial position within ring thickness
      phase: Math.random() * Math.PI * 2,         // individual breathing offset
      size: Math.random() * 0.75 + 0.45 + Math.abs(sf) * 0.2,
      baseOpacity: Math.random() * 0.22 + 0.72,
    });
  }
  return dots;
}

export default function PythiaCircle({ state, criticality = 0, queueSize = 0, onReturnComplete }) {
  const canvasRef = useRef(null);
  const stateRef = useRef(state);
  const critRef = useRef(criticality);
  const queueRef = useRef(queueSize);
  const frameRef = useRef(null);
  const startRef = useRef(Date.now());
  const dotsRef = useRef(null);
  const returnNotifiedRef = useRef(false);

  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { critRef.current = criticality; }, [criticality]);
  useEffect(() => { queueRef.current = queueSize; }, [queueSize]);

  // Reset phase timer on state change
  useEffect(() => {
    startRef.current = Date.now();
    returnNotifiedRef.current = false;
  }, [state]);

  // Animation loop — runs once for lifetime of component
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!dotsRef.current) dotsRef.current = initDots();

    const handleResize = () => {
      const size = Math.min(window.innerWidth, window.innerHeight) * 0.6;
      canvas.width = size;
      canvas.height = size;
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    const loop = () => {
      const ctx = canvas.getContext("2d");
      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const baseR = W * 0.38;
      const t = (Date.now() - startRef.current) / 1000;
      const s = stateRef.current;
      const crit = critRef.current;
      const queue = queueRef.current;

      ctx.clearRect(0, 0, W, H);

      // ── Distortion and spread per state ─────────────────────────────────────
      // distortion: amplitude of the sine-wave deformation (0 = perfect circle)
      // dotSpread:  ring thickness in px (how far dots scatter radially)
      let distortion = 0.06; // idle baseline — slightly organic, never perfectly round
      let dotSpread = 3.5;

      if (s === "idle") {
        distortion = 0.06;
        dotSpread = 3.5;
      } else if (s === "analyzing") {
        const prog = Math.min(t / 3, 1);
        distortion = 0.06 + prog * 0.36;
        dotSpread = 3.5 + prog * 9;
      } else if (s === "divergence") {
        const intensity = crit / 10;
        distortion = 0.4 + intensity * 0.6;
        dotSpread = 4 + intensity * 22;
      } else if (s === "returning") {
        const prog = Math.min(t / RETURN_DUR, 1);
        const intensity = crit / 10;
        // Ease cubic out: starts fast, slows at end
        const ease = 1 - Math.pow(1 - prog, 3);
        distortion = 0.06 + (1 - ease) * (0.4 + intensity * 0.6 - 0.06);
        dotSpread = 3.5 + (1 - ease) * (4 + intensity * 22 - 3.5);

        if (prog >= 1 && !returnNotifiedRef.current) {
          returnNotifiedRef.current = true;
          onReturnComplete?.();
        }
      }

      // Queue backpressure adds compound distortion
      const queueBonus = Math.min(queue * 0.07, 0.35);
      distortion += queueBonus;
      dotSpread += queue * 1.3;

      // ── Draw dots ──────────────────────────────────────────────────────────
      const dots = dotsRef.current;
      for (const dot of dots) {
        const angle = dot.baseAngle;

        // Multi-frequency sinusoidal deformation
        const d1 = Math.sin(angle * 3  + t * 0.7)  * distortion * baseR * 0.09;
        const d2 = Math.sin(angle * 7  - t * 1.3)  * distortion * baseR * 0.045;
        const d3 = Math.sin(angle * 17 + t * 0.55) * distortion * baseR * 0.022;
        const d4 = Math.sin(angle * 31 - t * 2.1)  * distortion * baseR * 0.01;

        // Slow individual breathing (each dot has its own phase)
        const breathe = Math.sin(t * 0.45 + dot.phase) * 1.8;

        // Final radial position: base + spread within ring + deformation + breathing
        const r = baseR + dot.spreadFactor * dotSpread + breathe + d1 + d2 + d3 + d4;
        const x = cx + Math.cos(angle) * r;
        const y = cy + Math.sin(angle) * r;

        // Opacity: falls off toward ring edges → tapered ring cross-section
        const edgeFalloff = 1 - Math.abs(dot.spreadFactor) * 0.55;
        const stateAlpha = s === "idle" ? 0.72 : 0.95;
        const alpha = dot.baseOpacity * edgeFalloff * stateAlpha;

        // Dot size grows slightly with distortion
        const sz = dot.size * (1 + (distortion - 0.06) * 0.45);

        // Color: monochrome baseline; dark tint only at high criticality in divergence
        let r0 = 15, g0 = 15, b0 = 15;
        if (s === "divergence" || s === "returning") {
          if (crit >= 8) { r0 = 72; g0 = 8; b0 = 8; }
          else if (crit >= 6) { r0 = 42; g0 = 18; b0 = 8; }
        }

        ctx.beginPath();
        ctx.arc(x, y, sz, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${r0},${g0},${b0},${alpha})`;
        ctx.fill();
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
