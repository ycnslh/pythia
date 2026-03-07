import { useState, useEffect } from "react";
import styles from "src/components/SystemPanel.module.css";

/**
 * Ambient system status panel — live clock, CPU/RAM bars, source health.
 * Displayed in the top-right corner below the brand block.
 * Read-only, no interaction.
 *
 * Props:
 *   t — i18n dictionary (needs t.locale, t.cpu, t.ram, t.sources)
 */
export default function SystemPanel({ t }) {
  const [now, setNow] = useState(new Date());
  const [sys, setSys] = useState(null);

  // Live clock — update every second
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  // System stats — poll every 5 seconds
  useEffect(() => {
    const fetchSys = () =>
      fetch("/api/system")
        .then((r) => r.json())
        .then(setSys)
        .catch(() => {});
    fetchSys();
    const id = setInterval(fetchSys, 5000);
    return () => clearInterval(id);
  }, []);

  const dateStr = now
    .toLocaleDateString(t.locale, { day: "2-digit", month: "short", year: "numeric" })
    .toUpperCase();

  const timeStr = now.toLocaleTimeString(t.locale, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  const ramDetail =
    sys &&
    (sys.ram_total_mb >= 1024
      ? `${(sys.ram_used_mb / 1024).toFixed(1)} / ${(sys.ram_total_mb / 1024).toFixed(1)} GB`
      : `${sys.ram_used_mb} / ${sys.ram_total_mb} MB`);

  return (
    <div className={styles.panel}>
      <div className={styles.clock}>
        <span className={styles.date}>{dateStr}</span>
        <span className={styles.time}>{timeStr}</span>
      </div>

      {sys && (
        <>
          <div className={styles.divider} />

          <div className={styles.metric}>
            <span className={styles.label}>{t.cpu}</span>
            <div className={styles.barTrack}>
              <div className={styles.barFill} style={{ width: `${sys.cpu}%` }} />
            </div>
            <span className={styles.value}>{sys.cpu.toFixed(0)}%</span>
          </div>

          <div className={styles.metric}>
            <span className={styles.label}>{t.ram}</span>
            <div className={styles.barTrack}>
              <div className={styles.barFill} style={{ width: `${sys.ram_pct}%` }} />
            </div>
            <span className={styles.value}>{sys.ram_pct.toFixed(0)}%</span>
          </div>

          <div className={styles.ramDetail}>{ramDetail}</div>

          {sys.sources?.length > 0 && (
            <>
              <div className={styles.divider} />
              <div className={styles.sourcesLabel}>{t.sources}</div>
              {sys.sources.map((s) => (
                <div key={s.name} className={styles.sourceRow}>
                  <span
                    className={styles.dot}
                    style={{
                      color: s.healthy
                        ? "rgba(30,100,30,0.85)"
                        : "rgba(140,30,30,0.85)",
                    }}
                  >
                    ●
                  </span>
                  <span className={styles.sourceName}>{s.name}</span>
                  <span className={styles.sourceType}>{s.type.toUpperCase()}</span>
                </div>
              ))}
            </>
          )}
        </>
      )}
    </div>
  );
}
