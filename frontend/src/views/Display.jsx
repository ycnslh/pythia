import { useState, useEffect, useContext, useRef, useCallback } from "react";
import PythiaCircle from "src/components/PythiaCircle";
import HUDOverlay from "src/components/HUDOverlay";
import { WSContext } from "src/App";
import styles from "src/views/Display.module.css";

// Display duration: linear scale — 8s base + 3s per criticality point
// crit 1 → 8s, crit 5 → 20s, crit 10 → 35s
function displayDuration(criticality) {
  return (8 + (criticality - 1) * 3) * 1_000;
}

const GAP_MS = 2_000;

export default function Display({ t }) {
  const { lastEvent } = useContext(WSContext);

  const pendingRef     = useRef([]);
  const timerRef       = useRef(null);
  const gapTimerRef    = useRef(null);
  // Ref mirror of circleState — lets stable callbacks read current state without stale closure
  const circleStateRef = useRef("idle");

  const [circleState, setCircleState]   = useState("idle");
  const [currentEvent, setCurrentEvent] = useState(null);
  const [queueSize, setQueueSize]       = useState(0);
  // Emission angle: generated once per event, shared with both PythiaCircle and HUDOverlay
  // so the particle burst and the HUD label always point at the same spot on the ring.
  const [displayAngle, setDisplayAngle] = useState(null);

  // Keep ref in sync every render (safe outside useEffect for reads, not writes)
  circleStateRef.current = circleState;

  // Cleanup all timers on unmount
  useEffect(() => {
    return () => {
      clearTimeout(timerRef.current);
      clearTimeout(gapTimerRef.current);
    };
  }, []);

  // Stable advance — reads only refs + stable setState, no stale closure risk
  const advance = useCallback(() => {
    const next = pendingRef.current.shift();
    setQueueSize(pendingRef.current.length);

    if (!next) {
      setCircleState("idle");
      setCurrentEvent(null);
      setDisplayAngle(null);
      return;
    }

    // Single angle shared by canvas particles and HUD leader line
    setDisplayAngle(Math.random() * Math.PI * 2);
    setCurrentEvent(next);
    setCircleState("analyzing");

    timerRef.current = setTimeout(() => {
      setCircleState("divergence");
      timerRef.current = setTimeout(() => {
        setCircleState("returning");
      }, displayDuration(next.criticality));
    }, 2_000);
  }, []); // stable: only refs and stable setState

  // Stable callback — PythiaCircle's animation loop won't restart on every render
  const handleReturnComplete = useCallback(() => {
    clearTimeout(timerRef.current);
    setCurrentEvent(null);
    setDisplayAngle(null);
    setCircleState("idle");

    if (pendingRef.current.length > 0) {
      gapTimerRef.current = setTimeout(() => {
        gapTimerRef.current = null;
        advance();
      }, GAP_MS);
    }
  }, [advance]);

  // Enqueue incoming events
  useEffect(() => {
    if (!lastEvent) return;
    pendingRef.current.push(lastEvent);
    pendingRef.current.sort((a, b) => b.criticality - a.criticality);
    setQueueSize(pendingRef.current.length);

    // Use ref to check current state — avoids stale closure on circleState
    if (circleStateRef.current === "idle" && !gapTimerRef.current) {
      advance();
    }
  }, [lastEvent, advance]);

  return (
    <div className={styles.display}>
      <PythiaCircle
        state={circleState}
        criticality={currentEvent?.criticality ?? 0}
        queueSize={queueSize}
        emissionAngle={displayAngle}
        onReturnComplete={handleReturnComplete}
      />
      <HUDOverlay
        t={t}
        event={currentEvent}
        state={circleState}
        queueSize={queueSize}
        anchorAngle={displayAngle}
      />
    </div>
  );
}
