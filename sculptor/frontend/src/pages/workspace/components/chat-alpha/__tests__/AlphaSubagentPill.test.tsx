import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { ToolResultBlock, ToolUseBlock } from "~/api";
import type { SubagentMetadata, SubagentTreeNode } from "~/pages/workspace/utils/subagentTree.ts";

import { AlphaSubagentPill } from "../AlphaSubagentPill.tsx";
import { ToolNavigationProvider, useToolNavigation } from "../ToolNavigationContext.tsx";

// Avoid timer side effects in tests. The spy records the hook's arguments so
// tests can assert on the isTicking flag (arg 1) — that flag is what actually
// starts/stops the live timer.
const elapsedTimeSpy = vi.hoisted(() => vi.fn());
vi.mock("../useElapsedTime.ts", () => ({
  useElapsedTime: (...args: Array<unknown>): { elapsed: string } => {
    elapsedTimeSpy(...args);
    return { elapsed: "2.5s" };
  },
}));

// Avoid complex popover dependencies (only the trigger is under test)
vi.mock("../AlphaSubagentPopover.tsx", () => ({
  AlphaSubagentPopover: (): ReactElement => <div data-testid="subagent-popover" />,
}));

const TOOL_USE_ID = "toolu_test_001";

const EMPTY_CHILD_NODES: Array<SubagentTreeNode> = [];

const makeParentBlock = (): ToolUseBlock => ({
  id: TOOL_USE_ID,
  name: "Agent",
  type: "tool_use",
  input: { prompt: "Explore the codebase", description: "Explore" },
});

const makeToolResult = (overrides: Partial<ToolResultBlock> = {}): ToolResultBlock => ({
  toolUseId: TOOL_USE_ID,
  toolName: "Agent",
  invocationString: "Agent(prompt='Explore')",
  content: { contentType: "generic", text: "Done" },
  isError: false,
  durationSeconds: 5.0,
  ...overrides,
});

const makeMetadataMap = (overrides: Partial<SubagentMetadata> = {}): Map<string, SubagentMetadata> => {
  const metadata: SubagentMetadata = {
    subagentType: undefined,
    prompt: "Explore the codebase",
    responseText: undefined,
    ...overrides,
  };
  return new Map([[TOOL_USE_ID, metadata]]);
};

const renderPill = ({
  toolResultMap = new Map<string, ToolResultBlock>(),
  subagentMetadataMap,
}: {
  toolResultMap?: Map<string, ToolResultBlock>;
  subagentMetadataMap?: Map<string, SubagentMetadata>;
} = {}): ReturnType<typeof render> => {
  const store = createStore();

  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  return render(
    <AlphaSubagentPill
      parentBlock={makeParentBlock()}
      childNodes={EMPTY_CHILD_NODES}
      toolResultMap={toolResultMap}
      subagentMetadataMap={subagentMetadataMap}
    />,
    { wrapper: Wrapper },
  );
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AlphaSubagentPill", () => {
  describe("thinking state", () => {
    it("shows animation when no responseText and no result", () => {
      const { container } = renderPill({ subagentMetadataMap: makeMetadataMap() });
      expect(container.querySelector(".gutterIcon")).toBeInTheDocument();
    });

    it("shows corner icon instead of animation when toolResultMap has the result", () => {
      // Regression: previously isThinking ignored toolResultMap and stayed true even
      // when the tool result was present, causing the thinking animation to persist.
      const toolResultMap = new Map([[TOOL_USE_ID, makeToolResult()]]);
      const { container } = renderPill({ toolResultMap, subagentMetadataMap: makeMetadataMap() });
      const gutterIcon = container.querySelector(".gutterIcon");
      expect(gutterIcon).toBeInTheDocument();
      expect(gutterIcon?.querySelector("svg")).toBeInTheDocument();
    });

    it("shows corner icon instead of animation when metadata has responseText", () => {
      const { container } = renderPill({
        subagentMetadataMap: makeMetadataMap({ responseText: "Subagent completed." }),
      });
      const gutterIcon = container.querySelector(".gutterIcon");
      expect(gutterIcon).toBeInTheDocument();
      expect(gutterIcon?.querySelector("svg")).toBeInTheDocument();
    });
  });

  describe("prompt display", () => {
    it("shows prompt text when prompt exists", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap() });
      expect(screen.getByText("Explore the codebase")).toBeInTheDocument();
    });

    it("hides prompt when no prompt", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap({ prompt: undefined }) });
      expect(screen.queryByText("Explore the codebase")).not.toBeInTheDocument();
    });

    it("renders full prompt text in DOM (CSS handles truncation)", () => {
      const longPrompt = "A".repeat(200);
      renderPill({ subagentMetadataMap: makeMetadataMap({ prompt: longPrompt }) });
      expect(screen.getByText(longPrompt)).toBeInTheDocument();
    });

    it("hides prompt and separator when no metadata", () => {
      renderPill();
      expect(screen.queryByText("\u00B7")).not.toBeInTheDocument();
    });
  });

  describe("duration", () => {
    it("shows elapsed time from hook while thinking", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap() });
      expect(screen.getByText("2.5s")).toBeInTheDocument();
    });

    it("shows backend duration when result exists", () => {
      const toolResultMap = new Map([[TOOL_USE_ID, makeToolResult({ durationSeconds: 5.0 })]]);
      renderPill({ toolResultMap, subagentMetadataMap: makeMetadataMap() });
      expect(screen.getByText("5.0s")).toBeInTheDocument();
    });

    it("formats duration in seconds even when >= 60s", () => {
      const toolResultMap = new Map([[TOOL_USE_ID, makeToolResult({ durationSeconds: 125.3 })]]);
      renderPill({ toolResultMap, subagentMetadataMap: makeMetadataMap() });
      expect(screen.getByText("125.3s")).toBeInTheDocument();
    });
  });

  describe("interaction", () => {
    it("renders a trigger button that can open the popover", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap() });
      expect(screen.getByRole("button")).toBeInTheDocument();
    });
  });

  describe("background liveness", () => {
    it("keeps the timer ticking while the background task is pending", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap({ isBackground: true, isStillRunning: true }) });
      expect(elapsedTimeSpy.mock.lastCall?.[1]).toBe(true);
    });

    it("stops the timer when the task left the pending set without a response", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap({ isBackground: true, isStillRunning: false }) });
      expect(elapsedTimeSpy.mock.lastCall?.[1]).toBe(false);
    });

    it("keeps ticking when liveness is unknown (no task id — older persisted sessions)", () => {
      renderPill({ subagentMetadataMap: makeMetadataMap({ isBackground: true }) });
      expect(elapsedTimeSpy.mock.lastCall?.[1]).toBe(true);
    });
  });

  describe("keyboard navigation", () => {
    type Nav = NonNullable<ReturnType<typeof useToolNavigation>>;

    let capturedNav: Nav;
    const NavCapture = ({ children }: { children: ReactNode }): ReactElement => {
      const nav = useToolNavigation();
      if (!nav) throw new Error("ToolNavigationProvider missing");
      capturedNav = nav;
      return <>{children}</>;
    };

    const renderPillWithNav = ({
      rowIndex,
      toolResultMap = new Map<string, ToolResultBlock>(),
      subagentMetadataMap,
    }: {
      rowIndex?: number;
      toolResultMap?: Map<string, ToolResultBlock>;
      subagentMetadataMap?: Map<string, SubagentMetadata>;
    }): ReturnType<typeof render> => {
      const store = createStore();

      const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
        <Provider store={store}>
          <Theme>
            <ToolNavigationProvider>
              <NavCapture>{children}</NavCapture>
            </ToolNavigationProvider>
          </Theme>
        </Provider>
      );

      return render(
        <AlphaSubagentPill
          parentBlock={makeParentBlock()}
          childNodes={EMPTY_CHILD_NODES}
          toolResultMap={toolResultMap}
          subagentMetadataMap={subagentMetadataMap}
          rowIndex={rowIndex}
        />,
        { wrapper: Wrapper },
      );
    };

    it("registers the row with ToolNavigationProvider when rowIndex is provided", () => {
      renderPillWithNav({ rowIndex: 0, subagentMetadataMap: makeMetadataMap() });

      const trigger = screen.getByRole("button");
      act(() => {
        fireEvent.click(trigger);
      });

      expect(capturedNav.openItemId).toBe(TOOL_USE_ID);
    });

    it("ArrowLeft/ArrowRight do nothing when the popover is closed", () => {
      renderPillWithNav({ rowIndex: 0, subagentMetadataMap: makeMetadataMap() });

      const trigger = screen.getByRole("button");
      // Don't open. Press ArrowRight while closed.
      act(() => {
        fireEvent.keyDown(trigger, { key: "ArrowRight" });
      });

      expect(capturedNav.openItemId).toBeNull();
    });

    it("ArrowRight steps to the next item via navigate when popover is open", () => {
      renderPillWithNav({ rowIndex: 0, subagentMetadataMap: makeMetadataMap() });

      // Register a sibling row with one item so "next" has somewhere to go.
      // Stub scrollIntoView/focus — navigate() calls both, and jsdom doesn't
      // implement scrollIntoView on elements that aren't in the document.
      const sibling = document.createElement("button");
      sibling.scrollIntoView = vi.fn();
      sibling.focus = vi.fn();
      act(() => {
        capturedNav.registerRow(1, ["other-id"]);
        capturedNav.setItemRef("other-id", sibling);
      });

      const trigger = screen.getByRole("button");
      act(() => {
        fireEvent.click(trigger);
      });
      expect(capturedNav.openItemId).toBe(TOOL_USE_ID);

      act(() => {
        fireEvent.keyDown(trigger, { key: "ArrowRight" });
      });

      expect(capturedNav.openItemId).toBe("other-id");
    });

    it("Escape closes the open popover", () => {
      renderPillWithNav({ rowIndex: 0, subagentMetadataMap: makeMetadataMap() });

      const trigger = screen.getByRole("button");
      act(() => {
        fireEvent.click(trigger);
      });
      expect(capturedNav.openItemId).toBe(TOOL_USE_ID);

      act(() => {
        fireEvent.keyDown(trigger, { key: "Escape" });
      });

      expect(capturedNav.openItemId).toBeNull();
    });

    it("falls back to local state when no ToolNavigationProvider wraps it", () => {
      // No provider — just Theme. The pill should fall back to local open state.
      render(
        <Theme>
          <AlphaSubagentPill
            parentBlock={makeParentBlock()}
            childNodes={EMPTY_CHILD_NODES}
            toolResultMap={new Map<string, ToolResultBlock>()}
            subagentMetadataMap={makeMetadataMap()}
          />
        </Theme>,
      );

      const trigger = screen.getByRole("button");
      act(() => {
        fireEvent.click(trigger);
      });

      // The mocked AlphaSubagentPopover renders a div with this testid when open.
      expect(screen.getByTestId("subagent-popover")).toBeInTheDocument();
    });
  });
});
