import { useState, useEffect, useContext, useRef } from "react";
import PythiaCircle from "src/components/PythiaCircle";
import HUDOverlay from "src/components/HUDOverlay";
import { WSContext } from "src/App";
import styles from "src/views/Display.module.css";

// Display duration per criticality band (ms)
function displayDuration(criticality) {
  if (criticality >= 7) return 30_000;
  if (criticality >= 4) return 20_000;
  return 10_000;
}

// Gap between events — circle returns to bare idle before showing next
const GAP_MS = 2_000;

export default function Display({ t }) {
  const { lastEvent } = useContext(WSContext);

  // Queue of events pending display, sorted by criticality desc
  const pendingRef = useRef([]);
  const timerRef = useRef(null);
  const gapTimerRef = useRef(null); // non-null while in the inter-event gap

  const [circleState, setCircleState] = useState("idle");
  const [currentEvent, setCurrentEvent] = useState(null);
  const [queueSize, setQueueSize] = useState(0);

  // Enqueue incoming events
  useEffect(() => {
    if (!lastEvent) return;
    pendingRef.current.push(lastEvent);
    // Highest criticality first
    pendingRef.current.sort((a, b) => b.criticality - a.criticality);
    setQueueSize(pendingRef.current.length);

    // Only auto-advance if circle is truly idle (not in gap, not busy)
    if (circleState === "idle" && !gapTimerRef.current) {
      advance();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  function advance() {
    const next = pendingRef.current.shift();
    setQueueSize(pendingRef.current.length);

    if (!next) {
      setCircleState("idle");
      setCurrentEvent(null);
      return;
    }

    setCurrentEvent(next);
    setCircleState("analyzing");

    timerRef.current = setTimeout(() => {
      setCircleState("divergence");
      timerRef.current = setTimeout(() => {
        setCircleState("returning");
      }, displayDuration(next.criticality));
    }, 2_000);
  }

  function handleReturnComplete() {
    clearTimeout(timerRef.current);
    // Clear HUD — circle visually returns to bare idle
    setCurrentEvent(null);
    setCircleState("idle");

    if (pendingRef.current.length > 0) {
      // Brief pause before next event so the circle "breathes"
      gapTimerRef.current = setTimeout(() => {
        gapTimerRef.current = null;
        advance();
      }, GAP_MS);
    }
  }

  return (
    <div className={styles.display}>
      <PythiaCircle
        state={circleState}
        criticality={currentEvent?.criticality ?? 0}
        queueSize={queueSize}
        onReturnComplete={handleReturnComplete}
      />
      <HUDOverlay t={t} event={currentEvent} state={circleState} />
    </div>
  );
}
