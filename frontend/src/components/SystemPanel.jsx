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

// Split out so the 1 s tick does not re-render the metric bars / source list.
function Clock({ locale }) {
  const [now, setNow] = useState(new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(id);
  }, []);

  const dateStr = now
    .toLocaleDateString(locale, { day: "2-digit", month: "short", year: "numeric" })
    .toUpperCase();

  const timeStr = now.toLocaleTimeString(locale, {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  return (
    <div className={styles.clock}>
      <span className={styles.date}>{dateStr}</span>
      <span className={styles.time}>{timeStr}</span>
    </div>
  );
}

export default function SystemPanel({ t }) {
  const [sys, setSys] = useState(null);

  // System stats — poll every 5 seconds
  useEffect(() => {
    const controller = new AbortController();
    const fetchSys = () =>
      fetch("/api/system", { signal: controller.signal })
        .then((r) => r.json())
        .then(setSys)
        .catch(() => {});
    fetchSys();
    const id = setInterval(fetchSys, 5000);
    return () => {
      controller.abort();
      clearInterval(id);
    };
  }, []);

  const ramDetail =
    sys &&
    (sys.ram_total_mb >= 1024
      ? `${(sys.ram_used_mb / 1024).toFixed(1)} / ${(sys.ram_total_mb / 1024).toFixed(1)} GB`
      : `${sys.ram_used_mb} / ${sys.ram_total_mb} MB`);

  return (
    <div className={styles.panel}>
      <Clock locale={t.locale} />

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

          <div className={styles.metric}>
            <span className={styles.label}>{t.disk}</span>
            <div className={styles.barTrack}>
              <div className={styles.barFill} style={{ width: `${sys.disk_pct}%` }} />
            </div>
            <span className={styles.value}>{sys.disk_pct.toFixed(0)}%</span>
          </div>
          <div className={styles.ramDetail}>
            {sys.disk_used_gb} / {sys.disk_total_gb} GB
          </div>

          {sys.gpu != null && (
            <div className={styles.metric}>
              <span className={styles.label}>{t.gpu}</span>
              <div className={styles.barTrack}>
                <div className={styles.barFill} style={{ width: `${sys.gpu}%` }} />
              </div>
              <span className={styles.value}>{sys.gpu.toFixed(0)}%</span>
            </div>
          )}

          {sys.temps && Object.keys(sys.temps).length > 0 && (
            <>
              <div className={styles.divider} />
              <div className={styles.sourcesLabel}>{t.temp}</div>
              <div className={styles.tempGrid}>
                {Object.entries(sys.temps).map(([key, val]) => (
                  <div key={key} className={styles.tempCell}>
                    <span className={styles.tempLabel}>{key}</span>
                    <span className={styles.tempValue}>{val.toFixed(0)}°</span>
                  </div>
                ))}
              </div>
            </>
          )}

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
