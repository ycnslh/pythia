import { useContext } from "react";
import { WSContext } from "src/App";
import styles from "src/views/Feed.module.css";

const CATEGORY_CLASS = {
  NOMINAL: styles.badgeNominal,
  "ELEVATED SCRUTINY": styles.badgeScrutiny,
  DIVERGENCE: styles.badgeDivergence,
  "INTERVENTION IN PROGRESS": styles.badgeIntervention,
  "CRITICAL DIVERGENCE": styles.badgeCritical,
};

export default function Feed({ t }) {
  const { eventHistory, status } = useContext(WSContext);

  return (
    <div className={styles.feed}>
      <header className={styles.header}>
        <span className={styles.title}>{t.feedTitle}</span>
        <span className={styles.wsStatus} data-status={status}>
          {status.toUpperCase()}
        </span>
      </header>

      <div className={styles.list}>
        {eventHistory.length === 0 && (
          <p className={styles.empty}>{t.noEvents}</p>
        )}
        {eventHistory.map((event, i) => (
          <EventCard key={`${event.timestamp}-${i}`} event={event} t={t} />
        ))}
      </div>
    </div>
  );
}

function EventCard({ event, t }) {
  const badgeClass = CATEGORY_CLASS[event.category] ?? styles.badgeNominal;
  const date = new Date(event.timestamp);
  const timeStr = isNaN(date) ? event.timestamp : date.toLocaleString();

  return (
    <article className={styles.card}>
      <div className={styles.cardHeader}>
        <span className={`${styles.badge} ${badgeClass}`}>
          {event.criticality.toFixed(1)}
        </span>
        <span className={styles.category}>{event.category}</span>
        <time className={styles.time}>{timeStr}</time>
      </div>

      <h2 className={styles.cardTitle}>
        {event.url ? (
          <a href={event.url} target="_blank" rel="noopener noreferrer">
            {event.title}
          </a>
        ) : (
          event.title
        )}
      </h2>

      <p className={styles.summary}>{event.summary}</p>

      <div className={styles.meta}>
        {event.location && (
          <span>
            {t.focalPoint}: <strong>{event.location}</strong>
          </span>
        )}
        <span>
          {t.source}: <strong>{event.source}</strong>
        </span>
      </div>
    </article>
  );
}
