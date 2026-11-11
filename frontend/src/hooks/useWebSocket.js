import { useEffect, useRef, useState, useCallback } from "react";

const RECONNECT_DELAY_MS = 3000;
const RECONNECT_DELAY_MAX_MS = 30000;
const RECONNECT_BACKOFF = 1.5;

const HISTORY_MAX = 100;

/**
 * Pure reducer for one server frame. Frames are:
 *   { type: "history", events: [...] }  — sent once per connection, oldest first
 *   { type: "event",   event: {...} }   — a live event
 *
 * History REPLACES the list (a reconnect must not duplicate events) and never
 * touches `lastEvent`, so /display does not replay old events on (re)connect.
 * Only live events update `lastEvent`.
 */
export function applyFrame(state, frame) {
  if (frame?.type === "history" && Array.isArray(frame.events)) {
    return {
      ...state,
      eventHistory: [...frame.events].reverse().slice(0, HISTORY_MAX),
    };
  }
  if (frame?.type === "event" && frame.event) {
    return {
      lastEvent: frame.event,
      eventHistory: [frame.event, ...state.eventHistory].slice(0, HISTORY_MAX),
    };
  }
  return state;
}

/**
 * Persistent WebSocket connection with exponential-backoff reconnect.
 *
 * Returns:
 *   lastEvent    — most recent LIVE EvaluatedEvent (or null); never set by history
 *   eventHistory — full list, newest first
 *   status       — "connecting" | "connected" | "disconnected"
 */
export function useWebSocket() {
  const wsRef = useRef(null);
  const delayRef = useRef(RECONNECT_DELAY_MS);
  const reconnectTimer = useRef(null);
  const isMounted = useRef(true);
  const connectRef = useRef(null); // lets onclose re-enter connect() without a circular dependency

  const [events, setEvents] = useState({ lastEvent: null, eventHistory: [] });
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
        const frame = JSON.parse(msg.data);
        setEvents((prev) => applyFrame(prev, frame));
      } catch {
        // ignore malformed frames
      }
    };

    ws.onclose = () => {
      if (!isMounted.current) return;
      setStatus("disconnected");
      reconnectTimer.current = setTimeout(() => {
        delayRef.current = Math.min(
          delayRef.current * RECONNECT_BACKOFF,
          RECONNECT_DELAY_MAX_MS
        );
        connectRef.current();
      }, delayRef.current);
    };

    ws.onerror = () => {
      ws.close(); // triggers onclose → reconnect
    };
  }, []);

  useEffect(() => {
    isMounted.current = true;
    connectRef.current = connect;
    connect();

    return () => {
      isMounted.current = false;
      clearTimeout(reconnectTimer.current);
      wsRef.current?.close();
    };
  }, [connect]);

  return { lastEvent: events.lastEvent, eventHistory: events.eventHistory, status };
}
