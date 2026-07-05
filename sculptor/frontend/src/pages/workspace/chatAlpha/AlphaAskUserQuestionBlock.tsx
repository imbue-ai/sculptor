import { Badge } from "@radix-ui/themes";
import type { ReactElement } from "react";

import type { SubmittedQuestionAnswers, ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import { useAgentDetailWithDefaults } from "~/common/state/hooks/useAgentDetail";
import { splitAnswerIntoParts } from "~/pages/workspace/chatAlpha/utils/askUserQuestion";

import styles from "./AlphaAskUserQuestionBlock.module.scss";
import { useChatAgent } from "./ChatAgentContext.tsx";

const DISMISSED_ANSWER = "[Dismissed]";

type Question = {
  question: string;
  options: Array<{ label: string; description: string }>;
};

/** Text-only options list for answered questions — no form controls. */
const AnsweredOptionsList = ({
  question,
  selectedOptions,
  customText,
}: {
  question: Question;
  selectedOptions: Array<string>;
  customText: string;
}): ReactElement => {
  const selectedSet = new Set(selectedOptions);
  return (
    <ul className={styles.optionsList}>
      {question.options.map((opt) => {
        const isSelected = selectedSet.has(opt.label);
        return (
          <li
            key={opt.label}
            className={isSelected ? styles.optionItemSelected : styles.optionItem}
            data-testid={ElementIds.ASK_USER_QUESTION_ANSWERED_OPTION}
            data-selected={isSelected}
          >
            <span
              className={styles.optionLabel}
              data-testid={isSelected ? ElementIds.ASK_USER_QUESTION_ANSWER_TEXT : undefined}
            >
              {opt.label}
            </span>
            {opt.description && <span>: {opt.description}</span>}
          </li>
        );
      })}
      {customText && (
        <li className={styles.optionItemSelected} data-testid={ElementIds.ASK_USER_QUESTION_CUSTOM_TEXT}>
          <span className={styles.optionLabel} data-testid={ElementIds.ASK_USER_QUESTION_ANSWER_TEXT}>
            {customText}
          </span>
        </li>
      )}
    </ul>
  );
};

/** Options list for dismissed questions — same bullet style as answered, all dimmed. */
const DismissedOptionsList = ({ question }: { question: Question }): ReactElement => (
  <ul className={styles.optionsList}>
    {question.options.map((opt) => (
      <li key={opt.label} className={styles.optionItem}>
        <span className={styles.optionLabel}>{opt.label}</span>
        {opt.description && <span>: {opt.description}</span>}
      </li>
    ))}
  </ul>
);

export const AlphaAskUserQuestionBlock = ({ toolBlock }: { toolBlock: ToolUseBlock }): ReactElement => {
  // The owning chat panel's agent — `toolBlock.id` lives in that agent's
  // transcript, so the answers lookup must use the same agent.
  const { agentId } = useChatAgent();
  const { submittedQuestionAnswers } = useAgentDetailWithDefaults(agentId);

  const matchingAnswers: SubmittedQuestionAnswers | undefined = submittedQuestionAnswers[toolBlock.id];

  if (!matchingAnswers) return <div data-testid={ElementIds.ASK_USER_QUESTION_TOOL_BLOCK} />;

  const isDismissed = Object.values(matchingAnswers.answers).every((a) => a === DISMISSED_ANSWER);

  return (
    <div className={styles.inlineContent} data-testid={ElementIds.ASK_USER_QUESTION_TOOL_BLOCK}>
      {isDismissed && (
        <Badge size="1" color="gray" variant="soft" className={styles.dismissedBadge}>
          DISMISSED
        </Badge>
      )}
      {matchingAnswers.questionData.questions.map((question, index) => {
        const answerText = matchingAnswers.answers[question.question] ?? "";
        const isDismissedAnswer = answerText === DISMISSED_ANSWER;
        const { selectedOptions, customText } = splitAnswerIntoParts(answerText, question.options);
        return (
          <div key={question.question}>
            {index > 0 && <hr className={styles.divider} />}
            <div className={styles.entry}>
              <div className={styles.entryHeader}>
                <span className={styles.entryLabel} data-testid={ElementIds.ASK_USER_QUESTION_TEXT}>
                  {question.question}
                </span>
              </div>
              {!isDismissedAnswer && question.options.length > 0 && (
                <AnsweredOptionsList question={question} selectedOptions={selectedOptions} customText={customText} />
              )}
              {!isDismissedAnswer && question.options.length === 0 && answerText && (
                <pre className={styles.entryBody} data-testid={ElementIds.ASK_USER_QUESTION_ANSWER_TEXT}>
                  {answerText}
                </pre>
              )}
              {isDismissedAnswer && question.options.length > 0 && <DismissedOptionsList question={question} />}
            </div>
          </div>
        );
      })}
    </div>
  );
};
