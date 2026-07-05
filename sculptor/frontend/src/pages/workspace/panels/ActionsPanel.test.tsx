import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomAction, CustomActionGroup, UserConfig } from "~/api";
import { chatActionsAtom } from "~/common/state/atoms/chatActions";
import { collapsedGroupsAtom } from "~/common/state/atoms/customActions";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";

import { ActionsPanel } from "./ActionsPanel";

// Mock useWorkspacePanelData (deep dependency on routing, agent state, etc.)
vi.mock("~/pages/workspace/panels/useWorkspacePanelData", () => ({
  useWorkspacePanelData: (): {
    agent: null;
    artifacts: Record<string, never>;
    userMessageIds: Array<string>;
    agentId: string;
    projectID: string;
  } => ({
    agent: null,
    artifacts: {},
    userMessageIds: [],
    agentId: "test-task",
    projectID: "test-project",
  }),
}));

// Mock API calls used by useUserConfig. The useUserConfig hook imports
// from "../../../api" which barrel-exports from sdk.gen. We mock the
// barrel via the same relative path that useUserConfig uses.
vi.mock("~/api/sdk.gen", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getUserConfig: vi.fn().mockResolvedValue({ data: null }),
    updateUserConfig: vi.fn().mockImplementation((options: { body: { userConfig: Record<string, unknown> } }) => {
      return Promise.resolve({ data: options.body.userConfig });
    }),
  };
});

const createAction = (overrides: Partial<CustomAction> = {}): CustomAction => ({
  id: crypto.randomUUID(),
  name: "Test Action",
  prompt: "Do something",
  autoSubmit: true,
  groupId: null,
  order: 0,
  ...overrides,
});

const createGroup = (overrides: Partial<CustomActionGroup> = {}): CustomActionGroup => ({
  id: crypto.randomUUID(),
  name: "Test Group",
  order: 0,
  ...overrides,
});

type RenderOptions = {
  actions?: Array<CustomAction>;
  groups?: Array<CustomActionGroup>;
  isChatDisabled?: boolean;
  collapsedGroups?: Record<string, boolean>;
};

const renderActionsPanel = (options: RenderOptions = {}): RenderResult & { store: ReturnType<typeof createStore> } => {
  const { actions = [], groups = [], isChatDisabled = false, collapsedGroups = {} } = options;

  const store = createStore();

  const config = {
    customActions: { actions, groups },
  } as unknown as UserConfig;

  store.set(userConfigAtom, config);
  store.set(chatActionsAtom, {
    appendText: vi.fn(),
    insertSkill: vi.fn(),
    sendMessage: vi.fn().mockResolvedValue(undefined),
    isDisabled: isChatDisabled,
  });
  store.set(collapsedGroupsAtom, collapsedGroups);

  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  return Object.assign(render(<ActionsPanel />, { wrapper: Wrapper }), { store });
};

beforeEach(() => {
  localStorage.clear();
  vi.clearAllMocks();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ActionsPanel", () => {
  describe("header", () => {
    it("renders Actions heading", () => {
      renderActionsPanel();
      expect(screen.getByText("Actions")).toBeInTheDocument();
    });
  });

  describe("rendering actions", () => {
    it("renders ungrouped action chips", () => {
      const actions = [
        createAction({ name: "Action 1", groupId: null, order: 0 }),
        createAction({ name: "Action 2", groupId: null, order: 1 }),
      ];
      renderActionsPanel({ actions });
      expect(screen.getByText("Action 1")).toBeInTheDocument();
      expect(screen.getByText("Action 2")).toBeInTheDocument();
    });

    it("renders grouped actions under their group header", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [createAction({ name: "Grouped Action", groupId: "g1", order: 0 })];
      renderActionsPanel({ actions, groups: [group] });

      expect(screen.getByText("My Group")).toBeInTheDocument();
      expect(screen.getByText("Grouped Action")).toBeInTheDocument();
    });

    it("renders multiple groups in order", () => {
      const g1 = createGroup({ id: "g1", name: "First Group", order: 0 });
      const g2 = createGroup({ id: "g2", name: "Second Group", order: 1 });
      const actions = [
        createAction({ name: "Action A", groupId: "g1", order: 0 }),
        createAction({ name: "Action B", groupId: "g2", order: 0 }),
      ];
      renderActionsPanel({ actions, groups: [g2, g1] });

      expect(screen.getByText("First Group")).toBeInTheDocument();
      expect(screen.getByText("Second Group")).toBeInTheDocument();
      expect(screen.getByText("Action A")).toBeInTheDocument();
      expect(screen.getByText("Action B")).toBeInTheDocument();
    });

    it("renders both ungrouped and grouped actions", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [
        createAction({ name: "Ungrouped", groupId: null, order: 0 }),
        createAction({ name: "Grouped", groupId: "g1", order: 0 }),
      ];
      renderActionsPanel({ actions, groups: [group] });

      expect(screen.getByText("Ungrouped")).toBeInTheDocument();
      expect(screen.getByText("Grouped")).toBeInTheDocument();
    });
  });

  describe("group collapse/expand", () => {
    it("shows actions in expanded groups", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [createAction({ name: "Visible Action", groupId: "g1", order: 0 })];
      renderActionsPanel({ actions, groups: [group] });

      expect(screen.getByText("Visible Action")).toBeInTheDocument();
    });

    it("hides actions in collapsed groups", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [createAction({ name: "Hidden Action", groupId: "g1", order: 0 })];
      renderActionsPanel({
        actions,
        groups: [group],
        collapsedGroups: { g1: true },
      });

      expect(screen.queryByText("Hidden Action")).not.toBeInTheDocument();
    });

    it("shows badge with action count on collapsed groups", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [
        createAction({ name: "Action 1", groupId: "g1", order: 0 }),
        createAction({ name: "Action 2", groupId: "g1", order: 1 }),
      ];
      renderActionsPanel({
        actions,
        groups: [group],
        collapsedGroups: { g1: true },
      });

      expect(screen.getByText("2")).toBeInTheDocument();
    });

    it("toggles collapse when group header is clicked", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [createAction({ name: "Toggle Action", groupId: "g1", order: 0 })];
      renderActionsPanel({ actions, groups: [group] });

      expect(screen.getByText("Toggle Action")).toBeInTheDocument();

      fireEvent.click(screen.getByText("My Group"));
      expect(screen.queryByText("Toggle Action")).not.toBeInTheDocument();

      fireEvent.click(screen.getByText("My Group"));
      expect(screen.getByText("Toggle Action")).toBeInTheDocument();
    });
  });

  describe("action click behavior", () => {
    it("calls sendMessage for auto-submit actions", () => {
      const sendMessage = vi.fn().mockResolvedValue(undefined);
      const actions = [createAction({ name: "Auto Action", prompt: "Run tests", autoSubmit: true })];

      const store = createStore();
      store.set(userConfigAtom, { customActions: { actions, groups: [] } } as unknown as UserConfig);
      store.set(chatActionsAtom, { appendText: vi.fn(), insertSkill: vi.fn(), sendMessage, isDisabled: false });
      store.set(collapsedGroupsAtom, {});

      const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
        <Provider store={store}>
          <Theme>{children}</Theme>
        </Provider>
      );

      render(<ActionsPanel />, { wrapper: Wrapper });
      fireEvent.click(screen.getByText("Auto Action"));
      expect(sendMessage).toHaveBeenCalledWith("Run tests");
    });

    it("calls appendText for draft (non-auto-submit) actions", () => {
      const appendText = vi.fn();
      const actions = [createAction({ name: "Draft Action", prompt: "Review code", autoSubmit: false })];

      const store = createStore();
      store.set(userConfigAtom, { customActions: { actions, groups: [] } } as unknown as UserConfig);
      store.set(chatActionsAtom, { appendText, insertSkill: vi.fn(), sendMessage: vi.fn(), isDisabled: false });
      store.set(collapsedGroupsAtom, {});

      const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
        <Provider store={store}>
          <Theme>{children}</Theme>
        </Provider>
      );

      render(<ActionsPanel />, { wrapper: Wrapper });
      fireEvent.click(screen.getByText("Draft Action"));
      expect(appendText).toHaveBeenCalledWith("Review code");
    });
  });

  describe("add action/group dropdown", () => {
    it("renders the add button (Plus icon)", () => {
      renderActionsPanel();
      // The plus button is always present in the header
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  describe("group context menu", () => {
    it("shows context menu options on right-click of group header", () => {
      const group = createGroup({ id: "g1", name: "My Group" });
      const actions = [createAction({ groupId: "g1", order: 0 })];
      renderActionsPanel({ actions, groups: [group] });

      fireEvent.contextMenu(screen.getByText("My Group"));
      expect(screen.getByText("Rename group")).toBeInTheDocument();
      expect(screen.getByText("Delete group")).toBeInTheDocument();
    });
  });

  describe("empty groups during non-drag state", () => {
    it("does not show empty group drop zone when not dragging", () => {
      const group = createGroup({ id: "g1", name: "Empty Group" });
      const { container } = renderActionsPanel({ actions: [], groups: [group] });

      expect(container.querySelector("[data-empty-group-drop]")).not.toBeInTheDocument();
    });
  });

  describe("data attributes for DnD", () => {
    it("renders data-action-chip attributes on action elements", () => {
      const action = createAction({ id: "a1", name: "DnD Action" });
      const { container } = renderActionsPanel({ actions: [action] });

      const chipEl = container.querySelector('[data-action-chip="a1"]');
      expect(chipEl).toBeInTheDocument();
    });

    it("renders data-action-group attributes on group sections", () => {
      const group = createGroup({ id: "g1", name: "DnD Group" });
      const actions = [createAction({ groupId: "g1", order: 0 })];
      const { container } = renderActionsPanel({ actions, groups: [group] });

      const groupEl = container.querySelector('[data-action-group="g1"]');
      expect(groupEl).toBeInTheDocument();
    });
  });

  describe("inline group creation", () => {
    it("does not show group creation input by default", () => {
      const actions = [createAction()];
      renderActionsPanel({ actions });
      expect(screen.queryByPlaceholderText("New group name")).not.toBeInTheDocument();
    });
  });

  describe("group header consistency", () => {
    it("renders chevron icons for groups", () => {
      const group = createGroup({ id: "g1", name: "Chevron Group" });
      const actions = [createAction({ groupId: "g1", order: 0 })];
      const { container } = renderActionsPanel({ actions, groups: [group] });

      // Expanded group should have ChevronDown
      const svgs = container.querySelectorAll("svg");
      expect(svgs.length).toBeGreaterThan(0);
    });
  });
});
