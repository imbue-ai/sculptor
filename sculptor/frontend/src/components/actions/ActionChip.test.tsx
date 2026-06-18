import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomAction, CustomActionGroup } from "~/api";

import { ActionChip } from "./ActionChip";

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

const renderChip = (props: Partial<React.ComponentProps<typeof ActionChip>> = {}): RenderResult => {
  const defaultProps: React.ComponentProps<typeof ActionChip> = {
    action: createAction(),
    onClick: vi.fn(),
    ...props,
  };
  return render(<ActionChip {...defaultProps} />, { wrapper: Wrapper });
};

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ActionChip", () => {
  describe("rendering", () => {
    it("renders the action name", () => {
      renderChip({ action: createAction({ name: "My Action" }) });
      expect(screen.getByText("My Action")).toBeInTheDocument();
    });

    it("renders as a button", () => {
      renderChip();
      expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("renders Zap icon for auto-submit actions", () => {
      const { container } = renderChip({ action: createAction({ autoSubmit: true }) });
      // Zap icon is from lucide-react - it renders as an SVG with the class
      const icon = container.querySelector(".autoSubmitIcon");
      expect(icon).toBeInTheDocument();
    });

    it("renders Pencil icon for draft (non-auto-submit) actions", () => {
      const { container } = renderChip({ action: createAction({ autoSubmit: false }) });
      const icon = container.querySelector(".draftIcon");
      expect(icon).toBeInTheDocument();
    });

    it("defaults to auto-submit when autoSubmit is undefined", () => {
      const action = createAction();
      delete (action as Record<string, unknown>)["autoSubmit"];
      const { container } = renderChip({ action });
      const icon = container.querySelector(".autoSubmitIcon");
      expect(icon).toBeInTheDocument();
    });
  });

  describe("click behavior", () => {
    it("calls onClick when clicked", () => {
      const onClick = vi.fn();
      renderChip({ onClick });
      fireEvent.click(screen.getByRole("button"));
      expect(onClick).toHaveBeenCalledTimes(1);
    });

    it("does not call onClick when disabled", () => {
      const onClick = vi.fn();
      renderChip({ onClick, disabled: true });
      fireEvent.click(screen.getByRole("button"));
      expect(onClick).not.toHaveBeenCalled();
    });

    it("applies disabled styling when disabled", () => {
      const { container } = renderChip({ disabled: true });
      const chip = container.querySelector(".chip");
      expect(chip).toHaveClass("disabled");
    });

    it("sets aria-disabled when disabled", () => {
      renderChip({ disabled: true });
      expect(screen.getByRole("button")).toHaveAttribute("aria-disabled", "true");
    });
  });

  describe("dragging state", () => {
    it("applies dragging class when isDragging is true", () => {
      const { container } = renderChip({ isDragging: true });
      const chip = container.querySelector(".chip");
      expect(chip).toHaveClass("dragging");
    });

    it("does not apply dragging class by default", () => {
      const { container } = renderChip();
      const chip = container.querySelector(".chip");
      expect(chip).not.toHaveClass("dragging");
    });
  });

  describe("context menu integration", () => {
    it("wraps chip in ActionContextMenu when edit/delete/move handlers are provided", () => {
      renderChip({
        onEdit: vi.fn(),
        onDelete: vi.fn(),
        onMoveToGroup: vi.fn(),
        groups: [createGroup()],
      });
      expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("renders without context menu when handlers are not provided", () => {
      renderChip();
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });
});
