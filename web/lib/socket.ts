"use client";

import { useEffect, useRef, useState } from "react";
import type { AriaEvent } from "./types";

type Handler = (e: AriaEvent) => void;

/**
 * Subscribe to Aria's event stream.
 *
 * IMPORTANT: We always connect to the global channel (`/ws/events` with no
 * call_id query param). Every event is double-published to the global channel
 * by the backend, so this gives us all events for all calls.
 *
 * Previous implementation reconnected on every callId change, which dropped
 * events during the reconnect window. Now we connect once and stay connected.
 */
export function useAriaSocket(_callId: string | null, onEvent: Handler) {
  const [connected, setConnected] = useState(false);
  const handlerRef = useRef(onEvent);
  handlerRef.current = onEvent;

  useEffect(() => {
    const wsUrl = process.env.NEXT_PUBLIC_WS_URL ?? "ws://localhost:8000";
    const url = `${wsUrl}/ws/events`;

    let ws: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let stopped = false;

    const connect = () => {
      ws = new WebSocket(url);

      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!stopped) {
          reconnectTimer = window.setTimeout(connect, 1000);
        }
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (msg) => {
        try {
          const event = JSON.parse(msg.data) as AriaEvent;
          handlerRef.current(event);
        } catch {
          /* ignore malformed frames */
        }
      };
    };

    connect();

    return () => {
      stopped = true;
      if (reconnectTimer) window.clearTimeout(reconnectTimer);
      ws?.close();
    };
    // Empty dep array — connect ONCE, never reconnect on state changes
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { connected };
}