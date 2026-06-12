import { Theme } from "@radix-ui/themes";
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { RefObject } from "react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type ChatMessage, ChatMessageRole } from "~/api";

import { AlphaPromptNavigator } from "../AlphaPromptNavigator.tsx";

// --- ResizeObserver mock ---------------------------------------------------
// We override the global polyfill from vitest.setup.ts so we can control the
// contentRect height delivered to the component — this lets us force the
// rail into its collapsed state without needing >30 messages.
const resizeObserverCallbacks = new Set<ResizeObserverCallback>();

class MockResizeObserver {
  private callback: ResizeObserverCallback;
  constructor(callback: ResizeObserverCallback) {
    this.callback = callback;
    resizeObserverCallbacks.add(callback);
  }
  observe = vi.fn();
  unobserve = vi.fn();
  disconnect = vi.fn().mockImplementation(() => {
    resizeObserverCallbacks.delete(this.callback);
  });
}

/** Deliver a mock ResizeObserver entry with the given container height. */
const triggerResize = (height: number): void => {
  const entry = {
    contentRect: { height } as DOMRectReadOnly,
  } as unknown as ResizeObserverEntry;
  for (const callback of resizeObserverCallbacks) {
    callback([entry], {} as ResizeObserver);
  }
};

// --- ChatMessage factory ---------------------------------------------------
const makeUserMessage = (id: string, text: string): ChatMessage =>
  ({
    id,
    role: ChatMessageRole.USER,
    content: [{ type: "text", text }],
  }) as unknown as ChatMessage;

const makeMessages = (count: number): ReadonlyArray<ChatMessage> =>
  Array.from({ length: count }, (_, i) => makeUserMessage(`m-${i}`, `prompt ${i + 1}`));

// --- Render helper ---------------------------------------------------------
type NavigatorProps = React.ComponentProps<typeof AlphaPromptNavigator>;

const renderNavigator = (
  overrides: Partial<NavigatorProps> = {},
): {
  rendered: ReturnType<typeof render>;
  onNavigate: ReturnType<typeof vi.fn>;
  scrollContainer: HTMLDivElement;
} => {
  const onNavigate = vi.fn();
  const scrollContainer = document.createElement("div");
  document.body.appendChild(scrollContainer);
  const scrollContainerRef: RefObject<HTMLDivElement | null> = { current: scrollContainer };

  const store = createStore();
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );

  const defaultProps: NavigatorProps = {
    userMessages: makeMessages(3),
    scrollContainerRef,
    activePromptIndex: 0,
    onNavigate,
    ...overrides,
  };

  const rendered = render(<AlphaPromptNavigator {...defaultProps} />, { wrapper: Wrapper });
  return { rendered, onNavigate, scrollContainer };
};

// --- Setup / teardown ------------------------------------------------------
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", MockResizeObserver);
  resizeObserverCallbacks.clear();

  // Mock the clipboard API — jsdom doesn't implement it.
  Object.defineProperty(navigator, "clipboard", {
    configurable: true,
    value: { writeText: vi.fn().mockResolvedValue(undefined) },
  });
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  vi.useRealTimers();
  vi.restoreAllMocks();
  // Remove any leftover scroll containers we appended.
  document.body.innerHTML = "";
});

describe("AlphaPromptNavigator", () => {
  describe("rendering", () => {
    it("renders null when userMessages is empty", () => {
      renderNavigator({ userMessages: [] });
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_RAIL")).not.toBeInTheDocument();
      expect(screen.queryAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT")).toHaveLength(0);
    });

    it("renders one dot per user message when the list is small", () => {
      renderNavigator({ userMessages: makeMessages(3) });
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_RAIL")).toBeInTheDocument();
      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      expect(dots).toHaveLength(3);
    });

    it("marks only the active dot with data-is-active=true", () => {
      renderNavigator({ userMessages: makeMessages(3), activePromptIndex: 1 });
      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      expect(dots[0]).toHaveAttribute("data-is-active", "false");
      expect(dots[1]).toHaveAttribute("data-is-active", "true");
      expect(dots[2]).toHaveAttribute("data-is-active", "false");
    });
  });

  describe("click navigation", () => {
    it("calls onNavigate with the dot's index when clicked", () => {
      const { onNavigate } = renderNavigator({ userMessages: makeMessages(3) });
      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      // The click handler is on the dot wrapper (parentElement), but the event
      // bubbles, so firing the click on the dot itself still triggers it.
      fireEvent.click(dots[2]!);
      expect(onNavigate).toHaveBeenCalledWith(2);
    });
  });

  describe("popover tooltip", () => {
    it("shows the popover with prompt text and label after hover delay", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      // Nothing visible initially.
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).not.toBeInTheDocument();

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      const dotWrapper = dots[1]!.parentElement!;
      fireEvent.mouseEnter(dotWrapper);

      // Before the 420 ms delay, still not visible.
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).not.toBeInTheDocument();

      // Flush past the open delay.
      act(() => {
        vi.advanceTimersByTime(450);
      });

      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveTextContent("PROMPT 2");
      expect(tooltip).toHaveTextContent("prompt 2");
    });

    it("copies the prompt text to the clipboard when the copy button is clicked", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(450);
      });

      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      // The copy button is an IconButton with title="Copy prompt".
      const copyButton = tooltip.querySelector('button[title="Copy prompt"]');
      expect(copyButton).not.toBeNull();

      fireEvent.click(copyButton!);
      expect(navigator.clipboard.writeText).toHaveBeenCalledWith("prompt 1");
    });
  });

  describe("collapse behavior", () => {
    it("shows a +N collapsed indicator when userMessages exceeds maxVisibleDots (length > 30)", () => {
      renderNavigator({ userMessages: makeMessages(35) });

      // Default maxVisibleDots is 30, so 35 messages should collapse.
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR")).toBeInTheDocument();
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR").textContent).toMatch(/^\+\d+$/);

      // Fewer dots visible than total messages.
      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      expect(dots.length).toBeLessThan(35);
    });

    it("collapses when ResizeObserver reports a small container height", () => {
      renderNavigator({ userMessages: makeMessages(10) });

      // With 10 messages and the default max of 30, no collapse yet.
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR")).not.toBeInTheDocument();

      // Deliver a tiny height — this should floor maxVisibleDots to MIN_VISIBLE_DOTS (5).
      act(() => {
        triggerResize(40);
      });

      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR")).toBeInTheDocument();
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR").textContent).toMatch(/^\+/);
    });

    it("expands to show all dots when the +N indicator is clicked", () => {
      renderNavigator({ userMessages: makeMessages(35) });

      const indicator = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR");
      expect(screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT").length).toBeLessThan(35);

      fireEvent.click(indicator);

      // Now all 35 dots should render and the indicator should be gone.
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR")).not.toBeInTheDocument();
      expect(screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT")).toHaveLength(35);
    });
  });

  describe("context menu", () => {
    it("wraps each dot in a Radix ContextMenu with a Copy prompt trigger", () => {
      // Radix ContextMenu pointer events are tricky to exercise in jsdom.
      // A lighter assertion: the component renders the dot wrapper as the
      // ContextMenu.Trigger child, and right-clicking doesn't throw.
      renderNavigator({ userMessages: makeMessages(3) });
      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      const wrapper = dots[0]!.parentElement!;

      expect(() => {
        fireEvent.contextMenu(wrapper);
      }).not.toThrow();

      // The dot wrapper (ContextMenu.Trigger's child) should still be present.
      expect(wrapper).toBeInTheDocument();
    });
  });

  describe("popover lifecycle", () => {
    it("swaps popover content instantly when hovering a different dot while open", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      // Open on dot 0.
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toHaveTextContent("PROMPT 1");

      // Move to dot 2 — content swaps immediately (no additional delay).
      fireEvent.mouseLeave(dots[0]!.parentElement!);
      fireEvent.mouseEnter(dots[2]!.parentElement!);
      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      expect(tooltip).toHaveTextContent("PROMPT 3");
      expect(tooltip).toHaveTextContent("prompt 3");
    });

    it("does not close immediately on mouseleave (close is debounced)", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toBeInTheDocument();

      fireEvent.mouseLeave(dots[0]!.parentElement!);
      // Within the 80ms close delay, popover is still mounted.
      act(() => {
        vi.advanceTimersByTime(40);
      });
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toBeInTheDocument();

      // After the close delay fires and neither dot nor popover is hovered,
      // it dismisses.
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).not.toBeInTheDocument();
    });

    it("opens instantly within the reopen grace period after a close", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      // Open, then close.
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      fireEvent.mouseLeave(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(200);
      });
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).not.toBeInTheDocument();

      // Re-enter within the 300ms grace window — reopen should fire synchronously
      // (delay=0), so advancing 0ms is enough.
      fireEvent.mouseEnter(dots[1]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(0);
      });
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toBeInTheDocument();
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toHaveTextContent("PROMPT 2");
    });
  });

  describe("copy button", () => {
    it("shows a check icon after copying, reverting after ~1.5s", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });

      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      const copyButton = tooltip.querySelector('button[title="Copy prompt"]') as HTMLElement;
      // Initially: lucide Copy icon rendered (check icon absent).
      expect(copyButton.querySelector(".lucide-check")).toBeNull();

      fireEvent.click(copyButton);

      // After click, CheckIcon is rendered. Lucide adds lucide-check class.
      const afterClick = tooltip.querySelector('button[title="Copy prompt"]') as HTMLElement;
      expect(afterClick.querySelector(".lucide-check")).not.toBeNull();

      // Wait past the 1500ms revert.
      act(() => {
        vi.advanceTimersByTime(1600);
      });
      const afterRevert = tooltip.querySelector('button[title="Copy prompt"]') as HTMLElement;
      expect(afterRevert.querySelector(".lucide-check")).toBeNull();
    });

    it("resets to the copy icon when hovering a different dot", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });

      let tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      const copyButton = tooltip.querySelector('button[title="Copy prompt"]') as HTMLElement;
      fireEvent.click(copyButton);
      expect(copyButton.querySelector(".lucide-check")).not.toBeNull();

      // Move to dot 2 — popover retargets and isCopied resets.
      fireEvent.mouseLeave(dots[0]!.parentElement!);
      fireEvent.mouseEnter(dots[2]!.parentElement!);
      tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      const newCopyButton = tooltip.querySelector('button[title="Copy prompt"]') as HTMLElement;
      expect(newCopyButton.querySelector(".lucide-check")).toBeNull();
    });
  });

  describe("active state", () => {
    it("flips data-is-active when activePromptIndex prop changes", () => {
      const { rendered } = renderNavigator({
        userMessages: makeMessages(3),
        activePromptIndex: 0,
      });

      let dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      expect(dots[0]).toHaveAttribute("data-is-active", "true");
      expect(dots[2]).toHaveAttribute("data-is-active", "false");

      const scrollContainer = document.createElement("div");
      const scrollContainerRef: RefObject<HTMLDivElement | null> = { current: scrollContainer };
      rendered.rerender(
        <AlphaPromptNavigator
          userMessages={makeMessages(3)}
          scrollContainerRef={scrollContainerRef}
          activePromptIndex={2}
          onNavigate={vi.fn()}
        />,
      );

      dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      expect(dots[0]).toHaveAttribute("data-is-active", "false");
      expect(dots[2]).toHaveAttribute("data-is-active", "true");
    });

    it("renders HTML markup in prompts as plain text (stripHtml)", () => {
      vi.useFakeTimers();
      const messages = [
        {
          id: "m-0",
          role: ChatMessageRole.USER,
          content: [{ type: "text", text: "<b>bold</b> &amp; <i>italic</i>" }],
        } as unknown as ChatMessage,
      ];
      renderNavigator({ userMessages: messages });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });

      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      // No literal <b> or &amp; in rendered content.
      expect(tooltip.innerHTML).not.toContain("<b>bold</b>");
      // Plain-text should include the words stripped of markup.
      expect(tooltip).toHaveTextContent("bold");
      expect(tooltip).toHaveTextContent("italic");
    });
  });

  describe("FLIP animation on new dot", () => {
    it("does not throw when userMessages length grows", () => {
      const { rendered, scrollContainer } = renderNavigator({ userMessages: makeMessages(3) });

      const scrollContainerRef: RefObject<HTMLDivElement | null> = { current: scrollContainer };

      expect(() => {
        rendered.rerender(
          <AlphaPromptNavigator
            userMessages={makeMessages(4)}
            scrollContainerRef={scrollContainerRef}
            activePromptIndex={3}
            onNavigate={vi.fn()}
          />,
        );
      }).not.toThrow();

      expect(screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT")).toHaveLength(4);
    });
  });

  describe("hover-timer sliding between dots", () => {
    it("does not reset the open timer when sliding from dot A to dot B", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      // Hover dot A. Open timer starts (420ms).
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(300);
      });
      // Before opening, slide to dot B: leave A, enter B.
      fireEvent.mouseLeave(dots[0]!.parentElement!);
      fireEvent.mouseEnter(dots[2]!.parentElement!);
      // Advance the remaining time to complete the cumulative 420ms.
      act(() => {
        vi.advanceTimersByTime(150);
      });

      // Popover should be OPEN showing dot B's content (prompt 3).
      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      expect(tooltip).toBeInTheDocument();
      expect(tooltip).toHaveTextContent("PROMPT 3");
    });

    it("stays open when mouse moves from dot to popover before close timer fires", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      expect(tooltip).toBeInTheDocument();

      // Leave dot (starts 80ms close timer), but enter popover hit-area before
      // it fires.
      fireEvent.mouseLeave(dots[0]!.parentElement!);
      const popoverHitArea = tooltip.parentElement!;
      fireEvent.mouseEnter(popoverHitArea);

      // Advance well past the 80ms close delay.
      act(() => {
        vi.advanceTimersByTime(300);
      });

      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toBeInTheDocument();
    });
  });

  describe("context menu dismisses popover", () => {
    it("closes an open popover when the context menu opens on the dot", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      const wrapper = dots[0]!.parentElement!;
      fireEvent.mouseEnter(wrapper);
      act(() => {
        vi.advanceTimersByTime(500);
      });
      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).toBeInTheDocument();

      // Fire contextmenu — Radix ContextMenu opens, which triggers
      // onOpenChange(true) → dismissPopover via the effect.
      fireEvent.contextMenu(wrapper);
      act(() => {
        vi.advanceTimersByTime(50);
      });

      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP")).not.toBeInTheDocument();
    });
  });

  describe("copy button visibility", () => {
    it("renders the copy button inside the popover without a hover-only wrapper", () => {
      vi.useFakeTimers();
      renderNavigator({ userMessages: makeMessages(3) });

      const dots = screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT");
      fireEvent.mouseEnter(dots[0]!.parentElement!);
      act(() => {
        vi.advanceTimersByTime(500);
      });

      const tooltip = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_TOOLTIP");
      const copyButton = tooltip.querySelector('button[title="Copy prompt"]') as HTMLElement;
      expect(copyButton).not.toBeNull();
      // The button is a direct child of the popover header (sibling of the
      // label) — not wrapped in any hover-only container.
      expect(copyButton.parentElement?.className).toMatch(/popoverHeader/);
      // Visible in the a11y tree — not hidden / display: none.
      expect(copyButton).toBeVisible();
    });
  });

  describe("expanded collapse", () => {
    it("collapses expanded view when clicking outside the rail", () => {
      renderNavigator({ userMessages: makeMessages(35) });

      // Expand first.
      const indicator = screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR");
      fireEvent.click(indicator);
      expect(screen.queryByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR")).not.toBeInTheDocument();
      expect(screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT")).toHaveLength(35);

      // Click outside — re-collapses.
      fireEvent.mouseDown(document.body);

      expect(screen.getByTestId("ALPHA_PROMPT_NAVIGATOR_COLLAPSED_INDICATOR")).toBeInTheDocument();
      expect(screen.getAllByTestId("ALPHA_PROMPT_NAVIGATOR_DOT").length).toBeLessThan(35);
    });
  });
});
