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
  const isNominal = state === "idle";
  const isAnalyzing = state === "analyzing";

  return (
    <div className={styles.hud}>
      {/* Top bar */}
      <div className={styles.topBar}>
        <span className={styles.systemName}>{t.systemName}</span>
        <span className={styles.subtitle}>{t.subtitle}</span>
      </div>

      {/* Center content */}
      <div className={styles.center}>
        {isNominal && !event && (
          <p className={styles.nominal}>{t.nominal}</p>
        )}
        {isAnalyzing && (
          <p className={styles.analyzing}>{t.analyzing}</p>
        )}
      </div>

      {/* Bottom data panel */}
      {event && !isAnalyzing && (
        <div className={styles.dataPanel}>
          <DataRow label={t.criticality} value={event.criticality.toFixed(1)} accent />
          <DataRow label={t.category} value={event.category} />
          {event.location && (
            <DataRow label={t.focalPoint} value={event.location} />
          )}
          <DataRow label={t.source} value={event.source} />
          <p className={styles.summary}>{event.title}</p>
        </div>
      )}
    </div>
  );
}

function DataRow({ label, value, accent }) {
  return (
    <div className={styles.dataRow}>
      <span className={styles.dataLabel}>{label}</span>
      <span className={accent ? styles.dataValueAccent : styles.dataValue}>
        {value}
      </span>
    </div>
  );
}
