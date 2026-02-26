import { useEffect, useState } from "react";
import styles from "src/components/HUDOverlay.module.css";

/**
 * HUD text overlay displayed over the PythiaCircle.
 *
 * Props:
 *   t        — i18n dictionary
 *   event    — EvaluatedEvent | null
 *   state    — "idle" | "analyzing" | "divergence" | "returning"
 */
export default function HUDOverlay({ t, event, state }) {
  const [vp, setVp] = useState({ w: window.innerWidth, h: window.innerHeight });

  useEffect(() => {
    const onResize = () => setVp({ w: window.innerWidth, h: window.innerHeight });
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  const isAnalyzing = state === "analyzing";
  const showData = !!event && !isAnalyzing;

  // ── Leader line geometry (must match PythiaCircle canvas math) ─────────────
  // Canvas size = min(vw, vh) * 0.6; base radius = canvas * 0.38
  const circleR = Math.min(vp.w, vp.h) * 0.6 * 0.38;
  const cx = vp.w / 2;
  const cy = vp.h / 2;
  // Anchor at ~195° — left side of circle, slightly above horizontal midline
  const anchorAngle = (195 * Math.PI) / 180;
  const anchorX = cx + Math.cos(anchorAngle) * circleR;
  const anchorY = cy + Math.sin(anchorAngle) * circleR;

  // Data block position (top-left)
  const TEXT_LEFT = 52;
  const TEXT_TOP = 60;
  // Line endpoint: bottom-right corner of approximate text block area
  const lineEndX = TEXT_LEFT + 220;
  const lineEndY = TEXT_TOP + 78;

  // Format time from ISO timestamp
  const timeStr = event?.timestamp
    ? new Date(event.timestamp).toLocaleTimeString("en-US", {
        hour12: false,
        hour: "2-digit",
        minute: "2-digit",
        second: "2-digit",
      })
    : null;

  return (
    <div className={styles.hud}>
      {/* Brand — top-right, very dim */}
      <div className={styles.brand}>
        <span className={styles.systemName}>{t.systemName}</span>
        <span className={styles.subtitle}>{t.subtitle}</span>
      </div>

      {/* Event data block — top-left */}
      {showData && (
        <div
          className={styles.dataBlock}
          style={{ top: TEXT_TOP, left: TEXT_LEFT }}
        >
          {timeStr && <div className={styles.timestamp}>{timeStr}</div>}
          <div className={styles.eventCategory}>
            {event.category}
            {event.location ? ` : ${event.location.toUpperCase()}` : ""}
          </div>
          <div className={styles.eventTitle}>{event.title}</div>
          <div className={styles.eventMeta}>
            {event.source}
            {" · "}
            <span className={styles.critValue}>{event.criticality.toFixed(1)}</span>
          </div>
        </div>
      )}

      {/* Analyzing indicator */}
      {isAnalyzing && (
        <div
          className={styles.analyzing}
          style={{ top: TEXT_TOP, left: TEXT_LEFT }}
        >
          {t.analyzing}
        </div>
      )}

      {/* Nominal — centered, barely visible */}
      {state === "idle" && !event && (
        <div className={styles.nominal}>{t.nominal}</div>
      )}

      {/* SVG leader line — only while data is visible */}
      {showData && (
        <svg className={styles.leaderSvg} xmlns="http://www.w3.org/2000/svg">
          {/* Crosshair at circle anchor point */}
          <circle
            cx={anchorX}
            cy={anchorY}
            r={3}
            fill="none"
            stroke="rgba(15,15,15,0.4)"
            strokeWidth={0.7}
          />
          <line
            x1={anchorX - 7} y1={anchorY}
            x2={anchorX + 7} y2={anchorY}
            stroke="rgba(15,15,15,0.3)"
            strokeWidth={0.6}
          />
          <line
            x1={anchorX} y1={anchorY - 7}
            x2={anchorX} y2={anchorY + 7}
            stroke="rgba(15,15,15,0.3)"
            strokeWidth={0.6}
          />
          {/* Diagonal leader */}
          <line
            x1={anchorX}
            y1={anchorY}
            x2={lineEndX}
            y2={lineEndY}
            stroke="rgba(15,15,15,0.2)"
            strokeWidth={0.5}
          />
        </svg>
      )}
    </div>
  );
}
