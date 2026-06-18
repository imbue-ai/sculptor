import * as Sentry from "@sentry/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { reportProblemAtom, submitReportAtom } from "./reportProblem";

// Preserve the real module (Telemetry.ts and others touch it) and override only
// the entry points the submit flow drives.
vi.mock("@sentry/react", async () => {
  const actual = await vi.importActual<typeof Sentry>("@sentry/react");
  return {
    ...actual,
    getClient: vi.fn(),
    captureFeedback: vi.fn(() => "evt-123"),
    withScope: vi.fn((cb: (scope: { setContext: () => void }) => string) => cb({ setContext: vi.fn() })),
    getReplay: vi.fn(() => undefined),
  };
});

describe("submitReportAtom", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  // A build with an empty Sentry DSN has no client; the flow must surface that
  // as an error rather than a fake "success".
  it("fails honestly when no Sentry client is configured", async () => {
    vi.mocked(Sentry.getClient).mockReturnValue(undefined);
    const store = createStore();
    store.set(reportProblemAtom, { ...store.get(reportProblemAtom), description: "something broke" });

    await store.set(submitReportAtom);

    expect(store.get(reportProblemAtom).submitState.type).toBe("error");
    expect(Sentry.captureFeedback).not.toHaveBeenCalled();
  });

  it("reports success when a Sentry client exists", async () => {
    vi.mocked(Sentry.getClient).mockReturnValue({} as ReturnType<typeof Sentry.getClient>);
    const store = createStore();
    store.set(reportProblemAtom, { ...store.get(reportProblemAtom), description: "something broke" });

    await store.set(submitReportAtom);

    const submitState = store.get(reportProblemAtom).submitState;
    expect(submitState.type).toBe("success");
    expect(Sentry.captureFeedback).toHaveBeenCalledOnce();
  });
});
