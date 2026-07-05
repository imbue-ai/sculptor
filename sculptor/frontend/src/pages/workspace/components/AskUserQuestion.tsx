import { Badge, Button, Checkbox, Flex, IconButton, Radio, Text } from "@radix-ui/themes";
import { useAtom } from "jotai";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { AskUserQuestionData } from "~/api";
import { ElementIds } from "~/api";
import { useTimedLatch } from "~/common/Hooks.ts";
import { useFocusOnMountIfUnclaimed } from "~/common/hooks/useFocusOnMountIfUnclaimed";
import { useKeybinding } from "~/common/keybindings/hooks.ts";
import { useModifiedEnter } from "~/common/ShortcutUtils";
import { draftQuestionStateAtomFamily, EMPTY_DRAFT_QUESTION_STATE } from "~/common/state/atoms/taskDetails";
import { mergeClasses, optional } from "~/common/Utils";
import { MarkdownBlock } from "~/components/MarkdownBlock";

import styles from "./AskUserQuestion.module.scss";

const OTHER_OPTION_LABEL = "Provide an alternative";
const OTHER_PLACEHOLDER = "Provide an alternative";

// Submitting answers locks the button immediately, but the spinner only appears
// once the submit has stayed in flight this long (a slow backend); a normal
// submit resolves well under this, so the common case shows no spinner. There's
// no trailing hold — the panel unmounts on success, and on failure the button
// should re-enable at once.
const SUBMIT_SPINNER_START_DELAY_MS = 1_000;

type AskUserQuestionProps = {
  taskId: string;
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

export const AskUserQuestion = ({ taskId, questionData, onSubmit, onDismiss }: AskUserQuestionProps): ReactElement => {
  const { questions } = questionData;
  const [rawDraftState, setDraftState] = useAtom(draftQuestionStateAtomFamily(taskId));

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
  const sendMessageBinding = useKeybinding("send_message");

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
      <div className={styles.card}>
        {/* Header chip and question */}
        <Flex direction="column" gap="2" align="start">
          <Flex align="center" gap="2">
            <Badge size="1" variant="surface" className={styles.headerChip}>
              {currentQuestion.header}
            </Badge>
            {shouldShowNavigation && (
              <Text size="1" className={styles.questionCounter}>
                Question {currentIndex + 1} of {questions.length}
              </Text>
            )}
          </Flex>
          <div className={styles.questionText} data-testid={ElementIds.ASK_USER_QUESTION_TEXT}>
            <MarkdownBlock content={currentQuestion.question} />
          </div>
        </Flex>

        {/* Options */}
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

        {/* Footer: navigation + submit */}
        <div className={styles.footer}>
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
          <Flex gap="3" align="center">
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
