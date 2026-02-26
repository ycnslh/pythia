import { useRef, useEffect, useState } from "react";
import styles from "src/components/HUDOverlay.module.css";

/**
 * HUD text overlay displayed over the PythiaCircle.
 *
 * All transitions are CSS-driven (no abrupt show/hide).
 * A "lastEventRef" keeps the last known event in the DOM during fade-out,
 * so the element never disappears before its opacity hits zero.
 *
 * The text block and leader line are positioned dynamically based on
 * anchorAngle — the same angle used by PythiaCircle for particle emission.
 * This ensures the HUD label always appears near the active burst site.
 *
 * Props:
 *   t           — i18n dictionary
 *   event       — EvaluatedEvent | null
 *   state       — "idle" | "analyzing" | "divergence" | "returning"
 *   queueSize   — number of pending events (suppresses NOMINAL during gap)
 *   anchorAngle — radians (shared with PythiaCircle), null when idle
 */

// Estimated text block dimensions for placement math.
// Vertical is approximate — clamping handles the rest.
const BLOCK_W = 260;
const BLOCK_H = 100;
// Gap between circle surface and text block attachment point (px).
const PAD = 54;

export default function HUDOverlay({ t, event, state, queueSize = 0, anchorAngle = null }) {
  // Keep the last non-null event for rendering during fade-out.
  // When event becomes null (gap state), we still render the old data
  // but at opacity 0 — no data disappears before it's invisible.
  const lastEventRef = useRef(null);
  const displayEvent = event || lastEventRef.current;
  if (event) lastEventRef.current = event;

  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });
  useEffect(() => {
    const onResize = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // ── Circle geometry (must match PythiaCircle canvas math) ──────────────────
  const circleR = Math.min(vp.w, vp.h) * 0.6 * 0.38;
  const cx = vp.w / 2;
  const cy = vp.h / 2;

  // ── Radial placement ────────────────────────────────────────────────────────
  // Use the provided angle, falling back to a fixed position for the idle state
  // (which is only ever rendered at opacity 0, so it doesn't matter visually).
  const effectiveAngle = anchorAngle ?? ((195 * Math.PI) / 180);
  const radX = Math.cos(effectiveAngle);
  const radY = Math.sin(effectiveAngle);

  // Point on circle surface
  const anchorX = cx + radX * circleR;
  const anchorY = cy + radY * circleR;

  // Attachment point just outside the circle, along the radial
  const attachX = cx + radX * (circleR + PAD);
  const attachY = cy + radY * (circleR + PAD);

  // Place the block so it flows away from the center.
  // When the angle is mostly horizontal: flow left/right, center vertically.
  // When mostly vertical: flow up/down, center horizontally.
  let blockLeft, blockTop, lineEndX, lineEndY;
  if (Math.abs(radX) >= Math.abs(radY)) {
    // Horizontal dominant
    blockLeft = radX >= 0 ? attachX : attachX - BLOCK_W;
    blockTop  = attachY - BLOCK_H / 2;
    lineEndX  = radX >= 0 ? blockLeft : blockLeft + BLOCK_W; // nearest vertical edge
    lineEndY  = blockTop + BLOCK_H / 2;                      // middle of that edge
  } else {
    // Vertical dominant
    blockLeft = attachX - BLOCK_W / 2;
    blockTop  = radY >= 0 ? attachY : attachY - BLOCK_H;
    lineEndX  = blockLeft + BLOCK_W / 2;                     // middle of nearest horizontal edge
    lineEndY  = radY >= 0 ? blockTop : blockTop + BLOCK_H;
  }

  // Clamp to viewport so the block never clips off-screen
  blockLeft = Math.max(12, Math.min(vp.w - BLOCK_W - 12, blockLeft));
  blockTop  = Math.max(12, Math.min(vp.h - BLOCK_H - 12, blockTop));

  // Format timestamp
  const timeStr = displayEvent?.timestamp
    ? new Date(displayEvent.timestamp).toLocaleTimeString(t.locale, {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  // ── Opacity targets — CSS transitions do the rest ─────────────────────────
  // Data block & leader: visible only in divergence.
  const dataOpacity    = state === "divergence" ? 1 : 0;
  // Analyzing indicator: visible only while analyzing.
  const analyzeOpacity = state === "analyzing" ? 1 : 0;
  // Nominal: visible only in true idle with nothing queued.
  const nominalOpacity = state === "idle" && !event && queueSize === 0 ? 1 : 0;

  return (
    <div className={styles.hud}>

      {/* Brand — top-right, always dim */}
      <div className={styles.brand}>
        <span className={styles.systemName}>{t.systemName}</span>
        <span className={styles.subtitle}>{t.subtitle}</span>
      </div>

      {/* Analyzing indicator — same position as data block, fades in during analyzing */}
      <div
        className={styles.fadeWrap}
        style={{ opacity: analyzeOpacity, top: blockTop, left: blockLeft }}
      >
        <p className={styles.analyzing}>{t.analyzing}</p>
      </div>

      {/* Nominal — wrapper drives fade */}
      <div className={`${styles.fadeWrap} ${styles.nominalWrap}`} style={{ opacity: nominalOpacity }}>
        <p className={styles.nominal}>{t.nominal}</p>
      </div>

      {/* Data block — always in DOM (using lastEventRef), opacity-controlled */}
      {displayEvent && (
        <>
          <div
            className={styles.dataBlock}
            style={{ opacity: dataOpacity, top: blockTop, left: blockLeft }}
          >
            {timeStr && <div className={styles.timestamp}>{timeStr}</div>}
            <div className={styles.eventCategory}>
              {displayEvent.category}
              {displayEvent.location
                ? ` : ${displayEvent.location.toUpperCase()}`
                : ""}
            </div>
            <div className={styles.eventTitle}>{displayEvent.title}</div>
            <div className={styles.eventMeta}>
              {displayEvent.source}
              {" · "}
              <span className={styles.critValue}>
                {displayEvent.criticality.toFixed(1)}
              </span>
            </div>
          </div>

          {/* SVG leader line — fades with the data block */}
          <svg
            className={styles.leaderSvg}
            style={{ opacity: dataOpacity }}
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx={anchorX} cy={anchorY} r={3}
              fill="none" stroke="rgba(15,15,15,0.4)" strokeWidth={0.7}
            />
            <line
              x1={anchorX - 7} y1={anchorY} x2={anchorX + 7} y2={anchorY}
              stroke="rgba(15,15,15,0.3)" strokeWidth={0.6}
            />
            <line
              x1={anchorX} y1={anchorY - 7} x2={anchorX} y2={anchorY + 7}
              stroke="rgba(15,15,15,0.3)" strokeWidth={0.6}
            />
            <line
              x1={anchorX} y1={anchorY} x2={lineEndX} y2={lineEndY}
              stroke="rgba(15,15,15,0.2)" strokeWidth={0.5}
            />
          </svg>
        </>
      )}
    </div>
  );
}
