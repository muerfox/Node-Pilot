import { useEffect, useRef } from "react";

import { authenticatedWsUrl } from "@/lib/api";

/**
 * Subscribes to a NodePilot WebSocket channel (section 36) for the
 * lifetime of the component. Reconnects with a short fixed backoff on
 * disconnect -- job/console/event streams are long-lived and the
 * backend already tolerates reconnects (job state is always replayed
 * via a snapshot message on connect, e.g. JobConsumer). Each (re)connect
 * fetches a fresh single-use auth ticket -- see authenticatedWsUrl.
 */
export function useWebSocketSubscription(path: string | null, onMessage: (data: unknown) => void) {
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;

  useEffect(() => {
    if (!path) return;
    let socket: WebSocket | null = null;
    let cancelled = false;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;

    const connect = async () => {
      let url: string;
      try {
        url = await authenticatedWsUrl(path);
      } catch {
        if (!cancelled) retryTimer = setTimeout(connect, 2000);
        return;
      }
      if (cancelled) return;

      socket = new WebSocket(url);
      socket.onmessage = (event) => {
        try {
          onMessageRef.current(JSON.parse(event.data));
        } catch {
          // Non-JSON frame (e.g. binary console data handled elsewhere); ignore here.
        }
      };
      socket.onclose = (event) => {
        if (cancelled || event.code === 4403 || event.code === 4401) return;
        retryTimer = setTimeout(connect, 2000);
      };
    };

    connect();

    return () => {
      cancelled = true;
      clearTimeout(retryTimer);
      socket?.close();
    };
  }, [path]);
}
