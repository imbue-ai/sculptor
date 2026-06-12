import type { Virtualizer } from "@tanstack/react-virtual";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage } from "~/api";
import { ChatMessageRole, ElementIds } from "~/api";
import { CHAT_INPUT_ELEMENT_ID } from "~/common/Constants.ts";

import type { ActivePromptIndex } from "./useAlphaActivePromptIndex.ts";

const HIGHLIGHT_CLASS = "alphaPromptHighlight";

/** Cancel a pending rAF tracked in the ref and reset it. */
const cancelRaf = (ref: React.MutableRefObject<number | null>): void => {
  if (ref.current !== null) {
    cancelAnimationFrame(ref.current);
    ref.current = null;
  }
};

/** Returns true when a modal dialog is open. Tool/chip/subagent popovers
 *  intentionally do not block turn navigation — up/down should always move
 *  between turns even when a popover is showing. */
const isOverlayOpen = (): boolean => document.querySelector('[role="dialog"][data-state="open"]') !== null;

/**
 * Returns true when the AskUserQuestion panel is mounted. The panel has its
 * own ArrowUp/ArrowDown handler for moving the focused option, so prompt nav
 * must not compete for those keys while it is showing.
 */
const isAskUserQuestionOpen = (): boolean =>
  document.querySelector(`[data-testid="${ElementIds.ASK_USER_QUESTION_PANEL}"]`) !== null;

/** Returns true when focus is in an editable element that is not the chat input. */
const isOtherEditableFocused = (inputContainer: HTMLElement | null): boolean => {
  const active = document.activeElement as HTMLElement | null;
  if (active === null) return false;
  if (inputContainer?.contains(active)) return false;
  return active.tagName === "INPUT" || active.tagName === "TEXTAREA" || active.contentEditable === "true";
};

/**
 * Returns true when the current selection is a collapsed caret sitting at the
 * very first DOM position of `container`. A plain `focusOffset === 0` check
 * is not enough (the caret can be at offset 0 of line 2 of a multi-line
 * editor) and a text-length check is not enough either (an empty leading
 * paragraph above a code block contributes zero characters, which would let
 * a caret inside the code block be misclassified as "very start"). We walk
 * up from the caret toward the container, requiring the position at every
 * level to be offset 0 of the first child — only then is the caret truly
 * at the start of the editor.
 */
const isCaretAtVeryStart = (container: HTMLElement): boolean => {
  const selection = window.getSelection();
  if (!selection || !selection.isCollapsed || selection.rangeCount === 0) return false;
  const range = selection.getRangeAt(0);
  if (!container.contains(range.startContainer)) return false;
  let node: Node = range.startContainer;
  let offset = range.startOffset;
  while (node !== container) {
    if (offset !== 0) return false;
    const parent: Node | null = node.parentNode;
    if (parent === null || parent.firstChild !== node) return false;
    node = parent;
    offset = 0;
  }
  return true;
};

type UseAlphaPromptNavReturn = {
  isNavigating: boolean;
  exitNavigation: () => void;
  /** Navigate to the prompt at the given index into userPromptIndices. */
  navigateToPrompt: (promptIdx: number) => void;
  /** Indices into filteredMessages that are user prompts, in order. */
  userPromptIndices: ReadonlyArray<number>;
};

export const useAlphaPromptNav = (
  filteredMessages: ReadonlyArray<ChatMessage>,
  virtualizer: Virtualizer<HTMLDivElement, Element>,
  scrollToBottom: () => void,
  setIsSuppressed: (val: boolean) => void,
  activePromptIndex?: ActivePromptIndex,
  isNavigatingRef?: React.MutableRefObject<boolean>,
): UseAlphaPromptNavReturn => {
  // Raw setter is wrapped below (`setIsNavigating`) to keep the external ref
  // in sync synchronously; the pair-naming lint rule is not applicable.
  // eslint-disable-next-line react/hook-use-state
  const [isNavigating, setIsNavigatingState] = useState(false);
  const highlightRafRef = useRef<number | null>(null);

  // Route the (possibly-undefined) controller methods through a ref so every
  // useCallback below has stable deps even though the parent re-creates the
  // `activePromptIndex` object on every render.
  const controllerRef = useRef(activePromptIndex);
  controllerRef.current = activePromptIndex;
  const fallbackActiveRef = useRef(-1);
  const activeRef = activePromptIndex?.ref ?? fallbackActiveRef;
  const setActiveIndex = useCallback((i: number): void => {
    controllerRef.current?.setIndex(i);
  }, []);
  const isScrolledPastActive = useCallback((): boolean => {
    return controllerRef.current?.isScrolledPastActive() ?? false;
  }, []);

  // Sync the shared ref synchronously so other hooks' render-time reads see
  // the new value in the same React render that triggered the state change.
  const setIsNavigating = useCallback(
    (val: boolean): void => {
      if (isNavigatingRef !== undefined) isNavigatingRef.current = val;
      setIsNavigatingState(val);
    },
    [isNavigatingRef],
  );

  // Build array of indices into filteredMessages that are user prompts
  const userPromptIndices = useMemo(
    () =>
      filteredMessages.reduce<Array<number>>((acc, msg, idx) => {
        if (msg.role === ChatMessageRole.USER) acc.push(idx);
        return acc;
      }, []),
    [filteredMessages],
  );

  const removeHighlight = useCallback((): void => {
    const highlighted = document.querySelectorAll(`.${HIGHLIGHT_CLASS}`);
    highlighted.forEach((el) => el.classList.remove(HIGHLIGHT_CLASS));
  }, []);

  const applyHighlight = useCallback(
    (messageIndex: number): void => {
      removeHighlight();
      cancelRaf(highlightRafRef);
      // The virtualizer's scrollToIndex queues a render — the target element
      // typically isn't in the DOM until after the browser commits. We wait
      // one frame so the virtualizer has materialized the row, then query
      // and tag it. Mirrors the pattern used by usePromptHighlight.
      highlightRafRef.current = requestAnimationFrame(() => {
        highlightRafRef.current = null;
        const items = document.querySelectorAll(`[data-testid="${ElementIds.ALPHA_CHAT_MESSAGE}"]`);
        for (const item of items) {
          const wrapper = item.closest(`[data-index="${messageIndex}"]`);
          if (wrapper) {
            item.classList.add(HIGHLIGHT_CLASS);
            break;
          }
        }
      });
    },
    [removeHighlight],
  );

  const focusChatInput = useCallback((): void => {
    const inputContainer = document.getElementById(CHAT_INPUT_ELEMENT_ID);
    const editable = inputContainer?.querySelector("[contenteditable]") as HTMLElement | null;
    editable?.focus();
  }, []);

  const exitNavigation = useCallback((): void => {
    setIsNavigating(false);
    cancelRaf(highlightRafRef);
    removeHighlight();
    setIsSuppressed(false);
    focusChatInput();
  }, [removeHighlight, setIsSuppressed, focusChatInput, setIsNavigating]);

  const navigateToPrompt = useCallback(
    (promptIdx: number): void => {
      if (promptIdx < 0 || promptIdx >= userPromptIndices.length) return;
      // Drive the shared active-index cursor so the dot rail and keyboard nav
      // are always in sync.
      setActiveIndex(promptIdx);
      setIsNavigating(true);
      // Disengage auto-scroll whether triggered by keyboard or dot rail.
      setIsSuppressed(true);
      const messageIndex = userPromptIndices[promptIdx];
      virtualizer.scrollToIndex(messageIndex, { align: "start" });
      applyHighlight(messageIndex);
    },
    [userPromptIndices, virtualizer, applyHighlight, setIsSuppressed, setActiveIndex, setIsNavigating],
  );

  // Exit navigation if messages shrink to no user prompts (e.g. agent switch)
  useEffect(() => {
    if (isNavigating && userPromptIndices.length === 0) exitNavigation();
  }, [isNavigating, userPromptIndices, exitNavigation]);

  // Cancel pending highlight rAF on unmount
  useEffect(() => {
    return (): void => cancelRaf(highlightRafRef);
  }, []);

  // Exit navigation when the input regains focus (e.g. user clicks back on it).
  // This prevents isSuppressed from staying true and blocking scroll-to-top.
  useEffect(() => {
    if (!isNavigating) return;
    const inputContainer = document.getElementById(CHAT_INPUT_ELEMENT_ID);
    if (!inputContainer) return;

    const handleFocusIn = (): void => exitNavigation();
    inputContainer.addEventListener("focusin", handleFocusIn);
    return (): void => inputContainer.removeEventListener("focusin", handleFocusIn);
  }, [isNavigating, exitNavigation]);

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent): void => {
      if (isOverlayOpen()) return;
      if (isAskUserQuestionOpen()) return;
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;

      const inputContainer = document.getElementById(CHAT_INPUT_ELEMENT_ID);
      const isInputFocused = !!inputContainer?.contains(document.activeElement);
      if (isOtherEditableFocused(inputContainer)) return;

      if (e.key === "ArrowUp") {
        if (userPromptIndices.length === 0) return;

        // Entering from the input requires the caret to be at the very first
        // position of the editor so we don't hijack normal cursor movement
        // inside a multi-line input.
        if (!isNavigating && isInputFocused) {
          const editable = inputContainer?.querySelector("[contenteditable]") as HTMLElement | null;
          if (!editable || !isCaretAtVeryStart(editable)) return;
        }

        const currentIdx = activeRef.current;

        // If the user has scrolled past the active prompt's top (they're
        // reading partway down a turn), the first ArrowUp scrolls the current
        // turn back to the top rather than jumping to the previous prompt.
        if (currentIdx >= 0 && currentIdx < userPromptIndices.length && isScrolledPastActive()) {
          e.preventDefault();
          if (isInputFocused) (document.activeElement as HTMLElement | null)?.blur();
          navigateToPrompt(currentIdx);
          return;
        }

        const newIdx = currentIdx - 1;
        if (newIdx < 0) return;
        e.preventDefault();
        if (isInputFocused) (document.activeElement as HTMLElement | null)?.blur();
        navigateToPrompt(newIdx);
        return;
      }

      if (e.key === "ArrowDown") {
        if (!isNavigating) return;

        e.preventDefault();
        const newIdx = activeRef.current + 1;
        if (newIdx >= userPromptIndices.length) {
          // Past last prompt: exit navigation and snap to bottom.
          exitNavigation();
          scrollToBottom();
          return;
        }
        navigateToPrompt(newIdx);
        return;
      }

      if (isNavigating && (e.key === "Escape" || e.key === "Enter")) {
        e.preventDefault();
        exitNavigation();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return (): void => window.removeEventListener("keydown", handleKeyDown);
  }, [
    isNavigating,
    userPromptIndices,
    activeRef,
    navigateToPrompt,
    exitNavigation,
    scrollToBottom,
    isScrolledPastActive,
  ]);

  return { isNavigating, exitNavigation, navigateToPrompt, userPromptIndices };
};
