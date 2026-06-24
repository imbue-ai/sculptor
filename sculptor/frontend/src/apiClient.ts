import { HTTPException, RequestTimeoutError, ValidationError } from "~/common/Errors.ts";

import { client } from "./api/client.gen";
import { setupAuthHeaders } from "./common/Auth.ts";
import { initBackendCapabilities } from "./common/state/atoms/backendCapabilities.ts";
import { createRequestTracker } from "./common/state/requestTracking.ts";
import { makeRequestId } from "./common/Utils.ts";
import { isElectron } from "./electron/utils.ts";

type TrackingConfig = {
  /** Custom timeout in milliseconds for WebSocket acknowledgment */
  customTimeoutMs?: number;
  /** Whether to skip WebSocket tracking entirely */
  shouldSkipTracking: boolean;
};

/**
 * Per-request meta options callers pass through the generated client's `meta`
 * field. The client types `meta` as `Record<string, unknown>` and does not
 * surface it on the interceptor's options type, so we narrow it here.
 */
type RequestMeta = {
  timeout?: number;
  skipWsAck?: boolean;
  signal?: AbortSignal;
};

/**
 * Internal headers used as a transport mechanism for meta options
 * SKIP_WS_ACK is stripped before the request reaches the backend
 */
const INTERNAL_HEADERS = {
  SKIP_WS_ACK: "Sculptor-Skip-WS-Ack",
  REQUEST_TIMEOUT: "Sculptor-Request-Timeout",
  REQUEST_ID: "Sculptor-Request-ID",
} as const;

/**
 * Custom fetch implementation that adds request tracking and session token headers
 *
 * This function:
 * 1. Generates a unique request ID for tracking
 * 2. Sets up session token headers (CSRF protection)
 * 3. Creates a request tracker that waits for WebSocket acknowledgment
 * 4. Ensures proper cleanup on error
 *
 * @param input - The resource to fetch (URL, Request, or string)
 * @param init - Request initialization options
 * @returns A Promise that resolves to the Response
 */
export const makeAPIRequest = async (input: RequestInfo | URL, init: RequestInit = {}): Promise<Response> => {
  const requestId = makeRequestId();

  let headers: Headers;
  if (input instanceof Request) {
    // If it's a Request, use its headers (which may have been modified by interceptor)
    headers = new Headers(input.headers);
  } else {
    // Otherwise, use headers from init
    headers = new Headers(init.headers ?? {});
  }

  headers.set(INTERNAL_HEADERS.REQUEST_ID, requestId);

  setupAuthHeaders(headers);
  const trackingConfig = extractTrackingConfig(headers);
  setupContentTypeHeader(headers, init.body);

  const urlString = extractUrlString(input);

  const tracker = trackingConfig.shouldSkipTracking
    ? createNoOpTracker()
    : createRequestTracker(requestId, urlString, trackingConfig.customTimeoutMs);

  try {
    const response = await fetch(input, { ...init, headers });

    if (response.status === 403 && response.headers.get("x-error-code") === "invalid_session_token") {
      console.error("Invalid session token - cannot recover");
    }

    if (!response.ok) {
      tracker.cancel();

      let errorDetail = `HTTP ${response.status}`;
      // A FastAPI validation failure is an HTTP 422 whose body is
      // `{ detail: [...] }`. The 422 lives on the Response, not in the JSON
      // body, so it must be read from `response.status` (not `errorData.status`,
      // which doesn't exist on the body). Capture the detail here and throw
      // after the try/catch so the ValidationError isn't swallowed by the bare
      // `catch` that guards JSON parsing (SCU-1365).
      let validationErrors: ValidationError["detail"] | undefined;
      try {
        const errorData = await response.json();
        if (errorData.detail && typeof errorData.detail === "string") {
          errorDetail = errorData.detail;
        } else if (response.status === 422 && Array.isArray(errorData.detail)) {
          validationErrors = errorData.detail;
        }
      } catch {
        // Failed to parse JSON, use default error message
      }

      if (validationErrors !== undefined) {
        throw new ValidationError(validationErrors);
      }
      throw new HTTPException(response.status, errorDetail);
    }

    await tracker.wait;
    return response;
  } catch (error) {
    tracker.cancel();
    if (error instanceof DOMException && error.name === "TimeoutError") {
      throw new RequestTimeoutError("Request timed out");
    }
    throw error;
  }
};

export let baseUrl: string;

/**
 * Configures the API client with custom fetch and interceptors
 *
 * This function:
 * 1. Sets up the base URL and custom fetch implementation
 * 2. Adds a request interceptor to handle meta options for tracking
 * 3. Initialises backend capability flags for the session
 */
export const configureClient = async (): Promise<void> => {
  let isRemoteBackend = false;

  if (API_URL_BASE !== undefined) {
    baseUrl = API_URL_BASE;
  } else if (window.sculptor) {
    const backendUrl = await window.sculptor.getBackendUrl();

    if (backendUrl) {
      baseUrl = backendUrl;
      isRemoteBackend = true;
    } else {
      baseUrl = `http://localhost:${await window.sculptor.getBackendPort()}`;
    }
  }

  // Web builds (e.g. self-hosted/OpenHost) compile API_URL_BASE to "" (same-origin)
  // rather than leaving it undefined, so the first branch above runs and
  // isRemoteBackend stays false — even though there is no Electron IPC bridge.
  // Treat the absence of window.sculptor as a remote backend so file
  // uploads/downloads/previews go over HTTP instead of the (nonexistent) Electron
  // IPC channel. The desktop app and the Electron custom-backend case are
  // unaffected: they have window.sculptor, so isElectron() is true.
  initBackendCapabilities(isRemoteBackend || !isElectron());

  client.setConfig({
    baseUrl,
    fetch: makeAPIRequest,
  });

  // Interceptor converts meta options to headers that our custom fetch can read
  client.interceptors.request.use((request, options): Request => {
    const meta = (options as { meta?: RequestMeta }).meta;

    if (!meta) {
      return request;
    }

    const headers = new Headers(request.headers);

    if (meta.timeout) {
      headers.set(INTERNAL_HEADERS.REQUEST_TIMEOUT, String(meta.timeout));
    }

    if (meta.skipWsAck) {
      headers.set(INTERNAL_HEADERS.SKIP_WS_ACK, "true");
    }

    const signal = meta.signal ?? (meta.timeout ? AbortSignal.timeout(meta.timeout) : null);

    // Create a new Request with the modified headers
    return new Request(request, {
      headers,
      signal,
    });
  });
};

const extractUrlString = (input: RequestInfo | URL): string => {
  if (typeof input === "string") {
    return input;
  }

  if (typeof Request !== "undefined" && input instanceof Request) {
    return input.url;
  }

  if (typeof URL !== "undefined" && input instanceof URL) {
    return input.toString();
  }

  return String(input);
};

const extractTrackingConfig = (headers: Headers): TrackingConfig => {
  const timeoutHeader = headers.get(INTERNAL_HEADERS.REQUEST_TIMEOUT);
  const customTimeoutMs = timeoutHeader ? parseInt(timeoutHeader, 10) : undefined;
  const shouldSkipTracking = headers.get(INTERNAL_HEADERS.SKIP_WS_ACK) === "true";

  // Clean up the internal header before the request goes to the backend
  headers.delete(INTERNAL_HEADERS.SKIP_WS_ACK);

  return {
    customTimeoutMs,
    shouldSkipTracking,
  };
};

const setupContentTypeHeader = (headers: Headers, body: unknown): void => {
  const isJsonBody = typeof body === "string";
  const hasContentType = headers.has("Content-Type");

  if (isJsonBody && !hasContentType) {
    headers.set("Content-Type", "application/json");
  }
};

const createNoOpTracker = (): { wait: Promise<void>; cancel: () => void } => {
  return {
    wait: Promise.resolve(),
    cancel: (): void => {},
  };
};
