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

  it("does not yank the user when they leave the workspace root mid-create", async () => {
    // A keep-open multi-create or the user opening an agent themselves moves
    // them off `#/ws/<id>` while the background create is still in flight;
    // the late focus must read the route at resolution time and stand down.
    // Hold the agent create open, move the user, then release it.
    let resolveAgentCreate!: (value: Awaited<ReturnType<typeof createWorkspaceAgent>>) => void;
    const deferredAgentCreate = new Promise<Awaited<ReturnType<typeof createWorkspaceAgent>>>((resolve) => {
      resolveAgentCreate = resolve;
    });
    vi.mocked(createWorkspaceAgent).mockReturnValue(deferredAgentCreate as ReturnType<typeof createWorkspaceAgent>);
    const { result } = renderCreateWorkspaceHook();

    await result.current.createWorkspace(CREATE_ARGS);
    expect(createWorkspaceAgent).toHaveBeenCalled();

    window.location.hash = "#/ws/ws_1/agent/their_own_agent";
    resolveAgentCreate({ data: { id: "agent_1" } } as unknown as Awaited<ReturnType<typeof createWorkspaceAgent>>);

    // The analytics capture fires after the response and before the focus
    // guard — once it lands, the continuation has run through the guard.
    const { posthog } = await import("posthog-js");
    await waitFor(() => expect(posthog.capture).toHaveBeenCalled());
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
