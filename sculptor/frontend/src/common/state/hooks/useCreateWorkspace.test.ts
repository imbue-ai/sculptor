import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import { EffortLevel, LlmModel, WorkspaceInitializationStrategy } from "~/api";
import { encodeRegisteredAgentType, type StoredAgentType } from "~/common/state/atoms/agentTabs.ts";

import { useCreateWorkspace } from "./useCreateWorkspace.ts";

// Stub the two create endpoints so we can inspect exactly what the hook sends
// for each agent type (the gating between Claude / pi / terminal is the unit
// under test).
const { mockCreateWorkspaceV2, mockCreateWorkspaceAgent } = vi.hoisted(() => ({
  mockCreateWorkspaceV2: vi.fn(),
  mockCreateWorkspaceAgent: vi.fn(),
}));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return {
    ...actual,
    createWorkspaceV2: mockCreateWorkspaceV2,
    createWorkspaceAgent: mockCreateWorkspaceAgent,
  };
});

vi.mock("~/common/NavigateUtils.ts", () => ({
  useImbueNavigate: (): Record<string, unknown> => ({ navigateToAgent: vi.fn(), navigateToWorkspace: vi.fn() }),
}));

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const makeWrapper =
  (store: ReturnType<typeof createStore>) =>
  ({ children }: { children: ReactNode }): ReactElement =>
    createElement(Provider, { store }, children);

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
  mockCreateWorkspaceAgent.mock.calls[0][0].body as Record<string, unknown>;

beforeEach(() => {
  vi.clearAllMocks();
  mockCreateWorkspaceV2.mockResolvedValue({ data: { objectId: "workspace-1" } });
  mockCreateWorkspaceAgent.mockResolvedValue({ data: { id: "agent-1" } });
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useCreateWorkspace agent-type gating", () => {
  it("sends prompt, model, effort, fast, and plan for a Claude agent", async () => {
    const store = createStore();
    const { result } = renderHook(() => useCreateWorkspace(), { wrapper: makeWrapper(store) });

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
    const store = createStore();
    const { result } = renderHook(() => useCreateWorkspace(), { wrapper: makeWrapper(store) });

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
    const store = createStore();
    const { result } = renderHook(() => useCreateWorkspace(), { wrapper: makeWrapper(store) });

    await result.current.createWorkspace(baseArgs({ agentTypeValue: "pi" as StoredAgentType, prompt: "   " }));

    const body = getAgentRequestBody();
    expect(body.agentType).toBe("pi");
    expect(body.prompt).toBeUndefined();
    // No prompt → the backend does not require a model, so pi starts on its own default.
    expect(body.model).toBeUndefined();
  });

  it("never sends a prompt or model for a terminal agent", async () => {
    const store = createStore();
    const { result } = renderHook(() => useCreateWorkspace(), { wrapper: makeWrapper(store) });

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
    const store = createStore();
    const { result } = renderHook(() => useCreateWorkspace(), { wrapper: makeWrapper(store) });

    const registration: api.TerminalAgentRegistration = {
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
    const store = createStore();
    const { result } = renderHook(() => useCreateWorkspace(), { wrapper: makeWrapper(store) });

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
