import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CodingAgentTaskView, PrStatusInfo, UserConfig } from "~/api";
import { ElementIds, LlmModel, TaskStatus } from "~/api";
import { reusableTabTarget } from "~/common/reusableTabTarget.ts";
import { agentAtomFamily, agentIdsAtom } from "~/common/state/atoms/agents.ts";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus.ts";
import { commitPromptSendFailedToastAtom } from "~/common/state/atoms/toasts.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";
import { workspaceLayoutFamily } from "~/pages/workspace/layout/atoms/section.ts";
import { EMPTY_WORKSPACE_LAYOUT } from "~/pages/workspace/layout/persistence/snapshot.ts";
import { makeAgentPanelId } from "~/pages/workspace/layout/registry/dynamicPanels.tsx";

import { PrButton } from "./PrButton.tsx";

// posthog isn't initialised in tests; the button captures an analytics event
// on click, so stub it to a no-op.
vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

// The send API hits the backend; stub it so the prompt's destination can be
// asserted deterministically.
const { sendMessagesMock } = vi.hoisted(() => ({ sendMessagesMock: vi.fn() }));
vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, sendWorkspaceAgentMessages: sendMessagesMock };
});

const WORKSPACE_ID = "ws-pr-1";
const PR_URL = "https://github.com/imbue-ai/sculptor/pull/392";

const storeWith = (status: PrStatusInfo): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(prStatusAtomFamily(WORKSPACE_ID), status);
  return store;
};

const prStatus = (overrides: Partial<PrStatusInfo>): PrStatusInfo => ({
  workspaceId: WORKSPACE_ID,
  prState: "open",
  prIid: 392,
  prWebUrl: PR_URL,
  ...overrides,
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  sendMessagesMock.mockReset();
  localStorage.clear();
});

describe("PrButton opens PRs in a reusable browser tab", () => {
  it("opens an open PR in its stable named tab, not _blank", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch="origin/main" gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "open" })),
    });

    fireEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_OPEN));

    expect(open).toHaveBeenCalledWith(PR_URL, reusableTabTarget(PR_URL));
    expect(open).not.toHaveBeenCalledWith(PR_URL, "_blank");
  });

  it("opens a merged PR in the same reusable tab as the open PR", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch="origin/main" gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "merged" })),
    });

    fireEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_MERGED));

    expect(open).toHaveBeenCalledWith(PR_URL, reusableTabTarget(PR_URL));
  });
});

describe("PrButton without a target branch", () => {
  it("disables Create PR", () => {
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch={null} gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "none" })),
    });

    expect(screen.getByTestId(ElementIds.PR_BUTTON_CREATE)).toBeDisabled();
  });
});

describe("PrButton offers to adopt an existing PR only when it targets another branch", () => {
  const renderWithNoPr = (targetBranch: string, mismatchedPrTargetBranch: string): void => {
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch={targetBranch} gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "none", mismatchedPrIid: 7, mismatchedPrTargetBranch })),
    });
  };

  it("offers the existing PR when it targets a different branch", () => {
    renderWithNoPr("origin/main", "release");

    expect(screen.getByTestId(ElementIds.PR_BUTTON_ASSIGN)).toBeTruthy();
  });

  it("offers to create a PR when the existing PR targets the remote target's branch", () => {
    renderWithNoPr("origin/main", "main");

    expect(screen.getByTestId(ElementIds.PR_BUTTON_CREATE)).toBeTruthy();
  });

  it("keeps offering the reported PR when the target is a local branch with a slash", () => {
    // PR status matches `feature/login` as `login`, so it reports the PR based
    // on `feature/login` as a mismatch. Answering that with "Create PR" would
    // hide the PR that already exists.
    renderWithNoPr("feature/login", "feature/login");

    expect(screen.getByTestId(ElementIds.PR_BUTTON_ASSIGN)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.PR_BUTTON_CREATE)).toBeNull();
  });
});

const AGENT_ID = "agent-pr-1";
const PR_PROMPT = "Open a pull request";

type AgentHarness = {
  supportsChatInterface: boolean;
  acceptsAutomatedPrompts: boolean;
  status: TaskStatus;
};

const CHAT_AGENT: AgentHarness = {
  supportsChatInterface: true,
  acceptsAutomatedPrompts: false,
  status: TaskStatus.READY,
};

const storeWithAgent = (inputs: {
  status: PrStatusInfo;
  harness: AgentHarness;
  activeCenterPanel: "agent" | "changes";
}): ReturnType<typeof createStore> => {
  const store = storeWith(inputs.status);
  store.set(userConfigAtom, { prCreationPrompt: PR_PROMPT } as unknown as UserConfig);
  store.set(agentAtomFamily(AGENT_ID), {
    id: AGENT_ID,
    workspaceId: WORKSPACE_ID,
    projectId: "proj-1",
    status: inputs.harness.status,
    model: LlmModel.CLAUDE_4_SONNET,
    harnessCapabilities: { supportsChatInterface: inputs.harness.supportsChatInterface },
    acceptsAutomatedPrompts: inputs.harness.acceptsAutomatedPrompts,
    isDeleted: false,
  } as unknown as CodingAgentTaskView);
  store.set(agentIdsAtom, [AGENT_ID]);
  store.set(workspaceLayoutFamily(WORKSPACE_ID), {
    ...EMPTY_WORKSPACE_LAYOUT,
    placement: { [makeAgentPanelId(AGENT_ID)]: "center", changes: "center" },
    order: { center: [makeAgentPanelId(AGENT_ID), "changes"] },
    activePanel: { center: inputs.activeCenterPanel === "agent" ? makeAgentPanelId(AGENT_ID) : "changes" },
  });
  return store;
};

const renderPrButton = (store: ReturnType<typeof createStore>): void => {
  renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch="origin/main" gitProvider="github" />, {
    store,
  });
};

const openAssignPrMenu = async (): Promise<void> => {
  await userEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_ASSIGN));
  await screen.findByRole("menu");
};

const NO_PR = prStatus({ prState: "none" });
const PR_ON_OTHER_TARGET = prStatus({ prState: "none", mismatchedPrIid: 7, mismatchedPrTargetBranch: "release" });

describe("PrButton sends the create-PR prompt to the workspace's agent", () => {
  const EXPECTED_SEND = {
    path: { workspace_id: WORKSPACE_ID, agent_id: AGENT_ID },
    body: {
      message: "Open a pull request\n\nTarget the pull request against `origin/main`.",
      model: LlmModel.CLAUDE_4_SONNET,
    },
  };

  // The agent's chat panel is open but the Changes panel is the active center
  // tab, so no chat panel is mounted and none has registered chat actions.
  const storeWithAgentBehindChangesTab = (status: PrStatusInfo): ReturnType<typeof createStore> =>
    storeWithAgent({ status, harness: CHAT_AGENT, activeCenterPanel: "changes" });

  it("sends from Create PR while no agent panel is mounted", () => {
    renderPrButton(storeWithAgentBehindChangesTab(NO_PR));

    fireEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_CREATE));

    expect(sendMessagesMock).toHaveBeenCalledTimes(1);
    expect(sendMessagesMock).toHaveBeenCalledWith(EXPECTED_SEND);
  });

  // The app shell renders this atom as a toast, the same one every other
  // Create PR and Commit entry point raises on a failed send.
  it("raises the send-failed toast when Create PR's send fails", async () => {
    const store = storeWithAgentBehindChangesTab(NO_PR);
    renderPrButton(store);
    sendMessagesMock.mockRejectedValueOnce(new Error("network down"));

    fireEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_CREATE));

    await waitFor(() =>
      expect(store.get(commitPromptSendFailedToastAtom)).toMatchObject({ title: "Couldn't send pull request prompt" }),
    );
  });

  it("sends from the Assign PR menu's create item while no agent panel is mounted", async () => {
    renderPrButton(storeWithAgentBehindChangesTab(PR_ON_OTHER_TARGET));

    await openAssignPrMenu();
    await userEvent.click(screen.getByRole("menuitem", { name: /Create PR/ }));

    expect(sendMessagesMock).toHaveBeenCalledTimes(1);
    expect(sendMessagesMock).toHaveBeenCalledWith(EXPECTED_SEND);
  });
});

describe("PrButton disables its create controls while the workspace's current agent cannot take a prompt", () => {
  const PLAIN_TERMINAL: AgentHarness = {
    supportsChatInterface: false,
    acceptsAutomatedPrompts: false,
    status: TaskStatus.READY,
  };
  const BUSY_PROMPT_CAPABLE_TERMINAL: AgentHarness = {
    supportsChatInterface: false,
    acceptsAutomatedPrompts: true,
    status: TaskStatus.RUNNING,
  };

  it.each([
    { label: "a plain terminal is the visible agent", harness: PLAIN_TERMINAL },
    { label: "the visible terminal agent is not at its prompt", harness: BUSY_PROMPT_CAPABLE_TERMINAL },
  ])("disables Create PR when $label", ({ harness }) => {
    renderPrButton(storeWithAgent({ status: NO_PR, harness, activeCenterPanel: "agent" }));

    const createButton = screen.getByTestId(ElementIds.PR_BUTTON_CREATE);
    expect(createButton).toBeDisabled();
    fireEvent.click(createButton);
    expect(sendMessagesMock).not.toHaveBeenCalled();
  });

  it("disables only the Assign PR menu's create item, keeping the switch-target item", async () => {
    renderPrButton(storeWithAgent({ status: PR_ON_OTHER_TARGET, harness: PLAIN_TERMINAL, activeCenterPanel: "agent" }));

    await openAssignPrMenu();

    expect(screen.getByRole("menuitem", { name: /Create PR/ })).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("menuitem", { name: /switch target/ })).not.toHaveAttribute("aria-disabled");
  });

  it("enables Create PR while a chat agent is the visible agent", () => {
    renderPrButton(storeWithAgent({ status: NO_PR, harness: CHAT_AGENT, activeCenterPanel: "agent" }));

    expect(screen.getByTestId(ElementIds.PR_BUTTON_CREATE)).toBeEnabled();
  });
});
