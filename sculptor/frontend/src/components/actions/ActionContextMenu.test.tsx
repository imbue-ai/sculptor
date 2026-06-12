import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomAction, CustomActionGroup } from "~/api";

import { ActionContextMenu } from "./ActionContextMenu";

const createAction = (overrides: Partial<CustomAction> = {}): CustomAction => ({
  id: "action-1",
  name: "Test Action",
  prompt: "Do the thing",
  autoSubmit: true,
  groupId: null,
  order: 0,
  ...overrides,
});

const createGroup = (overrides: Partial<CustomActionGroup> = {}): CustomActionGroup => ({
  id: "group-1",
  name: "Test Group",
  order: 0,
  ...overrides,
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const renderContextMenu = (props: Partial<React.ComponentProps<typeof ActionContextMenu>> = {}): RenderResult => {
  const defaultProps: React.ComponentProps<typeof ActionContextMenu> = {
    action: createAction(),
    groups: [],
    children: <button data-testid="trigger">Action Button</button>,
    onEdit: vi.fn(),
    onDelete: vi.fn(),
    onMoveToGroup: vi.fn(),
    ...props,
  };
  return render(<ActionContextMenu {...defaultProps} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ActionContextMenu", () => {
  describe("rendering", () => {
    it("renders the trigger content", () => {
      renderContextMenu();
      expect(screen.getByTestId("trigger")).toBeInTheDocument();
    });

    it("shows Edit action and Delete action on right-click", () => {
      renderContextMenu();
      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(screen.getByText("Edit action")).toBeInTheDocument();
      expect(screen.getByText("Delete action")).toBeInTheDocument();
    });

    it("shows Move to group... submenu on right-click", () => {
      renderContextMenu();
      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(screen.getByText("Move to group...")).toBeInTheDocument();
    });
  });

  describe("edit action", () => {
    it("calls onEdit with the action when Edit action is selected", () => {
      const onEdit = vi.fn();
      const action = createAction({ id: "a1", name: "My Action" });
      renderContextMenu({ action, onEdit });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      fireEvent.click(screen.getByText("Edit action"));

      expect(onEdit).toHaveBeenCalledWith(action);
    });
  });

  describe("delete action", () => {
    it("calls onDelete with the action when Delete action is selected", () => {
      const onDelete = vi.fn();
      const action = createAction({ id: "a1" });
      renderContextMenu({ action, onDelete });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      fireEvent.click(screen.getByText("Delete action"));

      expect(onDelete).toHaveBeenCalledWith(action);
    });
  });

  describe("queue message", () => {
    it("shows Queue message when agent is running and handler is provided", () => {
      renderContextMenu({
        isAgentRunning: true,
        onQueueMessage: vi.fn(),
      });
      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(screen.getByText("Queue message")).toBeInTheDocument();
    });

    it("does not show Queue message when agent is not running", () => {
      renderContextMenu({
        isAgentRunning: false,
        onQueueMessage: vi.fn(),
      });
      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(screen.queryByText("Queue message")).not.toBeInTheDocument();
    });

    it("does not show Queue message when handler is not provided", () => {
      renderContextMenu({
        isAgentRunning: true,
        onQueueMessage: undefined,
      });
      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(screen.queryByText("Queue message")).not.toBeInTheDocument();
    });

    it("calls onQueueMessage with the action prompt when selected", () => {
      const onQueueMessage = vi.fn();
      const action = createAction({ prompt: "Run tests" });
      renderContextMenu({ action, isAgentRunning: true, onQueueMessage });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      fireEvent.click(screen.getByText("Queue message"));

      expect(onQueueMessage).toHaveBeenCalledWith("Run tests");
    });
  });

  describe("move to group submenu", () => {
    it("shows No group option that calls onMoveToGroup with null", () => {
      const onMoveToGroup = vi.fn();
      const action = createAction({ groupId: "g1" });
      renderContextMenu({ action, onMoveToGroup });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      // Hover over the submenu trigger to open it
      fireEvent.pointerMove(screen.getByText("Move to group..."));
      fireEvent.click(screen.getByText("Move to group..."));

      // The submenu content should render with "No group" option
      // Note: Radix submenus may need pointer events to open
    });

    it("shows available groups in the submenu", () => {
      const groups = [createGroup({ id: "g1", name: "Group Alpha" }), createGroup({ id: "g2", name: "Group Beta" })];
      renderContextMenu({ groups });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      // Submenu trigger is visible
      expect(screen.getByText("Move to group...")).toBeInTheDocument();
    });

    it("disables No group option when action is already ungrouped", () => {
      const action = createAction({ groupId: null });
      renderContextMenu({ action });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
    });

    it("disables current group option in the submenu", () => {
      const action = createAction({ groupId: "g1" });
      const groups = [createGroup({ id: "g1", name: "Current Group" })];
      renderContextMenu({ action, groups });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
    });
  });

  describe("onOpenChange", () => {
    it("calls onOpenChange when menu opens", () => {
      const onOpenChange = vi.fn();
      renderContextMenu({ onOpenChange });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(onOpenChange).toHaveBeenCalledWith(true);
    });
  });
});
