import type { Virtualizer } from "@tanstack/react-virtual";
import { act, cleanup, renderHook } from "@testing-library/react";
import type { Mock } from "vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { type ChatMessage, ChatMessageRole, ElementIds } from "~/api";

import type { ActivePromptIndex } from "../useAlphaActivePromptIndex.ts";
import { useAlphaPromptNav } from "../useAlphaPromptNav.ts";

// ---------------------------------------------------------------------------
// Fixtures / helpers
// ---------------------------------------------------------------------------

const makeMessage = (id: string, role: ChatMessageRole): ChatMessage =>
  ({
    id,
    role,
    content: [{ type: "text", text: `msg-${id}` }],
  }) as unknown as ChatMessage;

/** 5 messages with 3 USER prompts at filteredMessage indices 0, 2, 4. */
const buildMessages = (): ReadonlyArray<ChatMessage> => [
  makeMessage("1", ChatMessageRole.USER),
  makeMessage("2", ChatMessageRole.ASSISTANT),
  makeMessage("3", ChatMessageRole.USER),
  makeMessage("4", ChatMessageRole.ASSISTANT),
  makeMessage("5", ChatMessageRole.USER),
];

const createMockVirtualizer = (): Virtualizer<HTMLDivElement, Element> =>
  ({
    scrollToIndex: vi.fn(),
  }) as unknown as Virtualizer<HTMLDivElement, Element>;

/**
 * Build a controller matching the shape useAlphaActivePromptIndex returns,
 * suitable for driving useAlphaPromptNav in a unit test. `setIndex` is a mock
 * that also mutates `ref.current` so subsequent reads in the hook observe it.
 */
type TestController = ActivePromptIndex & {
  setIndex: ReturnType<typeof vi.fn>;
  isScrolledPastActive: ReturnType<typeof vi.fn>;
};

const createController = (startIndex: number, opts: { isScrolledPast?: boolean } = {}): TestController => {
  const ref = { current: startIndex };
  const setIndex = vi.fn((i: number) => {
    ref.current = i;
  });
  const isScrolledPastActive = vi.fn(() => opts.isScrolledPast ?? false);
  return { index: startIndex, ref, setIndex, isScrolledPastActive };
};

/**
 * Place a collapsed caret inside `el`. If `text` is provided it becomes the
 * element's text content (replacing any existing content). `offset` is the
 * character offset into that text at which the caret should sit. With the
 * default `text === ""` and `offset === 0` the caret lands at the very first
 * position of the editable — the only state that should trigger prompt-nav.
 */
const setCaretAtOffset = (el: HTMLElement, offset: number, text: string = ""): void => {
  el.textContent = text;
  const range = document.createRange();
  if (text.length === 0) {
    range.setStart(el, 0);
  } else {
    const textNode = el.firstChild as Text;
    range.setStart(textNode, offset);
  }
  range.collapse(true);
  const selection = window.getSelection();
  selection?.removeAllRanges();
  selection?.addRange(range);
};

const dispatchKey = (
  key: string,
  modifiers: { altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } = {},
): void => {
  window.dispatchEvent(new KeyboardEvent("keydown", { key, bubbles: true, ...modifiers }));
};

const dispatchArrowUp = (
  mods: { altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } = {},
): void => dispatchKey("ArrowUp", mods);

const dispatchArrowDown = (
  mods: { altKey?: boolean; ctrlKey?: boolean; metaKey?: boolean; shiftKey?: boolean } = {},
): void => dispatchKey("ArrowDown", mods);

const dispatchEscape = (): void => dispatchKey("Escape");
const dispatchEnter = (): void => dispatchKey("Enter");

// Wait for a queued rAF (applyHighlight schedules one) to run.
const flushRaf = async (): Promise<void> => {
  await act(async () => {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
  });
};

// ---------------------------------------------------------------------------
// Test suite
// ---------------------------------------------------------------------------

describe("useAlphaPromptNav", () => {
  let mockScrollToBottom: Mock<() => void>;
  let mockSetIsSuppressed: Mock<(val: boolean) => void>;
  let chatInputContainer: HTMLDivElement;
  let editableEl: HTMLDivElement;
  let unmountHandles: Array<() => void>;

  beforeEach(() => {
    mockScrollToBottom = vi.fn();
    mockSetIsSuppressed = vi.fn();
    unmountHandles = [];

    // Build a chat-input container with a focusable contenteditable child.
    chatInputContainer = document.createElement("div");
    chatInputContainer.id = "chat-input";
    editableEl = document.createElement("div");
    editableEl.setAttribute("contenteditable", "true");
    editableEl.setAttribute("tabindex", "0");
    chatInputContainer.appendChild(editableEl);
    document.body.appendChild(chatInputContainer);

    editableEl.focus();

    // Default: caret is collapsed at the very start of the editable so
    // ArrowUp qualifies as "entering navigation from the first position".
    setCaretAtOffset(editableEl, 0);
  });

  afterEach(() => {
    // Unmount every hook we rendered so their window keydown / focusin
    // listeners are torn down before the next test runs.
    unmountHandles.forEach((u) => u());
    cleanup();
    // Remove any body-level nodes we left around (overlays, extra inputs).
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  const render = (
    messages: ReadonlyArray<ChatMessage>,
    opts: { controller?: TestController; virtualizer?: Virtualizer<HTMLDivElement, Element> } = {},
  ): {
    result: ReturnType<
      typeof renderHook<ReturnType<typeof useAlphaPromptNav>, { msgs: ReadonlyArray<ChatMessage> }>
    >["result"];
    rerender: ReturnType<
      typeof renderHook<ReturnType<typeof useAlphaPromptNav>, { msgs: ReadonlyArray<ChatMessage> }>
    >["rerender"];
    virtualizer: Virtualizer<HTMLDivElement, Element>;
    controller: TestController | undefined;
  } => {
    const virtualizer = opts.virtualizer ?? createMockVirtualizer();
    const controller = opts.controller;
    const { result, rerender, unmount } = renderHook(
      ({ msgs }) => useAlphaPromptNav(msgs, virtualizer, mockScrollToBottom, mockSetIsSuppressed, controller),
      { initialProps: { msgs: messages } },
    );
    unmountHandles.push(unmount);
    return { result, rerender, virtualizer, controller };
  };

  // -------------------------------------------------------------------------
  // 1. Baseline
  // -------------------------------------------------------------------------

  it("starts with isNavigating === false", () => {
    const { result } = render(buildMessages());
    expect(result.current.isNavigating).toBe(false);
  });

  // -------------------------------------------------------------------------
  // 2. ArrowUp entry
  // -------------------------------------------------------------------------

  it("ArrowUp from focused chat input (caret at 0) enters navigation", () => {
    // 3 user prompts; start the controller cursor at the last (index 2 into
    // userPromptIndices — i.e. the "4" in filteredMessages is index 4).
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(true);
    expect(mockSetIsSuppressed).toHaveBeenCalledWith(true);
    // newIdx = 2 - 1 = 1; userPromptIndices[1] = 2 (the second USER message).
    expect(controller.setIndex).toHaveBeenCalledWith(1);
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(2, { align: "start" });
  });

  it("ArrowUp while scrolled past active prompt scrolls current turn to top first", () => {
    // User is reading partway down a turn: scrolled below the active prompt's
    // top edge.  First ArrowUp should scroll the current turn back to the top
    // (navigate to activeIdx), NOT decrement to activeIdx - 1.
    const controller = createController(2, { isScrolledPast: true });
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(true);
    // Navigates to the SAME index (2), not the decrement (1).
    expect(controller.setIndex).toHaveBeenCalledWith(2);
    // userPromptIndices[2] = 4 → scroll that message to top.
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(4, { align: "start" });
  });

  it("ArrowUp from top-of-turn (not scrolled past) decrements to previous prompt", () => {
    // Opposite of the test above: user is already at the top of the active
    // turn.  ArrowUp should decrement to the previous prompt as usual.
    const controller = createController(2, { isScrolledPast: false });
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(true);
    expect(controller.setIndex).toHaveBeenCalledWith(1);
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(2, { align: "start" });
  });

  it("ArrowUp with caret mid-text does nothing", () => {
    setCaretAtOffset(editableEl, 5, "hello world");

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  it("ArrowUp at start of second line (not the very first position) does nothing", () => {
    // Multi-line editor: two paragraphs. Caret sits at offset 0 of the second
    // paragraph's text node — a plain focusOffset===0 check would incorrectly
    // consider this the "first position".
    editableEl.textContent = "";
    const line1 = document.createElement("div");
    line1.textContent = "first line";
    const line2 = document.createElement("div");
    line2.textContent = "second line";
    editableEl.appendChild(line1);
    editableEl.appendChild(line2);

    const range = document.createRange();
    range.setStart(line2.firstChild as Text, 0);
    range.collapse(true);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 3. Modifier keys are inert
  // -------------------------------------------------------------------------

  it.each([
    ["altKey", { altKey: true }],
    ["ctrlKey", { ctrlKey: true }],
    ["metaKey", { metaKey: true }],
    ["shiftKey", { shiftKey: true }],
  ] as const)("ArrowUp with %s does nothing", (_label, mods) => {
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp(mods));

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 4. Overlay / editable-outside guards
  // -------------------------------------------------------------------------

  it("does nothing while a dialog overlay is open", () => {
    const overlay = document.createElement("div");
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("data-state", "open");
    document.body.appendChild(overlay);

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("does nothing when focus is in an unrelated <input>", () => {
    const strayInput = document.createElement("input");
    document.body.appendChild(strayInput);
    strayInput.focus();

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("does nothing when focus is in an unrelated <textarea>", () => {
    const stray = document.createElement("textarea");
    document.body.appendChild(stray);
    stray.focus();

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  it("does nothing when focus is in an unrelated contenteditable", () => {
    const stray = document.createElement("div");
    // Both setAttribute and the DOM property — JSDOM doesn't always reflect
    // the attribute onto the `contentEditable` IDL property, and the hook
    // reads the property.
    stray.setAttribute("contenteditable", "true");
    stray.contentEditable = "true";
    stray.setAttribute("tabindex", "0");
    document.body.appendChild(stray);
    stray.focus();

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 5. Empty prompt list
  // -------------------------------------------------------------------------

  it("empty user prompt list: ArrowUp is a no-op", () => {
    const messages: ReadonlyArray<ChatMessage> = [makeMessage("a", ChatMessageRole.ASSISTANT)];
    const controller = createController(0);
    const { result, virtualizer } = render(messages, { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 6. Repeated ArrowUp cycles through prompts
  // -------------------------------------------------------------------------

  it("ArrowUp decrements the active cursor on each press", () => {
    const controller = createController(2);
    const { virtualizer } = render(buildMessages(), { controller });
    const scrollToIndex = virtualizer.scrollToIndex as ReturnType<typeof vi.fn>;

    act(() => dispatchArrowUp()); // 2 -> 1, scroll filteredMessages[2]
    act(() => dispatchArrowUp()); // 1 -> 0, scroll filteredMessages[0]

    // Two successful navigations.
    expect(scrollToIndex).toHaveBeenCalledTimes(2);
    expect(scrollToIndex).toHaveBeenNthCalledWith(1, 2, { align: "start" });
    expect(scrollToIndex).toHaveBeenNthCalledWith(2, 0, { align: "start" });

    expect(controller.setIndex).toHaveBeenNthCalledWith(1, 1);
    expect(controller.setIndex).toHaveBeenNthCalledWith(2, 0);
  });

  it("ArrowUp at active index 0 is a no-op", () => {
    const controller = createController(0);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 7. ArrowDown behavior
  // -------------------------------------------------------------------------

  it("ArrowDown when not navigating does nothing", () => {
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowDown());

    expect(result.current.isNavigating).toBe(false);
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(mockScrollToBottom).not.toHaveBeenCalled();
  });

  it("ArrowDown while navigating increments the cursor", () => {
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });
    const scrollToIndex = virtualizer.scrollToIndex as ReturnType<typeof vi.fn>;

    // Enter nav by pressing up once (2 -> 1).
    act(() => dispatchArrowUp());
    scrollToIndex.mockClear();

    // Now press down (1 -> 2).
    act(() => dispatchArrowDown());

    expect(result.current.isNavigating).toBe(true);
    expect(controller.setIndex).toHaveBeenLastCalledWith(2);
    // userPromptIndices[2] = 4 (the last USER in filteredMessages).
    expect(scrollToIndex).toHaveBeenCalledWith(4, { align: "start" });
  });

  it("ArrowDown past the last prompt exits navigation and scrolls to bottom", () => {
    const controller = createController(2);
    const { result } = render(buildMessages(), { controller });

    // Enter nav: 2 -> 1.
    act(() => dispatchArrowUp());
    // Back down: 1 -> 2.
    act(() => dispatchArrowDown());
    // One more down pushes past the last (length is 3 so idx 3 is out of range).
    act(() => dispatchArrowDown());

    expect(result.current.isNavigating).toBe(false);
    expect(mockScrollToBottom).toHaveBeenCalled();
    expect(mockSetIsSuppressed).toHaveBeenCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 8. Escape / Enter exit
  // -------------------------------------------------------------------------

  it("Escape while navigating exits, clears highlight, and re-focuses chat input", async () => {
    // Build DOM with a highlighted message so we can verify class removal.
    const wrapper = document.createElement("div");
    wrapper.setAttribute("data-index", "2");
    const item = document.createElement("div");
    item.setAttribute("data-testid", ElementIds.ALPHA_CHAT_MESSAGE);
    wrapper.appendChild(item);
    document.body.appendChild(wrapper);

    const controller = createController(2);
    const { result } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());
    await flushRaf(); // let applyHighlight add the class

    expect(item.classList.contains("alphaPromptHighlight")).toBe(true);

    // Move focus away so we can prove exitNavigation re-focuses.
    editableEl.blur();

    act(() => dispatchEscape());

    expect(result.current.isNavigating).toBe(false);
    expect(mockSetIsSuppressed).toHaveBeenLastCalledWith(false);
    expect(item.classList.contains("alphaPromptHighlight")).toBe(false);
    expect(document.activeElement).toBe(editableEl);
  });

  it("Enter while navigating exits the same as Escape", () => {
    const controller = createController(2);
    const { result } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());
    expect(result.current.isNavigating).toBe(true);

    act(() => dispatchEnter());

    expect(result.current.isNavigating).toBe(false);
    expect(mockSetIsSuppressed).toHaveBeenLastCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 9. External navigateToPrompt (dot rail click)
  // -------------------------------------------------------------------------

  it("navigateToPrompt(idx) enters navigation and drives the controller", () => {
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => result.current.navigateToPrompt(0));

    expect(result.current.isNavigating).toBe(true);
    expect(controller.setIndex).toHaveBeenCalledWith(0);
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(0, { align: "start" });
    expect(mockSetIsSuppressed).toHaveBeenCalledWith(true);
  });

  it("ArrowUp continues cycling after a navigateToPrompt() dot click", () => {
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });
    const scrollToIndex = virtualizer.scrollToIndex as ReturnType<typeof vi.fn>;

    // Simulate a dot click on prompt idx 2 (last). After this controller.ref
    // is 2 and focus has left the chat input, mirroring the real UI.
    act(() => result.current.navigateToPrompt(2));
    editableEl.blur();
    scrollToIndex.mockClear();

    // Now ArrowUp should still cycle (2 -> 1). Even though focus is no longer
    // in the chat input, the overlay/editable-outside guards don't block it
    // because body is the active element.
    act(() => dispatchArrowUp());

    expect(controller.setIndex).toHaveBeenLastCalledWith(1);
    expect(scrollToIndex).toHaveBeenCalledWith(2, { align: "start" });
  });

  // -------------------------------------------------------------------------
  // 10. Focus-in / shrinking message list
  // -------------------------------------------------------------------------

  it("focus-in on the chat input container while navigating exits navigation", () => {
    const controller = createController(2);
    const { result } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());
    expect(result.current.isNavigating).toBe(true);

    act(() => {
      chatInputContainer.dispatchEvent(new FocusEvent("focusin", { bubbles: true }));
    });

    expect(result.current.isNavigating).toBe(false);
    expect(mockSetIsSuppressed).toHaveBeenLastCalledWith(false);
  });

  // -------------------------------------------------------------------------
  // 11. navigateToPrompt bounds checking
  // -------------------------------------------------------------------------

  it("navigateToPrompt with a negative index is a no-op", () => {
    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => result.current.navigateToPrompt(-1));

    expect(result.current.isNavigating).toBe(false);
    expect(controller.setIndex).not.toHaveBeenCalled();
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
    expect(mockSetIsSuppressed).not.toHaveBeenCalled();
  });

  it("navigateToPrompt with an index past the last prompt is a no-op", () => {
    const controller = createController(0);
    const { result, virtualizer } = render(buildMessages(), { controller });

    // 3 user prompts → indices 0..2; 3 is out of range.
    act(() => result.current.navigateToPrompt(3));

    expect(result.current.isNavigating).toBe(false);
    expect(controller.setIndex).not.toHaveBeenCalled();
    expect(virtualizer.scrollToIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 12. Escape / Enter while NOT navigating are inert
  // -------------------------------------------------------------------------

  it("Escape while not navigating has no side effects", () => {
    const controller = createController(2);
    const { result } = render(buildMessages(), { controller });

    act(() => dispatchEscape());

    expect(result.current.isNavigating).toBe(false);
    // setIsSuppressed is called only by navigation transitions, never by a
    // bare Escape when we're not in nav.
    expect(mockSetIsSuppressed).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  it("Enter while not navigating has no side effects", () => {
    const controller = createController(2);
    const { result } = render(buildMessages(), { controller });

    act(() => dispatchEnter());

    expect(result.current.isNavigating).toBe(false);
    expect(mockSetIsSuppressed).not.toHaveBeenCalled();
    expect(controller.setIndex).not.toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 13. Unmount cleans up pending highlight rAF
  // -------------------------------------------------------------------------

  it("unmount cancels any pending highlight animation frame", () => {
    // Build DOM so applyHighlight has something to target.
    const wrapper = document.createElement("div");
    wrapper.setAttribute("data-index", "2");
    const item = document.createElement("div");
    item.setAttribute("data-testid", ElementIds.ALPHA_CHAT_MESSAGE);
    wrapper.appendChild(item);
    document.body.appendChild(wrapper);

    const cancelSpy = vi.spyOn(window, "cancelAnimationFrame");

    const controller = createController(2);
    const virtualizer = createMockVirtualizer();
    const { result, unmount } = renderHook(
      () => useAlphaPromptNav(buildMessages(), virtualizer, mockScrollToBottom, mockSetIsSuppressed, controller),
      {},
    );

    // Enter nav — schedules an rAF to apply the highlight class.
    act(() => dispatchArrowUp());
    expect(result.current.isNavigating).toBe(true);

    unmount();

    // Unmount path cancels the rAF we scheduled.
    expect(cancelSpy).toHaveBeenCalled();

    cancelSpy.mockRestore();
  });

  // -------------------------------------------------------------------------
  // 14. Radix popper wrapper treated as an open overlay
  // -------------------------------------------------------------------------

  it("ArrowUp still navigates turns while a Radix popper-content-wrapper is mounted", () => {
    // Tool/chip/subagent popovers must NOT block turn navigation — up/down
    // should always move between turns even when a popover is open. Only
    // role='dialog' modal overlays suppress navigation.
    const popperWrapper = document.createElement("div");
    popperWrapper.setAttribute("data-radix-popper-content-wrapper", "");
    document.body.appendChild(popperWrapper);

    const controller = createController(2);
    const { result, virtualizer } = render(buildMessages(), { controller });

    act(() => dispatchArrowUp());

    expect(result.current.isNavigating).toBe(true);
    expect(virtualizer.scrollToIndex).toHaveBeenCalled();
    expect(controller.setIndex).toHaveBeenCalled();
  });

  // -------------------------------------------------------------------------
  // 15. Highlight cleanup after unmount
  // -------------------------------------------------------------------------

  it("unmount leaves no highlight class on any message element", async () => {
    const wrapper = document.createElement("div");
    wrapper.setAttribute("data-index", "2");
    const item = document.createElement("div");
    item.setAttribute("data-testid", ElementIds.ALPHA_CHAT_MESSAGE);
    wrapper.appendChild(item);
    document.body.appendChild(wrapper);

    const controller = createController(2);
    const virtualizer = createMockVirtualizer();
    const { result, unmount } = renderHook(() =>
      useAlphaPromptNav(buildMessages(), virtualizer, mockScrollToBottom, mockSetIsSuppressed, controller),
    );

    act(() => dispatchArrowUp());
    await flushRaf();
    expect(result.current.isNavigating).toBe(true);
    expect(item.classList.contains("alphaPromptHighlight")).toBe(true);

    // Exit before unmount: ensures the highlight is cleaned up.
    act(() => dispatchEscape());
    expect(item.classList.contains("alphaPromptHighlight")).toBe(false);

    unmount();
    // Still no highlight anywhere in the DOM after tear-down.
    expect(document.querySelectorAll(".alphaPromptHighlight")).toHaveLength(0);
  });

  it("exits navigation when filteredMessages shrinks to no user prompts", () => {
    const controller = createController(2);
    const virtualizer = createMockVirtualizer();
    const { result, rerender, unmount } = renderHook(
      ({ msgs }) => useAlphaPromptNav(msgs, virtualizer, mockScrollToBottom, mockSetIsSuppressed, controller),
      { initialProps: { msgs: buildMessages() as ReadonlyArray<ChatMessage> } },
    );
    unmountHandles.push(unmount);

    act(() => dispatchArrowUp());
    expect(result.current.isNavigating).toBe(true);

    // Rerender with only an assistant message — no USER prompts left.
    rerender({ msgs: [makeMessage("a", ChatMessageRole.ASSISTANT)] });

    expect(result.current.isNavigating).toBe(false);
  });
});
