import { useRef, useEffect } from "react";
import styles from "src/components/PythiaCircle.module.css";

/**
 * Canvas-based animated circle.
 *
 * Props:
 *   state        — "idle" | "analyzing" | "divergence" | "returning"
 *   criticality  — number 1–10
 *   onReturnComplete — called when the "returning" animation finishes
 */
export default function PythiaCircle({ state, criticality = 0, onReturnComplete }) {
  const canvasRef = useRef(null);
  const stateRef = useRef(state);
  const critRef = useRef(criticality);
  const frameRef = useRef(null);
  const startRef = useRef(Date.now());
  const particlesRef = useRef([]);
  const returnNotifiedRef = useRef(false);

  // Keep refs in sync with props
  useEffect(() => { stateRef.current = state; }, [state]);
  useEffect(() => { critRef.current = criticality; }, [criticality]);

  // Reset timer and particles when state changes
  useEffect(() => {
    startRef.current = Date.now();
    returnNotifiedRef.current = false;

    if (state === "divergence") {
      const canvas = canvasRef.current;
      if (!canvas) return;
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      particlesRef.current = spawnParticles(cx, cy, criticality);
    }
    if (state === "idle" || state === "analyzing") {
      particlesRef.current = [];
    }
  }, [state, criticality]);

  // Animation loop
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;

    const handleResize = () => {
      const size = Math.min(window.innerWidth, window.innerHeight) * 0.6;
      canvas.width = size;
      canvas.height = size;
    };
    handleResize();
    window.addEventListener("resize", handleResize);

    const loop = () => {
      const ctx = canvas.getContext("2d");
      const t = (Date.now() - startRef.current) / 1000;
      const cx = canvas.width / 2;
      const cy = canvas.height / 2;
      const baseRadius = canvas.width * 0.35;

      ctx.clearRect(0, 0, canvas.width, canvas.height);

      const currentState = stateRef.current;
      const crit = critRef.current;

      if (currentState === "idle") {
        drawIdle(ctx, cx, cy, baseRadius, t);
      } else if (currentState === "analyzing") {
        drawAnalyzing(ctx, cx, cy, baseRadius, t);
      } else if (currentState === "divergence") {
        drawDivergence(ctx, cx, cy, baseRadius, t, crit);
      } else if (currentState === "returning") {
        const done = drawReturning(ctx, cx, cy, baseRadius, t, crit);
        if (done && !returnNotifiedRef.current) {
          returnNotifiedRef.current = true;
          onReturnComplete?.();
        }
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

// ─── Drawing helpers ──────────────────────────────────────────────────────────

function drawCirclePath(ctx, cx, cy, radius, t, distortion = 0, steps = 180) {
  ctx.beginPath();
  for (let i = 0; i <= steps; i++) {
    const angle = (i / steps) * Math.PI * 2;
    const noise =
      distortion > 0
        ? Math.sin(angle * 3 + t * 0.7) * distortion * radius * 0.08 +
          Math.sin(angle * 7 - t * 1.1) * distortion * radius * 0.04 +
          Math.sin(angle * 13 + t * 0.4) * distortion * radius * 0.02
        : 0;
    const r = radius + noise;
    const x = cx + r * Math.cos(angle);
    const y = cy + r * Math.sin(angle);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  }
  ctx.closePath();
}

function drawGlow(ctx, cx, cy, radius, opacity, color = "255,255,255") {
  const grad = ctx.createRadialGradient(cx, cy, radius * 0.8, cx, cy, radius * 1.3);
  grad.addColorStop(0, `rgba(${color},${opacity * 0.2})`);
  grad.addColorStop(1, `rgba(${color},0)`);
  ctx.fillStyle = grad;
  ctx.beginPath();
  ctx.arc(cx, cy, radius * 1.3, 0, Math.PI * 2);
  ctx.fill();
}

function drawIdle(ctx, cx, cy, radius, t) {
  const pulse = 1 + Math.sin(t * 0.8) * 0.015;
  const r = radius * pulse;
  const opacity = 0.55 + Math.sin(t * 0.8) * 0.1;

  drawGlow(ctx, cx, cy, r, opacity * 0.4);
  drawCirclePath(ctx, cx, cy, r, t);
  ctx.strokeStyle = `rgba(255,255,255,${opacity})`;
  ctx.lineWidth = 1;
  ctx.stroke();
}

function drawAnalyzing(ctx, cx, cy, radius, t) {
  // Ink-spread distortion grows over time, capped at 1.0
  const distortion = Math.min(t / 4, 1.0);
  const opacity = 0.75 + Math.sin(t * 3) * 0.1;

  drawGlow(ctx, cx, cy, radius, 0.5);
  drawCirclePath(ctx, cx, cy, radius, t, distortion);
  ctx.strokeStyle = `rgba(255,255,255,${opacity})`;
  ctx.lineWidth = 1.5;
  ctx.stroke();

  // Scanning dash
  const dashAngle = (t * 1.2) % (Math.PI * 2);
  const dashLen = radius * 0.15;
  ctx.beginPath();
  ctx.moveTo(cx + radius * Math.cos(dashAngle), cy + radius * Math.sin(dashAngle));
  ctx.lineTo(
    cx + (radius + dashLen) * Math.cos(dashAngle),
    cy + (radius + dashLen) * Math.sin(dashAngle)
  );
  ctx.strokeStyle = "rgba(255,255,255,0.9)";
  ctx.lineWidth = 2;
  ctx.stroke();
}

function drawDivergence(ctx, cx, cy, radius, t, criticality) {
  const intensity = criticality / 10;

  // Update and draw particles
  const dt = 1 / 60;
  particlesRef.current = particlesRef.current
    .map((p) => ({
      ...p,
      x: p.x + p.vx,
      y: p.y + p.vy,
      vx: p.vx * 0.97,
      vy: p.vy * 0.97,
      life: p.life - dt * 0.6,
    }))
    .filter((p) => p.life > 0);

  for (const p of particlesRef.current) {
    ctx.globalAlpha = p.life;
    ctx.fillStyle = critColor(criticality);
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  // Distorted circle
  const distortion = intensity * (1 + Math.sin(t * 5) * 0.2);
  drawGlow(ctx, cx, cy, radius, 0.7, critColorRGB(criticality));
  drawCirclePath(ctx, cx, cy, radius, t, distortion);
  ctx.strokeStyle = critColor(criticality);
  ctx.lineWidth = 2;
  ctx.stroke();
}

function drawReturning(ctx, cx, cy, radius, t, criticality) {
  const RETURN_DURATION = 2.5;
  const progress = Math.min(t / RETURN_DURATION, 1);
  const distortion = (1 - progress) * (criticality / 10);
  const opacity = 0.3 + progress * 0.25;

  // Fade particles out
  particlesRef.current = particlesRef.current
    .map((p) => ({ ...p, life: p.life - 0.02 }))
    .filter((p) => p.life > 0);

  for (const p of particlesRef.current) {
    ctx.globalAlpha = p.life * (1 - progress);
    ctx.fillStyle = "white";
    ctx.beginPath();
    ctx.arc(p.x, p.y, p.size, 0, Math.PI * 2);
    ctx.fill();
  }
  ctx.globalAlpha = 1;

  drawGlow(ctx, cx, cy, radius, opacity * 0.3);
  drawCirclePath(ctx, cx, cy, radius, t, distortion);
  ctx.strokeStyle = `rgba(255,255,255,${opacity})`;
  ctx.lineWidth = 1 + (1 - progress);
  ctx.stroke();

  return progress >= 1;
}

// ─── Particles ────────────────────────────────────────────────────────────────

function spawnParticles(cx, cy, criticality) {
  const count = Math.floor(20 + criticality * 8);
  const speedBase = criticality * 0.4;
  return Array.from({ length: count }, () => {
    const angle = Math.random() * Math.PI * 2;
    const speed = (Math.random() * 0.6 + 0.4) * speedBase;
    return {
      x: cx,
      y: cy,
      vx: Math.cos(angle) * speed,
      vy: Math.sin(angle) * speed,
      life: 1.0,
      size: Math.random() * 2.5 + 0.5,
    };
  });
}

// ─── Color helpers ────────────────────────────────────────────────────────────

function critColorRGB(criticality) {
  if (criticality >= 8) return "255,32,32";
  if (criticality >= 6) return "255,107,53";
  return "255,255,255";
}

function critColor(criticality) {
  if (criticality >= 8) return "#ff2020";
  if (criticality >= 6) return "#ff6b35";
  return "#ffffff";
}
