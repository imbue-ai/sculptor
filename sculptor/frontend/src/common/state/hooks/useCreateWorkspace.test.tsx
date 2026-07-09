import { cleanup, renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as ApiModule from "~/api";
import { createWorkspaceAgent, createWorkspaceV2, EffortLevel, LlmModel, WorkspaceInitializationStrategy } from "~/api";
import type * as NavigateUtilsModule from "~/common/NavigateUtils.ts";
import { encodeRegisteredAgentType, type StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
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

    expect(createResult).toEqual({ ok: true, workspaceId: "ws_1" });
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

    expect(createResult).toEqual({ ok: true, workspaceId: "ws_1" });
    expect(navigateToWorkspace).toHaveBeenCalledWith("ws_1");
    await waitFor(() => expect(store.get(createAgentErrorToastAtom)).not.toBeNull());
    expect(store.get(createAgentErrorToastAtom)).toMatchObject({ title: "Failed to create agent" });
    expect(navigateToAgent).not.toHaveBeenCalled();
  });
});

// Request-body gating between Claude / pi / terminal / registered agents. The
// agent create is fired in the background, but its request body is built and
// the call issued synchronously within createWorkspace, so the mock's calls
// are inspectable as soon as createWorkspace resolves.
describe("useCreateWorkspace agent-type gating", () => {
  type CreateArgs = Parameters<ReturnType<typeof useCreateWorkspace>["createWorkspace"]>[0];

  const baseArgs = (overrides: Partial<CreateArgs>): CreateArgs => ({
    projectId: "project-1",
    workspaceName: "My workspace",
    prompt: "",
    mode: WorkspaceInitializationStrategy.WORKTREE,
    sourceBranch: "main",
    branchName: "feature/branch",
    agentTypeValue: "claude" as StoredAgentType,
    registrations: [],
    defaultModel: LlmModel.CLAUDE_4_OPUS,
    effort: EffortLevel.HIGH,
    fastMode: false,
    enterPlanMode: false,
    ...overrides,
  });

  const getAgentRequestBody = (): Record<string, unknown> =>
    vi.mocked(createWorkspaceAgent).mock.calls[0][0].body as unknown as Record<string, unknown>;

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(createWorkspaceV2).mockResolvedValue({
      data: { objectId: "workspace-1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceV2>>);
    vi.mocked(createWorkspaceAgent).mockResolvedValue({
      data: { id: "agent-1" },
    } as unknown as Awaited<ReturnType<typeof createWorkspaceAgent>>);
  });

  afterEach(() => {
    cleanup();
  });

  it("sends prompt, model, effort, fast, and plan for a Claude agent", async () => {
    const { result } = renderCreateWorkspaceHook();

    await result.current.createWorkspace(
      baseArgs({ agentTypeValue: "claude" as StoredAgentType, prompt: "do a thing", enterPlanMode: true }),
    );

    const body = getAgentRequestBody();
    expect(body.agentType).toBe("claude");
    expect(body.prompt).toBe("do a thing");
    expect(body.model).toBe(LlmModel.CLAUDE_4_OPUS);
    expect(body.effort).toBe(EffortLevel.HIGH);
    expect(body.fastMode).toBe(false);
    expect(body.enterPlanMode).toBe(true);
  });

  it("sends the prompt (and a placeholder model) for a pi agent, but omits effort/fast/plan", async () => {
    const { result } = renderCreateWorkspaceHook();

    await result.current.createWorkspace(
      baseArgs({ agentTypeValue: "pi" as StoredAgentType, prompt: "help me get started", enterPlanMode: true }),
    );

    const body = getAgentRequestBody();
    expect(body.agentType).toBe("pi");
    // The prompt the user typed must reach pi, not be silently dropped.
    expect(body.prompt).toBe("help me get started");
    // pi ignores the model (it picks from its own in-task catalog), but the
    // backend requires one alongside a prompt, so a placeholder default rides along.
    expect(body.model).toBe(LlmModel.CLAUDE_4_OPUS);
    // These Claude-only per-prompt settings do not apply to a pi create.
    expect(body.effort).toBeUndefined();
    expect(body.fastMode).toBeUndefined();
    expect(body.enterPlanMode).toBeUndefined();
  });

  it("omits the prompt and model for a pi agent when no prompt was typed", async () => {
    const { result } = renderCreateWorkspaceHook();

    await result.current.createWorkspace(baseArgs({ agentTypeValue: "pi" as StoredAgentType, prompt: "   " }));

    const body = getAgentRequestBody();
    expect(body.agentType).toBe("pi");
    expect(body.prompt).toBeUndefined();
    // No prompt → the backend does not require a model, so pi starts on its own default.
    expect(body.model).toBeUndefined();
  });

  it("never sends a prompt or model for a terminal agent", async () => {
    const { result } = renderCreateWorkspaceHook();

    await result.current.createWorkspace(
      baseArgs({ agentTypeValue: "terminal" as StoredAgentType, prompt: "this should be ignored" }),
    );

    const body = getAgentRequestBody();
    expect(body.agentType).toBe("terminal");
    // The backend rejects a prompt for terminal/registered agents (422), so it must never be sent.
    expect(body.prompt).toBeUndefined();
    expect(body.model).toBeUndefined();
  });

  it("omits the prompt and model for a registered agent whose registration exists", async () => {
    const { result } = renderCreateWorkspaceHook();

    const registration: ApiModule.TerminalAgentRegistration = {
      registrationId: "reg-1",
      displayName: "My Agent",
      launchCommand: "my-agent",
    };
    await result.current.createWorkspace(
      baseArgs({
        agentTypeValue: encodeRegisteredAgentType("reg-1"),
        registrations: [registration],
        prompt: "this should be ignored",
      }),
    );

    const body = getAgentRequestBody();
    // A registered agent is terminal-like: the backend rejects a prompt for it,
    // and it carries no model / per-prompt settings.
    expect(body.agentType).toBe("registered");
    expect(body.registrationId).toBe("reg-1");
    expect(body.prompt).toBeUndefined();
    expect(body.model).toBeUndefined();
    expect(body.effort).toBeUndefined();
    expect(body.fastMode).toBeUndefined();
    expect(body.enterPlanMode).toBeUndefined();
  });

  it("falls back to Claude (prompt + model + settings) when the registered agent's registration was deleted", async () => {
    const { result } = renderCreateWorkspaceHook();

    // The stored type references a registration that no longer exists, so
    // resolveEffectiveAgentType falls back to Claude — which must send the prompt
    // and settings, not silently drop them.
    await result.current.createWorkspace(
      baseArgs({
        agentTypeValue: encodeRegisteredAgentType("reg-deleted"),
        registrations: [],
        prompt: "help me get started",
        enterPlanMode: true,
      }),
    );

    const body = getAgentRequestBody();
    expect(body.agentType).toBe("claude");
    expect(body.registrationId).toBeUndefined();
    expect(body.prompt).toBe("help me get started");
    expect(body.model).toBe(LlmModel.CLAUDE_4_OPUS);
    expect(body.effort).toBe(EffortLevel.HIGH);
    expect(body.fastMode).toBe(false);
    expect(body.enterPlanMode).toBe(true);
  });
});
