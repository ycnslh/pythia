import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas-based stipple ring with local particle emission.
 *
 * The ring itself stays circular at all times.
 * Alerts trigger particles that escape outward from a specific arc of the ring,
 * forming ripple-like puffs at the emission site.
 *
 * Props:
 *   state          — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality    — number 1–10
 *   queueSize      — pending events (adds secondary emission arcs)
 *   onReturnComplete — called when the "returning" animation finishes
 */

const N_RING = 480;
const MAX_PARTICLES = 600;
const RETURN_DUR = 2.5; // seconds

// 80% tight ring + 20% halo — natural ring thickness without deformation
function initRing() {
  const dots = [];
  for (let i = 0; i < N_RING; i++) {
    const halo = Math.random() > 0.8;
    dots.push({
      baseAngle: (i / N_RING) * Math.PI * 2 + (Math.random() - 0.5) * 0.008,
      jitter: halo
        ? (Math.random() - 0.5) * 8   // ±4px outer halo
        : (Math.random() - 0.5) * 3,  // ±1.5px tight ring
      phase: Math.random() * Math.PI * 2,
      size: Math.random() * 0.65 + 0.48,
      baseOpacity: Math.random() * 0.18 + 0.72,
    });
  }
  return dots;
}

function makeEmission(criticality, angle = null) {
  return {
    angle: angle ?? Math.random() * Math.PI * 2,
    halfWidth: (0.35 + (criticality / 10) * 0.85) / 2,
    strength: 0.35 + (criticality / 10) * 0.75,
  };
}

export default function PythiaCircle({ state, criticality = 0, queueSize = 0, emissionAngle = null, onReturnComplete }) {
  const canvasRef   = useRef(null);
  // performance.now() timestamps — consistent with rAF timestamps
  const mountRef    = useRef(performance.now());
  const startRef    = useRef(performance.now()); // resets on state change
  const stateRef    = useRef(state);
  const critRef     = useRef(criticality);
  const queueRef    = useRef(queueSize);
  const frameRef    = useRef(null);
  const ringRef     = useRef(null);
  const particlesRef = useRef([]);
  const emissionRef  = useRef(null);
  const returnNotifiedRef = useRef(false);

  // Sync props to refs during render — same frame as the prop change, no async delay.
  stateRef.current = state;
  critRef.current = criticality;
  queueRef.current = queueSize;

  // Reset phase timer and setup emission arc on state change
  useEffect(() => {
    startRef.current = performance.now(); // use same clock as rAF
    returnNotifiedRef.current = false;

    if (state === "analyzing") {
      emissionRef.current = makeEmission(criticality, emissionAngle);
    } else if (state === "divergence") {
      if (!emissionRef.current) emissionRef.current = makeEmission(criticality, emissionAngle);
    } else if (state === "idle") {
      emissionRef.current = null;
    }
  }, [state, criticality, emissionAngle]);

  // Animation loop — single instance for component lifetime.
  // onReturnComplete is wrapped in useCallback by the parent to keep this stable.
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    if (!ringRef.current) ringRef.current = initRing();

    // Cache the 2D context — same object reference, safe to reuse after resize
    const ctx = canvas.getContext("2d");

    const handleResize = () => {
      const size = Math.min(window.innerWidth, window.innerHeight) * 0.6;
      canvas.width = size;
      canvas.height = size;
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    // rAF loop — timestamp is performance.now(), same origin as mountRef / startRef
    const loop = (timestamp) => {
      const totalT = (timestamp - mountRef.current) / 1000; // never resets
      const stateT = (timestamp - startRef.current) / 1000; // resets per state
      // Real dt from actual frame delta, capped to avoid physics explosion after tab switch
      const dt = Math.min((timestamp - (loop._last ?? timestamp)) / 1000, 0.05);
      loop._last = timestamp;

      const W = canvas.width;
      const H = canvas.height;
      const cx = W / 2;
      const cy = H / 2;
      const baseR = W * 0.38;

      const s     = stateRef.current;
      const crit  = critRef.current;
      const queue = queueRef.current;

      ctx.clearRect(0, 0, W, H);

      // ── Emission params ────────────────────────────────────────────────────
      const em = emissionRef.current;
      let emitRate = 0;
      let emitStrength = 0;

      if (s === "idle") {
        emitRate = 1.5;
        emitStrength = 0.1;
      } else if (s === "analyzing" && em) {
        const prog = Math.min(stateT / 3, 1);
        emitRate = prog * (10 + crit * 3);
        emitStrength = em.strength * (0.25 + prog * 0.75);
      } else if (s === "divergence" && em) {
        emitRate = 16 + crit * 5;
        emitStrength = em.strength;
      } else if (s === "returning" && em) {
        const prog = Math.min(stateT / RETURN_DUR, 1);
        emitRate = (16 + crit * 5) * Math.pow(1 - prog, 2);
        emitStrength = em.strength * (1 - prog);
      }

      // ── Spawn primary particles ────────────────────────────────────────────
      const toSpawn = emitRate > 0 ? Math.floor(emitRate * dt + Math.random()) : 0;
      for (let i = 0; i < toSpawn && particlesRef.current.length < MAX_PARTICLES; i++) {
        let spawnAngle;
        if (em) {
          const u = Math.random() - Math.random(); // triangular distribution
          spawnAngle = em.angle + u * em.halfWidth;
        } else {
          spawnAngle = Math.random() * Math.PI * 2;
        }
        const speed = emitStrength * (0.3 + Math.random() * 0.7) * baseR * 0.04;
        particlesRef.current.push({
          angle: spawnAngle,
          radialOffset: (Math.random() - 0.5) * 3,
          tangentialDrift: 0,
          vr: speed,
          vt: (Math.random() - 0.5) * 0.005,
          life: 1.0,
          decay: 0.38 + Math.random() * 0.38,
          size: Math.random() * 0.85 + 0.3,
        });
      }

      // ── Spawn secondary particles (queue backpressure) ─────────────────────
      if (queue > 0 && em && s !== "idle") {
        const secRate = Math.min(queue * 4, 28);
        const toSpawnSec = Math.floor(secRate * dt + Math.random() * 0.5);
        const secBase = em.angle + Math.PI;
        for (let i = 0; i < toSpawnSec && particlesRef.current.length < MAX_PARTICLES; i++) {
          const secAngle = secBase + (Math.random() - 0.5) * Math.PI;
          const speed = 0.2 * (0.4 + Math.random() * 0.6) * baseR * 0.04;
          particlesRef.current.push({
            angle: secAngle,
            radialOffset: (Math.random() - 0.5) * 2,
            tangentialDrift: 0,
            vr: speed,
            vt: (Math.random() - 0.5) * 0.003,
            life: 1.0,
            decay: 0.45 + Math.random() * 0.45,
            size: Math.random() * 0.55 + 0.25,
          });
        }
      }

      // ── Update & draw particles ────────────────────────────────────────────
      const alive = [];
      for (const p of particlesRef.current) {
        p.radialOffset    += p.vr * dt;
        p.tangentialDrift += p.vt;
        p.life -= p.decay * dt;
        if (p.life <= 0) continue;
        alive.push(p);

        const r = baseR + p.radialOffset;
        if (r < 4) continue;

        const x = cx + Math.cos(p.angle + p.tangentialDrift) * r;
        const y = cy + Math.sin(p.angle + p.tangentialDrift) * r;

        let colR = 15, colG = 15, colB = 15;
        if (s !== "idle") {
          if (crit >= 8) { colR = 62; colG = 8;  colB = 8; }
          else if (crit >= 6) { colR = 38; colG = 14; colB = 6; }
        }

        ctx.beginPath();
        ctx.arc(x, y, p.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(${colR},${colG},${colB},${p.life * 0.75})`;
        ctx.fill();
      }
      particlesRef.current = alive;

      // ── Draw ring — always on top of particles ─────────────────────────────
      const breatheAmp = s === "idle" ? 1.3 : 0.65;
      const ringAlpha  = s === "idle" ? 0.64 : 0.9;

      for (const dot of ringRef.current) {
        const breathe = Math.sin(totalT * 0.45 + dot.phase) * breatheAmp;
        const r = baseR + dot.jitter + breathe;
        const x = cx + Math.cos(dot.baseAngle) * r;
        const y = cy + Math.sin(dot.baseAngle) * r;

        ctx.beginPath();
        ctx.arc(x, y, dot.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(15,15,15,${dot.baseOpacity * ringAlpha})`;
        ctx.fill();
      }

      // ── Notify return complete ─────────────────────────────────────────────
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
  }, [onReturnComplete]); // stable only if parent wraps handler in useCallback

  return <canvas ref={canvasRef} className={styles.canvas} />;
}
