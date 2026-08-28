import { Badge, Button, Checkbox, Flex, IconButton, Radio, Text } from "@radix-ui/themes";
import { useAtom } from "jotai";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

import type { AskUserQuestionData } from "~/api";
import { ElementIds } from "~/api";
import { useFocusOnMountIfUnclaimed } from "~/common/hooks/useFocusOnMountIfUnclaimed";
import { useKeybinding } from "~/common/keybindings/useKeybinding.ts";
import { draftQuestionStateAtomFamily, EMPTY_DRAFT_QUESTION_STATE } from "~/common/state/atoms/agentDetails";
import { mergeClasses } from "~/common/utils/classNames";
import { optional } from "~/common/utils/optional";
import { MarkdownBlock } from "~/components/MarkdownBlock";
import { useModifiedEnter } from "~/pages/workspace/hooks/useModifiedEnter";
import { useTimedLatch } from "~/pages/workspace/hooks/useTimedLatch.ts";
import { ResizeHandle } from "~/pages/workspace/layout/ResizeHandle.tsx";

import styles from "./AskUserQuestion.module.scss";

const OTHER_OPTION_LABEL = "Provide an alternative";
const OTHER_PLACEHOLDER = "Provide an alternative";

// Submitting answers locks the button immediately, but the spinner only appears
// once the submit has stayed in flight this long (a slow backend); a normal
// submit resolves well under this, so the common case shows no spinner. There's
// no trailing hold — the panel unmounts on success, and on failure the button
// should re-enable at once.
const SUBMIT_SPINNER_START_DELAY_MS = 1_000;

// A tall question caps the panel at this fraction of the viewport by default and
// scrolls its body, so the chat above stays readable and the footer stays
// reachable. The drag handle overrides the cap between MIN_PANEL_CAP_PX and
// whatever height the chat column can spare above the panel.
const DEFAULT_PANEL_CAP_FRACTION = 0.55;
const MIN_PANEL_CAP_PX = 140;
const MIN_CHAT_ABOVE_PX = 96;
// Horizontal gap the "N more" pill keeps from the footer buttons before it
// stops centering and deflects left to clear them.
const MORE_PILL_GAP_PX = 12;

type AskUserQuestionProps = {
  agentId: string;
  questionData: AskUserQuestionData;
  // May be async; `handleSubmit` awaits it to drive the in-flight state.
  onSubmit: (answers: Record<string, string>, notes: Record<string, string>) => void | Promise<void>;
  onDismiss?: () => void;
};

/** Convert a Record to a Map. */
const recordToMap = <TV,>(record: Record<string, TV>): Map<string, TV> => new Map(Object.entries(record));

/** Convert a Record of arrays to a Map of Sets. */
const recordToMapOfSets = (record: Record<string, Array<string>>): Map<string, Set<string>> =>
  new Map(Object.entries(record).map(([k, v]) => [k, new Set(v)]));

export const AskUserQuestion = ({ agentId, questionData, onSubmit, onDismiss }: AskUserQuestionProps): ReactElement => {
  const { questions } = questionData;
  const [rawDraftState, setDraftState] = useAtom(draftQuestionStateAtomFamily(agentId));

  // If the stored draft belongs to a different question batch, discard it.
  const draftState = rawDraftState.toolUseId === questionData.toolUseId ? rawDraftState : EMPTY_DRAFT_QUESTION_STATE;

  const [currentIndex, setCurrentIndex] = useState(draftState.currentIndex);
  const [answers, setAnswers] = useState<Map<string, string>>(() => recordToMap(draftState.answers));
  const [otherTexts, setOtherTexts] = useState<Map<string, string>>(() => recordToMap(draftState.otherTexts));
  const [otherSelected, setOtherSelected] = useState<Map<string, boolean>>(() => recordToMap(draftState.otherSelected));
  // For multi-select, track which predefined options are selected
  const [multiSelections, setMultiSelections] = useState<Map<string, Set<string>>>(() =>
    recordToMapOfSets(draftState.multiSelections),
  );
  const [focusedOptionIndex, setFocusedOptionIndex] = useState(0);
  // Reset the focused option whenever the active question changes. Adjusting
  // state during render (with a previous-value guard) avoids the stale frame
  // an effect would produce.
  const [prevIndexForFocus, setPrevIndexForFocus] = useState(currentIndex);
  if (prevIndexForFocus !== currentIndex) {
    setPrevIndexForFocus(currentIndex);
    setFocusedOptionIndex(0);
  }
  const otherInputRef = useRef<HTMLTextAreaElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const scrollBodyRef = useRef<HTMLDivElement>(null);
  const footerRef = useRef<HTMLDivElement>(null);
  const buttonsRef = useRef<HTMLDivElement>(null);
  const morePillRef = useRef<HTMLButtonElement>(null);
  const sendMessageBinding = useKeybinding("send_message");

  // Height cap the drag handle sets, in px; null keeps the CSS default cap.
  const [panelCapPx, setPanelCapPx] = useState<number | null>(null);
  // The panel only shows the resize handle once its content is tall enough to be
  // worth resizing (i.e. it would otherwise cap-and-scroll).
  const [isResizable, setIsResizable] = useState(false);
  // Count of options not fully in view; null hides the footer "N more" cue.
  const [moreCount, setMoreCount] = useState<number | null>(null);
  // Current panel height and its max, in px, reported as the resize handle's
  // aria-value* range for assistive tech.
  const [resizeRange, setResizeRange] = useState({ now: 0, max: 0 });

  // True while the answer POST is in flight. Drives the disabled state (instant
  // lock). The ref is the actual re-entrancy guard: setState is async, so a fast
  // second click or Enter would slip past a state-only check and submit twice.
  const [isSubmitting, setIsSubmitting] = useState(false);
  const isSubmittingRef = useRef(false);
  // Gate the spinner through a start-delay latch so only slow submits show it.
  const shouldShowSubmitSpinner = useTimedLatch(isSubmitting, 0, SUBMIT_SPINNER_START_DELAY_MS);

  const currentQuestion = questions[currentIndex];
  const isMultiSelect = currentQuestion.multiSelect;
  const questionKey = currentQuestion.question;

  const totalOptions = currentQuestion.options.length + 1; // +1 for "Other"

  // Focus the container on mount, but only if no element currently has
  // focus.  When this panel replaces the chat input, the browser drops
  // focus to <body> as the input unmounts, so we inherit focus naturally.
  // If the user had focused something else (e.g. the terminal), it stays.
  useFocusOnMountIfUnclaimed(containerRef);

  // Focus the "Other" input when it's selected
  useEffect(() => {
    if (otherSelected.get(questionKey)) {
      otherInputRef.current?.focus();
    }
  }, [otherSelected, questionKey]);

  // Sync form state back to the Jotai atom so it survives navigation
  useEffect(() => {
    setDraftState({
      toolUseId: questionData.toolUseId,
      currentIndex,
      answers: Object.fromEntries(answers),
      otherTexts: Object.fromEntries(otherTexts),
      otherSelected: Object.fromEntries(otherSelected),
      multiSelections: Object.fromEntries(Array.from(multiSelections.entries()).map(([k, v]) => [k, Array.from(v)])),
    });
  }, [questionData.toolUseId, currentIndex, answers, otherTexts, otherSelected, multiSelections, setDraftState]);

  // Auto-resize the textarea when content changes
  const autoResizeTextarea = useCallback(() => {
    const textarea = otherInputRef.current;
    if (textarea) {
      textarea.style.height = "auto";
      textarea.style.height = `${textarea.scrollHeight}px`;
    }
  }, []);

  useEffect(() => {
    autoResizeTextarea();
  }, [otherTexts, questionKey, autoResizeTextarea]);

  const updateAnswer = useCallback((key: string, value: string) => {
    setAnswers((prev) => {
      const next = new Map(prev);
      next.set(key, value);
      return next;
    });
  }, []);

  const handleOptionClick = useCallback(
    (optionLabel: string) => {
      if (isMultiSelect) {
        setMultiSelections((prev) => {
          const next = new Map(prev);
          const current = new Set(next.get(questionKey) ?? []);
          if (current.has(optionLabel)) {
            current.delete(optionLabel);
          } else {
            current.add(optionLabel);
          }
          next.set(questionKey, current);

          // Rebuild the answer string from selected predefined options + Other
          const parts: Array<string> = [...current];
          const isOtherSel = otherSelected.get(questionKey);
          const otherText = otherTexts.get(questionKey) ?? "";
          if (isOtherSel && otherText) {
            parts.push(otherText);
          }
          updateAnswer(questionKey, parts.join(", "));
          return next;
        });
      } else {
        // Single-select: deselect Other, set this option
        setOtherSelected((prev) => {
          const next = new Map(prev);
          next.set(questionKey, false);
          return next;
        });
        updateAnswer(questionKey, optionLabel);
      }
    },
    [isMultiSelect, questionKey, otherSelected, otherTexts, updateAnswer],
  );

  const handleOtherClick = useCallback(() => {
    if (isMultiSelect) {
      setOtherSelected((prev) => {
        const next = new Map(prev);
        const isPreviouslySelected = next.get(questionKey) ?? false;
        next.set(questionKey, !isPreviouslySelected);

        // Rebuild answer
        const selectedOptions = multiSelections.get(questionKey) ?? new Set();
        const parts: Array<string> = [...selectedOptions];
        const otherText = otherTexts.get(questionKey) ?? "";
        if (!isPreviouslySelected && otherText) {
          parts.push(otherText);
        }
        updateAnswer(questionKey, parts.join(", "));
        return next;
      });
    } else {
      setOtherSelected((prev) => {
        const next = new Map(prev);
        next.set(questionKey, true);
        return next;
      });
      const otherText = otherTexts.get(questionKey) ?? "";
      updateAnswer(questionKey, otherText);
    }
  }, [isMultiSelect, questionKey, multiSelections, otherTexts, updateAnswer]);

  const handleOtherTextChange = useCallback(
    (text: string) => {
      setOtherTexts((prev) => {
        const next = new Map(prev);
        next.set(questionKey, text);
        return next;
      });

      if (isMultiSelect) {
        const selectedOptions = multiSelections.get(questionKey) ?? new Set();
        const parts: Array<string> = [...selectedOptions];
        if (text) {
          parts.push(text);
        }
        updateAnswer(questionKey, parts.join(", "));
      } else {
        updateAnswer(questionKey, text);
      }
    },
    [isMultiSelect, questionKey, multiSelections, updateAnswer],
  );

  const isOptionSelected = useCallback(
    (optionLabel: string): boolean => {
      if (isMultiSelect) {
        const selected = multiSelections.get(questionKey);
        return selected?.has(optionLabel) ?? false;
      }
      const isOtherSel = otherSelected.get(questionKey) ?? false;
      if (isOtherSel) return false;
      return answers.get(questionKey) === optionLabel;
    },
    [isMultiSelect, questionKey, multiSelections, otherSelected, answers],
  );

  const isOtherCurrentlySelected = otherSelected.get(questionKey) ?? false;

  const hasAnswer = useCallback(
    (q: (typeof questions)[number]) => {
      const answer = answers.get(q.question);
      return answer !== undefined && answer !== "";
    },
    [answers],
  );

  const isAllAnswered = questions.every(hasAnswer);

  const hasUnansweredElsewhere = questions.some((q, i) => i !== currentIndex && !hasAnswer(q));

  const navigateToNextUnanswered = useCallback(() => {
    setCurrentIndex((prev) => {
      // Search forward from current, wrapping around
      for (let offset = 1; offset <= questions.length; offset++) {
        const i = (prev + offset) % questions.length;
        if (!hasAnswer(questions[i])) {
          return i;
        }
      }
      return prev;
    });
    containerRef.current?.focus();
  }, [questions, hasAnswer]);

  const handleSubmit = useCallback(async () => {
    if (!isAllAnswered) return;
    // Ignore re-entrant submits while a POST is already in flight (e.g. a second
    // Enter on a slow backend) so the same answers can't be submitted twice.
    if (isSubmittingRef.current) return;
    // Build the per-question `notes` map: whenever the user typed freeform
    // text in the "Other" textarea (and Other is selected), surface that
    // text as a separate annotation. The backend formatter renders it as
    // ` user notes: <text>` after the answer string, matching the native
    // AskUserQuestion CLI's `annotations.notes` field.
    const notes: Record<string, string> = {};
    for (const question of questions) {
      const key = question.question;
      if (otherSelected.get(key)) {
        const otherText = otherTexts.get(key) ?? "";
        if (otherText) {
          notes[key] = otherText;
        }
      }
    }
    isSubmittingRef.current = true;
    setIsSubmitting(true);
    try {
      await onSubmit(Object.fromEntries(answers), notes);
    } finally {
      // On success the panel unmounts (the WebSocket clears the pending
      // question), so this is moot; on failure it re-enables the button so the
      // user can retry. React ignores a state update on an unmounted component,
      // so this needs no is-mounted guard.
      isSubmittingRef.current = false;
      setIsSubmitting(false);
    }
  }, [isAllAnswered, answers, questions, otherSelected, otherTexts, onSubmit]);

  const handleModifiedEnter = useModifiedEnter({
    onConfirm: handleSubmit,
    sendMessageBinding,
  });

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      // The resize handle is a focusable separator nested in this container; let
      // it own its keys (arrows resize it). Only Escape still bubbles up here to
      // dismiss the panel.
      if ((e.target as HTMLElement).getAttribute("role") === "separator" && e.key !== "Escape") {
        return;
      }

      // Tab/Shift+Tab navigate between questions with wrap-around
      if (e.key === "Tab" && questions.length > 1) {
        e.preventDefault();
        if (e.shiftKey) {
          setCurrentIndex((i) => (i - 1 + questions.length) % questions.length);
        } else {
          setCurrentIndex((i) => (i + 1) % questions.length);
        }
        containerRef.current?.focus();
        return;
      }

      if (document.activeElement === otherInputRef.current) {
        if (e.key === "Escape") {
          // Escape from textarea blurs back to container, does NOT dismiss
          e.preventDefault();
          e.stopPropagation();
          containerRef.current?.focus();
          return;
        }

        if (e.key === "ArrowUp") {
          e.preventDefault();
          setFocusedOptionIndex((prev) => (prev - 1 + totalOptions) % totalOptions);
          containerRef.current?.focus();
          return;
        }

        if (handleModifiedEnter(e.nativeEvent)) {
          e.preventDefault();
        }
        return;
      }

      switch (e.key) {
        case "ArrowDown":
          e.preventDefault();
          setFocusedOptionIndex((prev) => (prev + 1) % totalOptions);
          break;

        case "ArrowUp":
          e.preventDefault();
          setFocusedOptionIndex((prev) => (prev - 1 + totalOptions) % totalOptions);
          break;

        case "ArrowRight":
          e.preventDefault();
          setCurrentIndex((i) => (i + 1) % questions.length);
          break;

        case "ArrowLeft":
          e.preventDefault();
          setCurrentIndex((i) => (i - 1 + questions.length) % questions.length);
          break;

        case "Enter":
        case " ":
          e.preventDefault();
          if (focusedOptionIndex < currentQuestion.options.length) {
            handleOptionClick(currentQuestion.options[focusedOptionIndex].label);
          } else {
            // "Other" option
            handleOtherClick();
          }
          break;

        case "Escape":
          e.preventDefault();
          if (onDismiss) {
            onDismiss();
          }
          break;

        default:
          // Check for submit shortcut (cmd-enter)
          if (handleModifiedEnter(e.nativeEvent)) {
            e.preventDefault();
          }
          break;
      }
    },
    [
      totalOptions,
      questions.length,
      focusedOptionIndex,
      currentQuestion.options,
      handleOptionClick,
      handleOtherClick,
      onDismiss,
      handleModifiedEnter,
    ],
  );

  // Place the footer "N more" pill: centered in the panel, deflecting left only
  // as far as needed to clear the buttons, and top-aligned with them.
  const positionMorePill = useCallback((): void => {
    const footer = footerRef.current;
    const buttons = buttonsRef.current;
    const pill = morePillRef.current;
    if (!footer || !buttons || !pill) return;
    const footerRect = footer.getBoundingClientRect();
    const buttonsRect = buttons.getBoundingClientRect();
    const pillWidth = pill.offsetWidth;
    let left = (footerRect.width - pillWidth) / 2;
    const maxLeft = buttonsRect.left - footerRect.left - MORE_PILL_GAP_PX - pillWidth;
    if (left > maxLeft) {
      left = Math.max(0, maxLeft);
    }
    pill.style.left = `${left}px`;
    pill.style.top = `${buttonsRect.top - footerRect.top}px`;
  }, []);

  // Largest cap that still leaves a slice of chat visible above the panel.
  const getMaxPanelCap = useCallback((): number => {
    const chatColumn = containerRef.current?.parentElement;
    const available = chatColumn ? chatColumn.getBoundingClientRect().height : window.innerHeight;
    return Math.max(MIN_PANEL_CAP_PX, available - MIN_CHAT_ABOVE_PX);
  }, []);

  // Update the resize affordance and the "N more" cue from the body's scroll
  // geometry. scrollHeight is the content height (independent of the cap), so the
  // resize handle stays put while dragging; moreCount reflects the live scroll.
  const recomputeScrollCue = useCallback((): void => {
    const body = scrollBodyRef.current;
    const card = cardRef.current;
    if (!body) return;
    setIsResizable(body.scrollHeight > window.innerHeight * DEFAULT_PANEL_CAP_FRACTION + 4);
    if (card) {
      const now = Math.round(card.getBoundingClientRect().height);
      const max = Math.round(getMaxPanelCap());
      setResizeRange((prev) => (prev.now === now && prev.max === max ? prev : { now, max }));
    }
    const isOverflowing = body.scrollHeight > body.clientHeight + 2;
    const isAtBottom = body.scrollTop + body.clientHeight >= body.scrollHeight - 2;
    if (!isOverflowing || isAtBottom) {
      setMoreCount(null);
      return;
    }
    const bodyBottom = body.getBoundingClientRect().bottom;
    const optionEls = body.querySelectorAll(
      `[data-testid="${ElementIds.ASK_USER_QUESTION_OPTION}"],[data-testid="${ElementIds.ASK_USER_QUESTION_OTHER_OPTION}"]`,
    );
    let hidden = 0;
    optionEls.forEach((el) => {
      if (el.getBoundingClientRect().bottom > bodyBottom - 2) hidden += 1;
    });
    setMoreCount((prev) => (prev === hidden ? prev : hidden));
  }, [getMaxPanelCap]);

  useEffect(() => {
    const body = scrollBodyRef.current;
    const card = cardRef.current;
    if (!body || !card) return;
    recomputeScrollCue();
    const onScroll = (): void => recomputeScrollCue();
    body.addEventListener("scroll", onScroll, { passive: true });
    const resizeObserver = new ResizeObserver(() => {
      recomputeScrollCue();
      positionMorePill();
    });
    resizeObserver.observe(card);
    const onWindowResize = (): void => {
      recomputeScrollCue();
      positionMorePill();
    };
    window.addEventListener("resize", onWindowResize);
    return (): void => {
      body.removeEventListener("scroll", onScroll);
      resizeObserver.disconnect();
      window.removeEventListener("resize", onWindowResize);
    };
  }, [recomputeScrollCue, positionMorePill, currentIndex]);

  // Re-place the pill once it mounts or its label width changes.
  useLayoutEffect(() => {
    if (moreCount !== null) positionMorePill();
  }, [moreCount, positionMorePill]);

  // Keep the keyboard-focused option in view as arrows move through a long list.
  useEffect(() => {
    const body = scrollBodyRef.current;
    if (!body) return;
    const optionEls = body.querySelectorAll(
      `[data-testid="${ElementIds.ASK_USER_QUESTION_OPTION}"],[data-testid="${ElementIds.ASK_USER_QUESTION_OTHER_OPTION}"]`,
    );
    (optionEls[focusedOptionIndex] as HTMLElement | undefined)?.scrollIntoView({ block: "nearest" });
  }, [focusedOptionIndex]);

  const getPanelHeight = useCallback((): number => cardRef.current?.getBoundingClientRect().height ?? 0, []);

  // Clamp a proposed panel height and store it as the card's max-height cap.
  const handlePanelResize = useCallback(
    (nextPx: number): void => {
      setPanelCapPx(Math.min(getMaxPanelCap(), Math.max(MIN_PANEL_CAP_PX, nextPx)));
    },
    [getMaxPanelCap],
  );

  const scrollBodyDown = useCallback((): void => {
    const body = scrollBodyRef.current;
    if (!body) return;
    body.scrollBy({ top: body.clientHeight * 0.85, behavior: "smooth" });
  }, []);

  const shouldShowNavigation = questions.length > 1;

  const renderIndicator = (isChecked: boolean): ReactElement =>
    isMultiSelect ? (
      <span className={styles.indicator}>
        <Checkbox size="1" variant="surface" checked={isChecked} tabIndex={-1} />
      </span>
    ) : (
      <span className={styles.indicator}>
        <Radio size="1" variant="surface" checked={isChecked} value="" tabIndex={-1} />
      </span>
    );

  return (
    <div
      ref={containerRef}
      className={styles.container}
      data-testid={ElementIds.ASK_USER_QUESTION_PANEL}
      tabIndex={0}
      onKeyDown={handleKeyDown}
    >
      {isResizable && (
        <ResizeHandle
          axis="y"
          direction={-1}
          getSize={getPanelHeight}
          onResize={handlePanelResize}
          ariaValueNow={resizeRange.now}
          ariaValueMin={MIN_PANEL_CAP_PX}
          ariaValueMax={resizeRange.max}
          ariaLabel="Resize question panel"
          className={styles.resizeHandle}
          data-testid={ElementIds.ASK_USER_QUESTION_RESIZE_HANDLE}
        />
      )}
      <div
        ref={cardRef}
        className={styles.card}
        style={panelCapPx != null ? { maxHeight: `${panelCapPx}px` } : undefined}
      >
        {/* Pinned header */}
        <Flex align="center" gap="2" className={styles.header}>
          <Badge size="1" variant="surface" className={styles.headerChip}>
            {currentQuestion.header}
          </Badge>
          {shouldShowNavigation && (
            <Text size="1" className={styles.questionCounter}>
              Question {currentIndex + 1} of {questions.length}
            </Text>
          )}
        </Flex>

        {/* Scrollable body: the question scrolls together with the options */}
        <div className={styles.scrollBody} ref={scrollBodyRef}>
          <div className={styles.questionText} data-testid={ElementIds.ASK_USER_QUESTION_TEXT}>
            <MarkdownBlock content={currentQuestion.question} />
          </div>

          <div className={styles.optionsList}>
            {currentQuestion.options.map((option, index) => (
              <div
                key={option.label}
                className={mergeClasses(
                  styles.optionItem,
                  optional(isOptionSelected(option.label), styles.selected),
                  optional(focusedOptionIndex === index, styles.focused),
                )}
                onMouseDown={(e) => {
                  e.preventDefault();
                  setFocusedOptionIndex(index);
                  handleOptionClick(option.label);
                }}
                data-testid={ElementIds.ASK_USER_QUESTION_OPTION}
              >
                {renderIndicator(isOptionSelected(option.label))}
                <div className={styles.optionText}>
                  <span className={styles.optionTextBold}>{option.label}</span>
                  {option.description && (
                    <span className={styles.optionDescription}>
                      : <MarkdownBlock content={option.description} />
                    </span>
                  )}
                </div>
              </div>
            ))}

            {/* Other option - "Provide an alternative" */}
            <div
              className={mergeClasses(
                styles.optionItem,
                optional(isOtherCurrentlySelected, styles.selected),
                optional(focusedOptionIndex === currentQuestion.options.length, styles.focused),
              )}
              onMouseDown={(e) => {
                if (e.target !== otherInputRef.current) {
                  e.preventDefault();
                }
                setFocusedOptionIndex(currentQuestion.options.length);
                handleOtherClick();
              }}
              data-testid={ElementIds.ASK_USER_QUESTION_OTHER_OPTION}
            >
              {renderIndicator(isOtherCurrentlySelected)}
              {isOtherCurrentlySelected ? (
                <textarea
                  ref={otherInputRef}
                  className={styles.otherInput}
                  placeholder={OTHER_PLACEHOLDER}
                  value={otherTexts.get(questionKey) ?? ""}
                  rows={1}
                  onChange={(e) => {
                    handleOtherTextChange(e.target.value);
                    autoResizeTextarea();
                  }}
                  onClick={(e) => e.stopPropagation()}
                  data-testid={ElementIds.ASK_USER_QUESTION_OTHER_INPUT}
                />
              ) : (
                <Text className={styles.otherLabel}>{currentQuestion.otherLabel ?? OTHER_OPTION_LABEL}</Text>
              )}
            </div>
          </div>
        </div>

        {/* Pinned footer */}
        <div className={styles.footer} ref={footerRef}>
          {moreCount !== null && (
            <Button
              type="button"
              ref={morePillRef}
              size="1"
              variant="soft"
              color="gray"
              className={styles.morePill}
              data-testid={ElementIds.ASK_USER_QUESTION_MORE_PILL}
              onClick={scrollBodyDown}
              tabIndex={-1}
            >
              {moreCount > 0 ? `${moreCount} more` : "More"} <span aria-hidden>↓</span>
            </Button>
          )}
          {shouldShowNavigation ? (
            <Flex align="center" gap="3">
              <div className={styles.navigation}>
                <IconButton
                  size="1"
                  variant="ghost"
                  onClick={() => setCurrentIndex((i) => (i - 1 + questions.length) % questions.length)}
                  data-testid={ElementIds.ASK_USER_QUESTION_PREVIOUS_BUTTON}
                >
                  <ChevronLeft size={16} />
                </IconButton>
                <div className={styles.dots}>
                  {questions.map((q, i) => {
                    const isAnswered = hasAnswer(q);
                    const isActive = i === currentIndex;
                    return (
                      <div
                        key={q.question}
                        className={mergeClasses(
                          styles.dot,
                          optional(isActive, styles.activeDot),
                          optional(isAnswered, styles.answeredDot),
                        )}
                        onClick={() => setCurrentIndex(i)}
                      >
                        {isAnswered && <Check size={isActive ? 12 : 10} strokeWidth={3} />}
                      </div>
                    );
                  })}
                </div>
                <IconButton
                  size="1"
                  variant="ghost"
                  onClick={() => setCurrentIndex((i) => (i + 1) % questions.length)}
                  data-testid={ElementIds.ASK_USER_QUESTION_NEXT_BUTTON}
                >
                  <ChevronRight size={16} />
                </IconButton>
              </div>
            </Flex>
          ) : (
            <div />
          )}
          <Flex gap="3" align="center" ref={buttonsRef}>
            {onDismiss && (
              <Button
                variant="ghost"
                color="gray"
                onClick={onDismiss}
                data-testid={ElementIds.ASK_USER_QUESTION_DISMISS_BUTTON}
              >
                Dismiss
              </Button>
            )}
            {!hasUnansweredElsewhere ? (
              <Button
                className={styles.submitButton}
                disabled={!isAllAnswered || isSubmitting}
                loading={shouldShowSubmitSpinner}
                onClick={handleSubmit}
                data-testid={ElementIds.ASK_USER_QUESTION_SUBMIT}
                {...(shouldShowSubmitSpinner ? { "data-loading": "true" } : {})}
              >
                Submit
              </Button>
            ) : (
              <Button
                className={styles.nextButton}
                onClick={navigateToNextUnanswered}
                data-testid={ElementIds.ASK_USER_QUESTION_SUBMIT}
              >
                Next
              </Button>
            )}
          </Flex>
        </div>
      </div>
    </div>
  );
};
