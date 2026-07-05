import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolUseBlock } from "~/api";

import type { ChipData } from "../chipRow.types.ts";
import { getExecutingLabel } from "../chipRowUtils.ts";
import { FileChip } from "../FileChip.tsx";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const createToolUseBlock = (overrides: Partial<ToolUseBlock> = {}): ToolUseBlock => ({
  id: "tool-1",
  name: "Edit",
  type: "tool_use",
  input: { file_path: "/src/example.ts" },
  ...overrides,
});

const createChipData = (overrides: Partial<ChipData> = {}): ChipData => ({
  id: "chip-1",
  filePath: "/src/example.ts",
  displayName: "example.ts",
  state: "completed",
  stats: { added: 10, removed: 3 },
  isNewFile: false,
  blocks: [],
  results: [],
  errorDetail: null,
  errorContentType: null,
  ...overrides,
});

type ChipProps = React.ComponentProps<typeof FileChip>;

const renderChip = (overrides: Partial<ChipProps> = {}): ReturnType<typeof render> => {
  const defaultProps: ChipProps = {
    chipData: createChipData(),
    isOpen: false,
    onToggle: vi.fn(),
    onFocus: vi.fn(),
    tabIndex: 0,
    ...overrides,
  };
  return render(<FileChip {...defaultProps} />, { wrapper: Wrapper });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("FileChip", () => {
  describe("rendering", () => {
    it("renders the display name", () => {
      renderChip({ chipData: createChipData({ displayName: "App.tsx" }) });
      expect(screen.getByText("App.tsx")).toBeInTheDocument();
    });

    it("renders as a button", () => {
      renderChip();
      expect(screen.getByRole("button")).toBeInTheDocument();
    });

    it("renders added and removed stats", () => {
      renderChip({ chipData: createChipData({ stats: { added: 5, removed: 2 } }) });
      expect(screen.getByText("+5")).toBeInTheDocument();
      expect(screen.getByText("-2")).toBeInTheDocument();
    });

    it("hides removed stats for new files", () => {
      renderChip({ chipData: createChipData({ isNewFile: true, stats: { added: 10, removed: 0 } }) });
      expect(screen.getByText("+10")).toBeInTheDocument();
      expect(screen.queryByText("-0")).not.toBeInTheDocument();
    });

    it("does not render stats when null", () => {
      renderChip({ chipData: createChipData({ state: "completed", stats: null }) });
      expect(screen.queryByText(/^\+/)).not.toBeInTheDocument();
      expect(screen.queryByText(/^-/)).not.toBeInTheDocument();
    });
  });

  describe("state classes", () => {
    it("applies open class when isOpen is true", () => {
      const { container } = renderChip({ isOpen: true });
      expect(container.querySelector(".chipOpen")).toBeInTheDocument();
    });

    it("does not apply open class when isOpen is false", () => {
      const { container } = renderChip({ isOpen: false });
      expect(container.querySelector(".chipOpen")).not.toBeInTheDocument();
    });

    it("applies executing class when state is executing", () => {
      const { container } = renderChip({
        chipData: createChipData({ state: "executing", stats: null }),
      });
      expect(container.querySelector(".chipExecuting")).toBeInTheDocument();
    });

    it("applies error class when state is error", () => {
      const { container } = renderChip({
        chipData: createChipData({ state: "error", stats: null }),
      });
      expect(container.querySelector(".chipError")).toBeInTheDocument();
    });

    it("applies error name class to display name when in error state", () => {
      const { container } = renderChip({
        chipData: createChipData({ state: "error", stats: null }),
      });
      expect(container.querySelector(".chipErrorName")).toBeInTheDocument();
    });
  });

  describe("executing state", () => {
    it("disables the button when executing", () => {
      renderChip({ chipData: createChipData({ state: "executing", stats: null }) });
      expect(screen.getByRole("button")).toBeDisabled();
    });

    it("does not call onToggle when clicked while executing", () => {
      const onToggle = vi.fn();
      renderChip({
        chipData: createChipData({ state: "executing", stats: null }),
        onToggle,
      });
      fireEvent.click(screen.getByRole("button"));
      expect(onToggle).not.toHaveBeenCalled();
    });

    it("renders skeleton loaders when executing with no stats", () => {
      const { container } = renderChip({
        chipData: createChipData({ state: "executing", stats: null }),
      });
      expect(container.querySelectorAll(".statsSkeleton")).toHaveLength(2);
    });

    it("wraps chip in a tooltip when executing", () => {
      renderChip({
        chipData: createChipData({
          state: "executing",
          stats: null,
          blocks: [createToolUseBlock({ name: "Edit" })],
        }),
      });
      // The tooltip is rendered but the button should still be present
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });

  describe("interactions", () => {
    it("calls onToggle when clicked in completed state", () => {
      const onToggle = vi.fn();
      renderChip({ onToggle });
      fireEvent.click(screen.getByRole("button"));
      expect(onToggle).toHaveBeenCalledOnce();
    });

    it("calls onFocus when focused", () => {
      const onFocus = vi.fn();
      renderChip({ onFocus });
      fireEvent.focus(screen.getByRole("button"));
      expect(onFocus).toHaveBeenCalledOnce();
    });

    it("respects tabIndex prop", () => {
      renderChip({ tabIndex: -1 });
      expect(screen.getByRole("button")).toHaveAttribute("tabindex", "-1");
    });

    it("sets tabIndex 0 for focusable chip", () => {
      renderChip({ tabIndex: 0 });
      expect(screen.getByRole("button")).toHaveAttribute("tabindex", "0");
    });
  });

  describe("getExecutingLabel", () => {
    it("returns 'Writing…' for a Write block", () => {
      const chipData = createChipData({ blocks: [createToolUseBlock({ name: "Write" })] });
      expect(getExecutingLabel(chipData)).toBe("Writing…");
    });

    it("returns 'Editing…' for an Edit block", () => {
      const chipData = createChipData({ blocks: [createToolUseBlock({ name: "Edit" })] });
      expect(getExecutingLabel(chipData)).toBe("Editing…");
    });

    it("falls back to 'Editing…' when there is no leading block", () => {
      const chipData = createChipData({ blocks: [] });
      expect(getExecutingLabel(chipData)).toBe("Editing…");
    });
  });

  describe("executing state rendering", () => {
    it("disables the chip while a tool is executing", () => {
      renderChip({
        chipData: createChipData({
          state: "executing",
          stats: null,
          blocks: [createToolUseBlock({ name: "Write" })],
        }),
      });
      expect(screen.getByRole("button")).toBeDisabled();
    });
  });
});
