import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "~/api";
import { createWorkspaceAgent, createWorkspaceV2, WorkspaceInitializationStrategy } from "~/api";
import type * as NavigateUtilsModule from "~/common/NavigateUtils.ts";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";

import { useCreateWorkspace } from "./useCreateWorkspace.ts";

// The hook talks to the backend and the router; both are stubbed so the tests
// pin the hook's own contract — navigate on the workspace POST, create the
// agent in the background, and route failures to the global toast.
vi.mock("~/api", async (importOriginal) => ({
  ...(await importOriginal<typeof ApiModule>()),
  createWorkspaceV2: vi.fn(),
  createWorkspaceAgent: vi.fn(),
}));

const navigateToWorkspace = vi.fn();
const navigateToAgent = vi.fn();
vi.mock("~/common/NavigateUtils.ts", async (importOriginal) => ({
  ...(await importOriginal<typeof NavigateUtilsModule>()),
  useImbueNavigate: (): Record<string, unknown> => ({ navigateToWorkspace, navigateToAgent }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const CREATE_ARGS = {
  projectId: "p1",
  workspaceName: "WS",
  prompt: "",
  mode: WorkspaceInitializationStrategy.WORKTREE,
  sourceBranch: "main",
  branchName: "dev/ws",
  agentTypeValue: "claude" as const,
  registrations: [],
  defaultModel: "claude-sonnet",
};

const renderCreateWorkspaceHook = (): {
  store: ReturnType<typeof createStore>;
  result: { current: ReturnType<typeof useCreateWorkspace> };
} => {
  const store = createStore();
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  const { result } = renderHook(() => useCreateWorkspace(), { wrapper });
  return { store, result };
};

describe("useCreateWorkspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createWorkspaceV2).mockResolvedValue({
      data: { objectId: "ws_1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceV2>>);
    window.location.hash = "#/ws/ws_1";
  });

  afterEach(() => {
    cleanup();
  });

  it("navigates to the workspace as soon as its record exists, then focuses the agent", async () => {
    vi.mocked(createWorkspaceAgent).mockResolvedValue({
      data: { id: "agent_1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceAgent>>);
    const { store, result } = renderCreateWorkspaceHook();

    const createResult = await result.current.createWorkspace(CREATE_ARGS);

    expect(createResult).toEqual({ ok: true });
    expect(navigateToWorkspace).toHaveBeenCalledWith("ws_1");
    await waitFor(() => expect(navigateToAgent).toHaveBeenCalledWith("ws_1", "agent_1"));
    expect(store.get(createAgentErrorToastAtom)).toBeNull();
  });

  it("does not yank the user when they have left the workspace root", async () => {
    // A keep-open multi-create or the user opening an agent themselves moves
    // them off `#/ws/<id>`; the late background focus must not pull them back.
    vi.mocked(createWorkspaceAgent).mockResolvedValue({
      data: { id: "agent_1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceAgent>>);
    window.location.hash = "#/ws/ws_1/agent/their_own_agent";
    const { result } = renderCreateWorkspaceHook();

    await result.current.createWorkspace(CREATE_ARGS);

    await waitFor(() => expect(createWorkspaceAgent).toHaveBeenCalled());
    expect(navigateToAgent).not.toHaveBeenCalled();
  });

  it("reports a background agent-create failure via the global toast", async () => {
    vi.mocked(createWorkspaceAgent).mockRejectedValue(new Error("boom"));
    const { store, result } = renderCreateWorkspaceHook();

    // The workspace half still succeeds — the caller's flow is done.
    const createResult = await result.current.createWorkspace(CREATE_ARGS);

    expect(createResult).toEqual({ ok: true });
    expect(navigateToWorkspace).toHaveBeenCalledWith("ws_1");
    await waitFor(() => expect(store.get(createAgentErrorToastAtom)).not.toBeNull());
    expect(store.get(createAgentErrorToastAtom)).toMatchObject({ title: "Failed to create agent" });
    expect(navigateToAgent).not.toHaveBeenCalled();
  });
});
