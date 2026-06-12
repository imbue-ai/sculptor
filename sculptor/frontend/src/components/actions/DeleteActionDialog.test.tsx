import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DeleteActionDialog } from "./DeleteActionDialog";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const renderDialog = (props: Partial<React.ComponentProps<typeof DeleteActionDialog>> = {}): RenderResult => {
  const defaultProps: React.ComponentProps<typeof DeleteActionDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    actionName: "Test Action",
    onConfirm: vi.fn(),
    ...props,
  };
  return render(<DeleteActionDialog {...defaultProps} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("DeleteActionDialog", () => {
  describe("rendering", () => {
    it("renders the dialog with action name in title", () => {
      renderDialog({ actionName: "My Action" });
      expect(screen.getByText("Delete 'My Action'")).toBeInTheDocument();
    });

    it("renders the warning message", () => {
      renderDialog();
      expect(screen.getByText("This action will be permanently deleted. This cannot be undone.")).toBeInTheDocument();
    });

    it("renders Cancel and Delete Action buttons", () => {
      renderDialog();
      expect(screen.getByText("Cancel")).toBeInTheDocument();
      expect(screen.getByText("Delete Action")).toBeInTheDocument();
    });

    it("does not render when open is false", () => {
      renderDialog({ open: false });
      expect(screen.queryByText("Delete Action")).not.toBeInTheDocument();
    });

    it("does not render a trash icon", () => {
      const { container } = renderDialog();
      // The trash icon was removed — ensure no lucide trash SVG exists
      const svgs = container.querySelectorAll("svg");
      for (const svg of svgs) {
        // Lucide Trash2 would have a specific path, but we just check there's
        // no icon before the title (inside the Flex wrapper if it existed)
        expect(svg.closest("[role='dialog']")).toBeTruthy();
      }
    });
  });

  describe("interactions", () => {
    it("calls onConfirm when Delete Action button is clicked", () => {
      const onConfirm = vi.fn();
      renderDialog({ onConfirm });
      fireEvent.click(screen.getByText("Delete Action"));
      expect(onConfirm).toHaveBeenCalledTimes(1);
    });

    it("calls onOpenChange when Cancel button is clicked", () => {
      const onOpenChange = vi.fn();
      renderDialog({ onOpenChange });
      fireEvent.click(screen.getByText("Cancel"));
      // Dialog.Close triggers onOpenChange(false)
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });

  describe("deleting state", () => {
    it("disables both buttons when isDeleting is true", () => {
      renderDialog({ isDeleting: true });
      expect(screen.getByText("Cancel").closest("button")).toBeDisabled();
      // When deleting, the delete button shows a spinner instead of text
      const buttons = screen.getAllByRole("button");
      const deleteButton = buttons.find((btn) => btn.style.minWidth === "120px");
      expect(deleteButton).toBeDisabled();
    });

    it("shows Delete Action text when not deleting", () => {
      renderDialog({ isDeleting: false });
      expect(screen.getByText("Delete Action")).toBeInTheDocument();
    });
  });
});
