import { Theme } from "@radix-ui/themes";
import type { RenderResult } from "@testing-library/react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CustomAction, CustomActionGroup } from "~/api";

import { ActionDialog } from "./ActionDialog";

// Mock the Editor component since TipTap requires a real browser DOM.
// The mock renders a simple textarea that mirrors the Editor's interface.
vi.mock("~/components/Editor", () => ({
  Editor: ({
    tagName,
    placeholder,
    value,
    onChange,
  }: {
    tagName: string;
    placeholder: string;
    value: string;
    onChange: (value: string) => void;
  }): ReactElement => (
    <textarea
      data-testid={tagName}
      placeholder={placeholder}
      value={value}
      onChange={(e) => onChange(e.target.value)}
    />
  ),
}));

const createAction = (overrides: Partial<CustomAction> = {}): CustomAction => ({
  id: "action-1",
  name: "Test Action",
  prompt: "Test prompt",
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

const renderDialog = (props: Partial<React.ComponentProps<typeof ActionDialog>> = {}): RenderResult => {
  const defaultProps: React.ComponentProps<typeof ActionDialog> = {
    open: true,
    onOpenChange: vi.fn(),
    groups: [],
    onSave: vi.fn(),
    ...props,
  };
  return render(<ActionDialog {...defaultProps} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("ActionDialog", () => {
  describe("rendering - add mode", () => {
    it("shows 'Add Action' title when no action is provided", () => {
      renderDialog();
      expect(screen.getByText("Add Action")).toBeInTheDocument();
    });

    it("renders Name, Prompt, Group, and Auto-submit fields", () => {
      renderDialog();
      expect(screen.getByText("Name")).toBeInTheDocument();
      expect(screen.getByText("Prompt")).toBeInTheDocument();
      expect(screen.getByText("Group")).toBeInTheDocument();
      expect(screen.getByText("Auto-submit (send immediately)")).toBeInTheDocument();
    });

    it("renders Cancel and Save Action buttons", () => {
      renderDialog();
      expect(screen.getByText("Cancel")).toBeInTheDocument();
      expect(screen.getByText("Save Action")).toBeInTheDocument();
    });

    it("Save Action is disabled when form is empty", () => {
      renderDialog();
      expect(screen.getByText("Save Action").closest("button")).toBeDisabled();
    });

    it("does not render when open is false", () => {
      renderDialog({ open: false });
      expect(screen.queryByText("Add Action")).not.toBeInTheDocument();
    });
  });

  describe("rendering - edit mode", () => {
    it("shows 'Edit Action' title when an action is provided", () => {
      renderDialog({ action: createAction({ name: "Edit Me" }) });
      expect(screen.getByText("Edit Action")).toBeInTheDocument();
    });

    it("pre-fills form fields from the action", () => {
      renderDialog({ action: createAction({ name: "My Action", prompt: "My prompt" }) });
      expect(screen.getByPlaceholderText("Action name")).toHaveValue("My Action");
      expect(screen.getByPlaceholderText("Action prompt")).toHaveValue("My prompt");
    });
  });

  describe("form validation", () => {
    it("enables Save when name and prompt are filled", () => {
      renderDialog();
      fireEvent.change(screen.getByPlaceholderText("Action name"), { target: { value: "A Name" } });
      fireEvent.change(screen.getByPlaceholderText("Action prompt"), { target: { value: "A Prompt" } });
      expect(screen.getByText("Save Action").closest("button")).not.toBeDisabled();
    });

    it("remains disabled when only name is filled", () => {
      renderDialog();
      fireEvent.change(screen.getByPlaceholderText("Action name"), { target: { value: "A Name" } });
      expect(screen.getByText("Save Action").closest("button")).toBeDisabled();
    });

    it("remains disabled when only prompt is filled", () => {
      renderDialog();
      fireEvent.change(screen.getByPlaceholderText("Action prompt"), { target: { value: "A Prompt" } });
      expect(screen.getByText("Save Action").closest("button")).toBeDisabled();
    });
  });

  describe("save behavior", () => {
    it("calls onSave with form data when Save is clicked", () => {
      const onSave = vi.fn();
      renderDialog({ onSave });

      fireEvent.change(screen.getByPlaceholderText("Action name"), { target: { value: "New Action" } });
      fireEvent.change(screen.getByPlaceholderText("Action prompt"), { target: { value: "New Prompt" } });
      fireEvent.click(screen.getByText("Save Action"));

      expect(onSave).toHaveBeenCalledWith({
        name: "New Action",
        prompt: "New Prompt",
        autoSubmit: true,
        groupId: null,
        newGroupName: undefined,
      });
    });
  });

  describe("group selection", () => {
    it("renders the group select with default value", () => {
      const groups = [createGroup({ id: "g1", name: "Group Alpha" }), createGroup({ id: "g2", name: "Group Beta" })];
      renderDialog({ groups });

      // The select starts with "No group" selected (value="none")
      expect(screen.getByText("No group")).toBeInTheDocument();
    });
  });

  describe("cancel", () => {
    it("calls onOpenChange when Cancel is clicked", () => {
      const onOpenChange = vi.fn();
      renderDialog({ onOpenChange });
      fireEvent.click(screen.getByText("Cancel"));
      expect(onOpenChange).toHaveBeenCalledWith(false);
    });
  });
});
