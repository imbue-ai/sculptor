import { useEffect, useRef } from "react";

import { baseUrl } from "../../../apiClient.ts";
import { getSessionToken, SESSION_TOKEN_HEADER_NAME } from "../../Auth.ts";
import { traceMark } from "../../tracing.ts";

const RECONNECT_DELAY = 1000;

export type WebsocketHookOptions<T> = {
  url: string;
  onMessage: (data: T) => void;
  onError?: (error: Event) => void;
  onOpen?: () => void;
  onClose?: () => void;
  enabled?: boolean;
};

/**
 * Hook for managing WebSocket connections with automatic reconnection
 */
export function useWebsocket<T>({
  url,
  onMessage,
  onError,
  onOpen,
  onClose,
  enabled = true,
}: WebsocketHookOptions<T>): void {
  // Use refs for callbacks to avoid stale closures
  const onMessageRef = useRef(onMessage);
  const onErrorRef = useRef(onError);
  const onOpenRef = useRef(onOpen);
  const onCloseRef = useRef(onClose);

  // We keep this ref to track if we've logged an error already on each successful connection. This protects us from
  // logging the same error multiple times during reconnections, chewing through our Sentry quota.
  const hasLoggedErrorRef = useRef(false);

  // Update refs when callbacks change
  useEffect(() => {
    onMessageRef.current = onMessage;
    onErrorRef.current = onError;
    onOpenRef.current = onOpen;
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!enabled) return;

    let ws: WebSocket | null = null;
    let reconnectTimeout: NodeJS.Timeout | null = null;
    let reconnectCount = 0;

    const connect = (): void => {
      try {
        // Convert HTTP URL to WebSocket URL
        const urlObj = new URL(url, baseUrl || window.location.origin);
        const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
        urlObj.protocol = protocol;

        // Add /ws suffix if it's a stream endpoint
        if (urlObj.pathname.endsWith("/stream")) {
          urlObj.pathname = urlObj.pathname + "/ws";
        }

        // Add the session token to URL params (CSRF protection)
        const sessionToken = getSessionToken();
        if (sessionToken) {
          urlObj.searchParams.set(SESSION_TOKEN_HEADER_NAME, sessionToken);
        }

        const wsUrl = urlObj.toString();
        console.log(`[WebSocket] Connecting to ${wsUrl}`);

        try {
          ws = new WebSocket(wsUrl);
        } catch (error) {
          if (!hasLoggedErrorRef.current) {
            hasLoggedErrorRef.current = true;
            console.error("[WebSocket] Failed to create WebSocket:", error);
          }
          return;
        }

        ws.onopen = (): void => {
          console.log(`[WebSocket] Connected to ${url}`);
          reconnectCount = 0;
          // Reset error logging state
          hasLoggedErrorRef.current = false;
          onOpenRef.current?.();
        };

        ws.onmessage = (event): void => {
          try {
            // Strip the query string before stamping the mark: mark names
            // land verbatim in the trace file, and the URL may carry a
            // session token in a query parameter in some code paths.
            traceMark(`ws.recv ${url.split("?")[0]}`);
            const data = JSON.parse(event.data);
            onMessageRef.current(data);
          } catch (error) {
            if (error instanceof SyntaxError) {
              console.trace("[WebSocket] Received non JSON message", error);
              return;
            }

            if (!hasLoggedErrorRef.current) {
              hasLoggedErrorRef.current = true;
              console.error("[WebSocket] Failed to parse message:", error);
            }
          }
        };

        ws.onerror = (event): void => {
          // PROD-1604: Websocket errors occur extremely often: in production when the server goes away and in testing
          // on the cleanup of every instance. We do not log a sentry error for this.
          onErrorRef.current?.(event);
        };

        ws.onclose = (event): void => {
          console.log(`[WebSocket] Connection closed for ${url}`, event);
          ws = null;
          onCloseRef.current?.();

          // Attempt reconnection
          reconnectCount++;
          console.log(`[WebSocket] Reconnecting in ${RECONNECT_DELAY}ms (attempt ${reconnectCount})`);

          reconnectTimeout = setTimeout(() => {
            connect();
          }, RECONNECT_DELAY);
        };
      } catch (error) {
        // We will swallow this error if we are flooding reconnects.
        if (!hasLoggedErrorRef.current) {
          hasLoggedErrorRef.current = true;
          console.error("[WebSocket] Failed to create WebSocket:", error);
        }
      }
    };

    connect();

    // Cleanup function
    return (): void => {
      // Clear any pending reconnect
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
        reconnectTimeout = null;
      }

      hasLoggedErrorRef.current = false;

      // Close the websocket
      if (ws) {
        // Remove event handlers to prevent reconnection
        ws.onclose = null;
        ws.onerror = null;
        ws.onopen = null;
        ws.onmessage = null;
        ws.close();
        ws = null;
      }
    };
  }, [enabled, url]);
}
