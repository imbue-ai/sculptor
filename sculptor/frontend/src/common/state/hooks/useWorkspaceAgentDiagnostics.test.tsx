import { QueryClientProvider } from "@tanstack/react-query";
import type { RenderHookResult } from "@testing-library/react";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TaskStatus } from "~/api";
import { queryClient } from "~/common/state/queryClient";

import type { AgentDiagnosticsTarget } from "./useWorkspaceAgentDiagnostics";
import { useWorkspaceAgentDiagnostics } from "./useWorkspaceAgentDiagnostics";

const { mockGetWorkspaceAgentDiagnostics } = vi.hoisted(() => ({ mockGetWorkspaceAgentDiagnostics: vi.fn() }));

vi.mock("~/api", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return { ...original, getWorkspaceAgentDiagnostics: mockGetWorkspaceAgentDiagnostics };
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const emptyDiagnostics = {
  data: { sessionId: null, transcriptFilePath: null, sculptorTranscriptFilePath: null },
};
const sessionDiagnostics = {
  data: {
    sessionId: "session-1",
    transcriptFilePath: "/home/dev/.claude/projects/ws/session-1.jsonl",
    sculptorTranscriptFilePath: "/env/artifacts/tasks/agent-1/transcript.jsonl",
  },
};

type DiagnosticsHookResult = ReturnType<typeof useWorkspaceAgentDiagnostics>;
type DiagnosticsRenderProps = { targets: ReadonlyArray<AgentDiagnosticsTarget> };

const renderDiagnostics = (
  initialTargets: ReadonlyArray<AgentDiagnosticsTarget>,
): RenderHookResult<DiagnosticsHookResult, DiagnosticsRenderProps> =>
  renderHook(({ targets }) => useWorkspaceAgentDiagnostics("ws-1", targets), {
    wrapper: Wrapper,
    initialProps: { targets: initialTargets },
  });

// Yield a macrotask so any (unexpected) refetch scheduled by a rerender has a
// chance to hit the mock before a call-count assertion.
const flushAsync = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 25));

beforeEach(() => {
  vi.clearAllMocks();
  // TanStack Query's cache is a process-wide singleton; wipe it so each test
  // starts from a known empty state.
  queryClient.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useWorkspaceAgentDiagnostics", () => {
  it("maps fetched diagnostics by agent id", async () => {
    mockGetWorkspaceAgentDiagnostics.mockResolvedValue(sessionDiagnostics);
    const { result } = renderDiagnostics([{ agentId: "agent-1", status: TaskStatus.READY }]);

    await waitFor(() => expect(result.current["agent-1"]).toBeDefined());
    expect(result.current["agent-1"]).toEqual({
      sessionId: "session-1",
      claudeTranscriptPath: "/home/dev/.claude/projects/ws/session-1.jsonl",
      sculptorTranscriptPath: "/env/artifacts/tasks/agent-1/transcript.jsonl",
    });
  });

  it("refetches on a status change — including back to an already-seen status", async () => {
    // Regression: an agent view can transiently derive READY before its messages load, so
    // the first fetch may cache (agent, READY) with empty diagnostics. When the run
    // completes and status returns to READY, the hook must hit the network again — a
    // status-keyed cache would serve the stale empty entry forever (focus/reconnect
    // refetches are disabled client-wide).
    mockGetWorkspaceAgentDiagnostics.mockResolvedValue(emptyDiagnostics);
    const { result, rerender } = renderDiagnostics([{ agentId: "agent-1", status: TaskStatus.READY }]);
    await waitFor(() => expect(result.current["agent-1"]).toBeDefined());
    expect(result.current["agent-1"]?.sessionId).toBeNull();

    rerender({ targets: [{ agentId: "agent-1", status: TaskStatus.RUNNING }] });
    await waitFor(() => expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(2));

    mockGetWorkspaceAgentDiagnostics.mockResolvedValue(sessionDiagnostics);
    rerender({ targets: [{ agentId: "agent-1", status: TaskStatus.READY }] });
    await waitFor(() => expect(result.current["agent-1"]?.sessionId).toBe("session-1"));
    expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(3);
  });

  it("only refetches the agent whose status changed", async () => {
    mockGetWorkspaceAgentDiagnostics.mockResolvedValue(emptyDiagnostics);
    const { result, rerender } = renderDiagnostics([
      { agentId: "agent-1", status: TaskStatus.RUNNING },
      { agentId: "agent-2", status: TaskStatus.READY },
    ]);
    await waitFor(() => expect(Object.keys(result.current)).toHaveLength(2));
    expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(2);

    rerender({
      targets: [
        { agentId: "agent-1", status: TaskStatus.READY },
        { agentId: "agent-2", status: TaskStatus.READY },
      ],
    });
    await waitFor(() => expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(3));
    await flushAsync();
    expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(3);
    expect(mockGetWorkspaceAgentDiagnostics.mock.calls[2]?.[0]?.path).toEqual({
      workspace_id: "ws-1",
      agent_id: "agent-1",
    });
  });

  it("does not refetch when targets re-render with unchanged statuses", async () => {
    mockGetWorkspaceAgentDiagnostics.mockResolvedValue(emptyDiagnostics);
    const { result, rerender } = renderDiagnostics([{ agentId: "agent-1", status: TaskStatus.RUNNING }]);
    await waitFor(() => expect(result.current["agent-1"]).toBeDefined());

    // A fresh targets array with identical contents — the agent-tick shape.
    rerender({ targets: [{ agentId: "agent-1", status: TaskStatus.RUNNING }] });
    await flushAsync();
    expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(1);
  });

  it("keeps serving the previous diagnostics while a status-change refetch is in flight", async () => {
    // The registry-derived context menu reads this map live; a status change must not
    // blank out an agent's entry (briefly disabling its copy items) while the refetch
    // is pending.
    mockGetWorkspaceAgentDiagnostics.mockResolvedValueOnce(sessionDiagnostics);
    const { result, rerender } = renderDiagnostics([{ agentId: "agent-1", status: TaskStatus.RUNNING }]);
    await waitFor(() => expect(result.current["agent-1"]?.sessionId).toBe("session-1"));

    mockGetWorkspaceAgentDiagnostics.mockReturnValue(new Promise(() => {}));
    rerender({ targets: [{ agentId: "agent-1", status: TaskStatus.READY }] });
    await waitFor(() => expect(mockGetWorkspaceAgentDiagnostics).toHaveBeenCalledTimes(2));
    expect(result.current["agent-1"]?.sessionId).toBe("session-1");
  });
});
