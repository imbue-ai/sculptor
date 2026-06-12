import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomActionGroup } from "~/api";

import { GroupContextMenu } from "./GroupContextMenu";

const createGroup = (overrides: Partial<CustomActionGroup> = {}): CustomActionGroup => ({
  id: "group-1",
  name: "Test Group",
  order: 0,
  ...overrides,
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const renderContextMenu = (props: Partial<React.ComponentProps<typeof GroupContextMenu>> = {}): RenderResult => {
  const defaultProps: React.ComponentProps<typeof GroupContextMenu> = {
    group: createGroup(),
    children: <div data-testid="trigger">Group Name</div>,
    onRename: vi.fn(),
    onDelete: vi.fn(),
    ...props,
  };
  return render(<GroupContextMenu {...defaultProps} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("GroupContextMenu", () => {
  describe("rendering", () => {
    it("renders the trigger content", () => {
      renderContextMenu();
      expect(screen.getByTestId("trigger")).toBeInTheDocument();
    });

    it("shows menu items on right-click", () => {
      renderContextMenu();
      fireEvent.contextMenu(screen.getByTestId("trigger"));
      expect(screen.getByText("Rename group")).toBeInTheDocument();
      expect(screen.getByText("Delete group")).toBeInTheDocument();
    });
  });

  describe("interactions", () => {
    it("calls onRename with the group when Rename group is selected", () => {
      const onRename = vi.fn();
      const group = createGroup({ id: "g1", name: "My Group" });
      renderContextMenu({ group, onRename });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      fireEvent.click(screen.getByText("Rename group"));

      expect(onRename).toHaveBeenCalledWith(group);
    });

    it("calls onDelete with the group when Delete group is selected", () => {
      const onDelete = vi.fn();
      const group = createGroup({ id: "g2", name: "Doomed Group" });
      renderContextMenu({ group, onDelete });

      fireEvent.contextMenu(screen.getByTestId("trigger"));
      fireEvent.click(screen.getByText("Delete group"));

      expect(onDelete).toHaveBeenCalledWith(group);
    });
  });

  describe("menu structure", () => {
    it("has a separator between rename and delete", () => {
      renderContextMenu();
      fireEvent.contextMenu(screen.getByTestId("trigger"));

      // Radix ContextMenu.Separator renders a role="separator" element
      const separator = screen.getByRole("separator");
      expect(separator).toBeInTheDocument();
    });
  });
});
