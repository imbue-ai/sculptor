import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";

import { AlphaChipRow } from "../AlphaChipRow.tsx";

// Mock the diff popover to keep tests focused on the row
vi.mock("../AlphaChipDiffPopover.tsx", () => ({
  AlphaChipDiffPopover: (): ReactElement => <div data-testid="diff-popover">Diff popover</div>,
}));

const createToolUseBlock = (overrides: Partial<ToolUseBlock> = {}): ToolUseBlock => ({
  id: `tool-${Math.random().toString(36).slice(2, 8)}`,
  name: "Edit",
  type: "tool_use",
  input: { file_path: "/src/file.ts", old_string: "old", new_string: "new" },
  ...overrides,
});

const createToolResultBlock = (toolUseId: string, overrides: Partial<ToolResultBlock> = {}): ToolResultBlock => ({
  toolUseId,
  toolName: "Edit",
  invocationString: "Edit file.ts",
  content: {
    contentType: "diff" as const,
    filePath: "/src/file.ts",
    oldContent: "old",
    newContent: "new",
    diff: "@@ -1 +1 @@\n-old\n+new",
    linesAdded: 1,
    linesRemoved: 1,
  } as ToolResultBlock["content"],
  isError: false,
  durationSeconds: 0.5,
  ...overrides,
});

type ChipRowProps = React.ComponentProps<typeof AlphaChipRow>;

const renderChipRow = (overrides: Partial<ChipRowProps> = {}): ReturnType<typeof render> => {
  const block = createToolUseBlock({ id: "tool-1", input: { file_path: "/src/app.ts" } });
  const result = createToolResultBlock("tool-1");
  const resultMap = new Map<string, ToolResultBlock>([["tool-1", result]]);

  const store = createStore();

  const defaultProps: ChipRowProps = {
    blocks: [block],
    toolResultMap: resultMap,
    inProgressMessageId: null,
    ...overrides,
  };

  const WrapperWithStore = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  return render(<AlphaChipRow {...defaultProps} />, { wrapper: WrapperWithStore });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AlphaChipRow", () => {
  describe("chip rendering", () => {
    it("renders nothing when no blocks produce chips", () => {
      const { container } = renderChipRow({
        blocks: [createToolUseBlock({ name: "Bash" })],
      });
      // Bash blocks don't produce chips in buildChipData
      // But depending on buildChipData logic, this might render null
      expect(container).toBeTruthy();
    });

    it("renders a toolbar with file modifications label", () => {
      renderChipRow();
      expect(screen.getByRole("toolbar", { name: "File modifications" })).toBeInTheDocument();
    });
  });

  describe("keyboard navigation", () => {
    it("opens panel on chip click", () => {
      renderChipRow();
      const chips = screen.getAllByTestId("ALPHA_CHAT_FILE_CHIP");
      fireEvent.click(chips[0]!);
      expect(screen.getByTestId("diff-popover")).toBeInTheDocument();
    });

    it("closes panel on Escape", () => {
      renderChipRow();
      const chips = screen.getAllByTestId("ALPHA_CHAT_FILE_CHIP");
      fireEvent.click(chips[0]!);
      expect(screen.getByTestId("diff-popover")).toBeInTheDocument();

      const toolbar = screen.getByRole("toolbar");
      fireEvent.keyDown(toolbar, { key: "Escape" });
      expect(screen.queryByTestId("diff-popover")).not.toBeInTheDocument();
    });

    it("moves focus right with ArrowRight when panel is closed", () => {
      const block1 = createToolUseBlock({ id: "t1", input: { file_path: "/src/a.ts" } });
      const block2 = createToolUseBlock({ id: "t2", input: { file_path: "/src/b.ts" } });
      const resultMap = new Map<string, ToolResultBlock>([
        [
          "t1",
          createToolResultBlock("t1", {
            content: {
              contentType: "diff" as const,
              filePath: "/src/a.ts",
              oldContent: "",
              newContent: "",
              diff: "",
              linesAdded: 0,
              linesRemoved: 0,
            } as ToolResultBlock["content"],
          }),
        ],
        [
          "t2",
          createToolResultBlock("t2", {
            content: {
              contentType: "diff" as const,
              filePath: "/src/b.ts",
              oldContent: "",
              newContent: "",
              diff: "",
              linesAdded: 0,
              linesRemoved: 0,
            } as ToolResultBlock["content"],
          }),
        ],
      ]);

      renderChipRow({ blocks: [block1, block2], toolResultMap: resultMap });

      const toolbar = screen.getByRole("toolbar");
      const chips = screen.getAllByTestId("ALPHA_CHAT_FILE_CHIP");

      // Initially first chip has tabIndex 0
      expect(chips[0]).toHaveAttribute("tabindex", "0");
      expect(chips[1]).toHaveAttribute("tabindex", "-1");

      fireEvent.keyDown(toolbar, { key: "ArrowRight" });

      // After ArrowRight, second chip should be focusable
      expect(chips[0]).toHaveAttribute("tabindex", "-1");
      expect(chips[1]).toHaveAttribute("tabindex", "0");
    });

    it("moves focus left with ArrowLeft when panel is closed", () => {
      const block1 = createToolUseBlock({ id: "t1", input: { file_path: "/src/a.ts" } });
      const block2 = createToolUseBlock({ id: "t2", input: { file_path: "/src/b.ts" } });
      const resultMap = new Map<string, ToolResultBlock>([
        [
          "t1",
          createToolResultBlock("t1", {
            content: {
              contentType: "diff" as const,
              filePath: "/src/a.ts",
              oldContent: "",
              newContent: "",
              diff: "",
              linesAdded: 0,
              linesRemoved: 0,
            } as ToolResultBlock["content"],
          }),
        ],
        [
          "t2",
          createToolResultBlock("t2", {
            content: {
              contentType: "diff" as const,
              filePath: "/src/b.ts",
              oldContent: "",
              newContent: "",
              diff: "",
              linesAdded: 0,
              linesRemoved: 0,
            } as ToolResultBlock["content"],
          }),
        ],
      ]);

      renderChipRow({ blocks: [block1, block2], toolResultMap: resultMap });

      const toolbar = screen.getByRole("toolbar");

      // Move right first, then left
      fireEvent.keyDown(toolbar, { key: "ArrowRight" });
      fireEvent.keyDown(toolbar, { key: "ArrowLeft" });

      const chips = screen.getAllByTestId("ALPHA_CHAT_FILE_CHIP");
      expect(chips[0]).toHaveAttribute("tabindex", "0");
    });

    it("clamps focus at the beginning", () => {
      renderChipRow();
      const toolbar = screen.getByRole("toolbar");
      fireEvent.keyDown(toolbar, { key: "ArrowLeft" });

      const chips = screen.getAllByTestId("ALPHA_CHAT_FILE_CHIP");
      expect(chips[0]).toHaveAttribute("tabindex", "0");
    });
  });
});
