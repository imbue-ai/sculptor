import { renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useWebsocket } from "./useWebsocket.ts";

const SESSION_TOKEN = "super-secret-session-token";

// The hook appends the session token to the URL query string via getSessionToken().
vi.mock("../../Auth.ts", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getSessionToken: (): string => SESSION_TOKEN,
  };
});

// jsdom does not provide WebSocket; provide a no-op stub so the connect path runs.
class FakeWebSocket {
  onopen: ((this: unknown) => void) | null = null;
  onmessage: ((this: unknown, ev: unknown) => void) | null = null;
  onerror: ((this: unknown, ev: unknown) => void) | null = null;
  onclose: ((this: unknown, ev: unknown) => void) | null = null;
  constructor(public url: string) {}
  close(): void {}
}

describe("useWebsocket connect logging", () => {
  let logSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    vi.stubGlobal("WebSocket", FakeWebSocket as unknown as typeof WebSocket);
    logSpy = vi.spyOn(console, "log").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  // Regression: the connect log previously included the full wsUrl whose query
  // string carries the session token; it now logs wsUrl.split("?")[0]. Assert
  // the connect log line contains neither the token nor any query string.
  it("does not log the session token (query string) in the connect URL", () => {
    renderHook(() =>
      useWebsocket({
        url: "/api/v1/stream",
        onMessage: () => {},
      }),
    );

    const connectLog = logSpy.mock.calls
      .map((call: Array<unknown>) => String(call[0]))
      .find((line: string) => line.includes("[WebSocket] Connecting to"));

    expect(connectLog).toBeDefined();
    // Buggy behavior logged the full URL including ?x-session-token=<token>.
    expect(connectLog).not.toContain(SESSION_TOKEN);
    expect(connectLog).not.toContain("?");
  });
});
