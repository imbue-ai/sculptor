import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";

import { AlphaToolPillRow } from "../AlphaToolPillRow.tsx";
import type * as AlphaToolPopoverModule from "../AlphaToolPopover.tsx";
import { chatToolDensityAtom } from "../atoms.ts";

vi.mock("~/pages/workspace/hooks/useWorkspaceCodePath.ts", () => ({
  useWorkspaceCodePath: (): string => "/workspace/code",
}));

vi.mock("../AlphaToolPopover.tsx", async (importOriginal) => {
  // Keep `ToolEntryContent` real — AlphaExpandedToolRow consumes it for the
  // per-tool inlined header content. Only override the popover surface.
  const actual = await importOriginal<typeof AlphaToolPopoverModule>();
  return {
    ...actual,
    AlphaToolPopover: ({ pillData }: { pillData: { label: string } }): ReactElement => (
      <div data-testid="tool-popover">{pillData.label}</div>
    ),
  };
});

vi.mock("../AlphaCommandPopover.tsx", () => ({
  AlphaCommandPopover: ({ toolName }: { toolName: string }): ReactElement => (
    <div data-testid="command-popover">{toolName}</div>
  ),
}));

const createToolUse = (overrides: Partial<ToolUseBlock> = {}): ToolUseBlock => ({
  id: `tool-${Math.random().toString(36).slice(2, 8)}`,
  name: "Read",
  type: "tool_use",
  input: { file_path: "/src/file.ts" },
  ...overrides,
});

const createToolResult = (toolUseId: string, overrides: Partial<ToolResultBlock> = {}): ToolResultBlock => ({
  toolUseId,
  toolName: "Read",
  invocationString: "Read file.ts",
  content: { contentType: "generic", text: "file contents" },
  isError: false,
  durationSeconds: 0.2,
  ...overrides,
});

type PillRowProps = React.ComponentProps<typeof AlphaToolPillRow>;

type RenderOptions = {
  density?: "default" | "expanded";
};

const renderPillRow = (
  overrides: Partial<PillRowProps> = {},
  options: RenderOptions = {},
): ReturnType<typeof render> => {
  const block = createToolUse({ id: "tool-1" });
  const result = createToolResult("tool-1");
  const resultMap = new Map<string, ToolResultBlock>([["tool-1", result]]);

  const store = createStore();
  if (options.density) {
    store.set(chatToolDensityAtom, options.density);
  }

  const defaultProps: PillRowProps = {
    blocks: [block, result],
    toolResultMap: resultMap,
    inProgressMessageId: null,
    ...overrides,
  };

  // Expanded density renders the per-tool entries inline, and ReadEntry
  // calls `useWorkspacePageParams` (which uses `useLocation`). Wrap in a
  // MemoryRouter with a workspace path so the hook resolves.
  const WrapperWithStore = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>
        <MemoryRouter initialEntries={["/ws/test-workspace"]}>
          <Routes>
            <Route path="/ws/:workspaceID" element={children} />
          </Routes>
        </MemoryRouter>
      </Theme>
    </Provider>
  );

  return render(<AlphaToolPillRow {...defaultProps} />, { wrapper: WrapperWithStore });
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AlphaToolPillRow", () => {
  describe("pill rendering", () => {
    it("renders pill buttons", () => {
      renderPillRow();
      const buttons = screen.getAllByRole("button");
      expect(buttons.length).toBeGreaterThan(0);
    });

    it("renders nothing when blocks produce no pills", () => {
      const { container } = renderPillRow({ blocks: [], toolResultMap: new Map() });
      expect(container.querySelector("button")).not.toBeInTheDocument();
    });
  });

  describe("panel toggle", () => {
    it("opens a popover when a pill is clicked", () => {
      renderPillRow();
      const buttons = screen.getAllByRole("button");
      fireEvent.click(buttons[0]!);
      expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();
    });

    it("closes a popover when the same pill is clicked again", () => {
      renderPillRow();
      const buttons = screen.getAllByRole("button");
      fireEvent.click(buttons[0]!);
      expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();

      fireEvent.click(buttons[0]!);
      expect(screen.queryByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).not.toBeInTheDocument();
    });
  });

  describe("pin / unpin / Escape", () => {
    it("keeps a click-opened popover open after the close delay elapses on hover-leave (pinned)", () => {
      vi.useFakeTimers();
      try {
        renderPillRow();
        const pillButton = screen.getAllByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL)[0]!;

        fireEvent.click(pillButton);
        expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();

        // Hover-leave should not dismiss a pinned popover even after the close
        // delay (80ms in usePillHoverDelay) plus a generous buffer.
        const hoverZone = pillButton.parentElement!;
        fireEvent.mouseLeave(hoverZone);
        act(() => {
          vi.advanceTimersByTime(500);
        });
        expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();
      } finally {
        vi.useRealTimers();
      }
    });

    it("closes when the same pinned pill is clicked again", () => {
      renderPillRow();
      const pillButton = screen.getAllByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL)[0]!;

      fireEvent.click(pillButton);
      expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();

      fireEvent.click(pillButton);
      expect(screen.queryByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).not.toBeInTheDocument();
    });

    it("closes a pinned popover when Escape is pressed on the toolbar", () => {
      renderPillRow();
      const pillButton = screen.getAllByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL)[0]!;
      fireEvent.click(pillButton);
      expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();

      const toolbar = screen.getByRole("toolbar");
      fireEvent.keyDown(toolbar, { key: "Escape" });
      expect(screen.queryByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).not.toBeInTheDocument();
    });
  });

  describe("expanded density", () => {
    it("renders one row per call with the tool name and the inlined header content", () => {
      const blockA = createToolUse({ id: "tool-a", input: { file_path: "/workspace/code/foo.ts" } });
      const blockB = createToolUse({ id: "tool-b", input: { file_path: "/workspace/code/bar.ts" } });
      const resultA = createToolResult("tool-a");
      const resultB = createToolResult("tool-b");
      const resultMap = new Map<string, ToolResultBlock>([
        ["tool-a", resultA],
        ["tool-b", resultB],
      ]);

      renderPillRow({ blocks: [blockA, blockB], toolResultMap: resultMap }, { density: "expanded" });

      // One row per call (instead of two pills on one row separated by a comma).
      const rows = screen.getAllByRole("button");
      expect(rows.length).toBeGreaterThanOrEqual(2);
      // Tool names render alongside each row (default density's pills also do —
      // the assertion below only confirms they're present, not which layout).
      expect(screen.getAllByText("Read").length).toBe(2);
      // Header content is inlined: project-relative file paths show on the row.
      expect(screen.getByText("foo.ts")).toBeInTheDocument();
      expect(screen.getByText("bar.ts")).toBeInTheDocument();
    });

    it("opens the popover when an expanded row is clicked", () => {
      renderPillRow({}, { density: "expanded" });
      const rows = screen.getAllByRole("button");
      fireEvent.click(rows[0]!);
      expect(screen.getByTestId(ElementIds.ALPHA_CHAT_TOOL_PILL_POPOVER)).toBeInTheDocument();
    });
  });
});
