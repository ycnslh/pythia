import { useEffect, useRef, useState, useCallback } from "react";

const RECONNECT_DELAY_MS = 3000;
const RECONNECT_DELAY_MAX_MS = 30000;
const RECONNECT_BACKOFF = 1.5;

/**
 * Persistent WebSocket connection with exponential-backoff reconnect.
 *
 * Returns:
 *   lastEvent    — most recently received EvaluatedEvent (or null)
 *   eventHistory — full list, newest first
 *   status       — "connecting" | "connected" | "disconnected"
 */
export function useWebSocket() {
  const wsRef = useRef(null);
  const delayRef = useRef(RECONNECT_DELAY_MS);
  const reconnectTimer = useRef(null);
  const isMounted = useRef(true);

  const [lastEvent, setLastEvent] = useState(null);
  const [eventHistory, setEventHistory] = useState([]);
  const [status, setStatus] = useState("connecting");

  const connect = useCallback(() => {
    if (!isMounted.current) return;

    // Build the WebSocket URL from the current page origin
    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${window.location.host}/ws`;

    setStatus("connecting");
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => {
      if (!isMounted.current) return;
      setStatus("connected");
      delayRef.current = RECONNECT_DELAY_MS; // reset backoff on success
    };

    ws.onmessage = (msg) => {
      if (!isMounted.current) return;
      try {
        const event = JSON.parse(msg.data);
        setLastEvent(event);
        setEventHistory((prev) => [event, ...prev].slice(0, 100));
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      if (!isMounted.current) return;
      setStatus("disconnected");
      scheduleReconnect();
    };

    ws.onerror = () => {
      ws.close(); // triggers onclose → reconnect
    };
  }, []);

  const scheduleReconnect = useCallback(() => {
    reconnectTimer.current = setTimeout(() => {
      delayRef.current = Math.min(
        delayRef.current * RECONNECT_BACKOFF,
        RECONNECT_DELAY_MAX_MS
      );
      connect();
    }, delayRef.current);
  }, [connect]);

  useEffect(() => {
    isMounted.current = true;
    connect();

    return () => {
      isMounted.current = false;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { lastEvent, eventHistory, status };
}
