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

export default function Display({ t }) {
  const { lastEvent } = useContext(WSContext);

  // Queue of events pending display, sorted by criticality desc
  const pendingRef = useRef([]);
  const timerRef = useRef(null);

  const [circleState, setCircleState] = useState("idle");
  const [currentEvent, setCurrentEvent] = useState(null);

  // Enqueue incoming events
  useEffect(() => {
    if (!lastEvent) return;
    pendingRef.current.push(lastEvent);
    // Keep highest criticality first
    pendingRef.current.sort((a, b) => b.criticality - a.criticality);
    if (circleState === "idle") {
      advance();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastEvent]);

  function advance() {
    const next = pendingRef.current.shift();
    if (!next) {
      setCircleState("idle");
      setCurrentEvent(null);
      return;
    }
    setCurrentEvent(next);
    setCircleState("analyzing");

    // Simulate brief analyzing phase, then show divergence
    setTimeout(() => {
      setCircleState("divergence");
      timerRef.current = setTimeout(() => {
        setCircleState("returning");
      }, displayDuration(next.criticality));
    }, 2_000);
  }

  function handleReturnComplete() {
    clearTimeout(timerRef.current);
    advance();
  }

  return (
    <div className={styles.display}>
      <PythiaCircle
        state={circleState}
        criticality={currentEvent?.criticality ?? 0}
        onReturnComplete={handleReturnComplete}
      />
      <HUDOverlay t={t} event={currentEvent} state={circleState} />
    </div>
  );
}
