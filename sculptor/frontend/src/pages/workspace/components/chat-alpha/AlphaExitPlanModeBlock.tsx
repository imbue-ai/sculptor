import { Badge } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import { ChevronRightIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import type { ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import { useTaskDetailWithDefaults } from "~/common/state/hooks/useTaskDetail";
import { MarkdownBlock } from "~/components/MarkdownBlock";
import { openFileViewTabAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";

import styles from "./AlphaChatView.module.scss";
import { useChatTask } from "./ChatTaskContext.tsx";
import { PulsingDot } from "./pill-animations";

const DISMISSED_ANSWER = "[Dismissed]";
const APPROVE_PLAN_ANSWER = "Approve plan";

export const AlphaExitPlanModeBlock = ({ toolBlock }: { toolBlock: ToolUseBlock }): ReactElement => {
  // The owning chat panel's agent — the pending-question and answer lookups
  // must resolve against the agent whose transcript holds this block.
  const { workspaceId: workspaceID, taskId: taskID } = useChatTask();
  const { pendingUserQuestion, submittedQuestionAnswers } = useTaskDetailWithDefaults(taskID);
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const [isExpanded, setIsExpanded] = useState(false);

  const isPending = pendingUserQuestion?.toolUseId === toolBlock.id;
  const matchingAnswers = submittedQuestionAnswers[toolBlock.id];

  // The plan file path now flows on the question payload (set by the backend
  // output processor when ExitPlanMode fires). Auto-open is event-driven via
  // openFileFromUiEventAtom; this lookup powers click-to-reopen across the
  // pending → answered → historical states.
  const planFilePath = pendingUserQuestion?.planFilePath ?? matchingAnswers?.questionData?.planFilePath;

  useEffect(() => {
    if (matchingAnswers) setIsExpanded(true);
  }, [matchingAnswers]);

  const handleOpenPlanFile = useCallback((): void => {
    if (planFilePath) openFileViewTab({ workspaceId: workspaceID, filePath: planFilePath });
  }, [planFilePath, workspaceID, openFileViewTab]);

  // Harnesses that present the plan inline (e.g. pi) pass it as the tool's
  // `plan` argument rather than writing a plan file; render it here so the user
  // can actually read the plan. Harnesses with a plan file (Claude) keep the
  // click-to-open link instead.
  const planText = typeof toolBlock.input?.plan === "string" ? toolBlock.input.plan : undefined;
  const planContent =
    planText && !planFilePath ? (
      <div className={styles.planInlineContent}>
        <MarkdownBlock content={planText} />
      </div>
    ) : null;

  if (isPending) {
    return (
      <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
        <div
          className={planFilePath ? `${styles.toolHeader} ${styles.planHeaderClickable}` : styles.toolHeader}
          onClick={planFilePath ? handleOpenPlanFile : undefined}
        >
          <PulsingDot />
          <span className={styles.toolName}>Plan ready for review</span>
        </div>
        {planContent}
      </div>
    );
  }

  if (matchingAnswers) {
    // Look the answer up by the question's OWN stored text (it varies by harness)
    // rather than a hardcoded string, so historical plan turns resolve too.
    const planQuestion = matchingAnswers.questionData.questions[0]?.question ?? "";
    const answerValue = matchingAnswers.answers[planQuestion] ?? "";
    const isDismissed = answerValue === DISMISSED_ANSWER;
    const isApproved = answerValue === APPROVE_PLAN_ANSWER;

    if (isApproved) {
      return (
        <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
          <div
            className={planFilePath ? `${styles.toolHeader} ${styles.planHeaderClickable}` : styles.toolHeader}
            onClick={planFilePath ? handleOpenPlanFile : undefined}
          >
            <span className={styles.toolName}>Plan approved</span>
            <Badge size="1" variant="soft" color="green">
              Approved
            </Badge>
          </div>
          {planContent}
        </div>
      );
    }

    if (isDismissed) {
      return (
        <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
          <div className={styles.toolHeader}>
            <span className={styles.toolName}>Plan review dismissed</span>
            <Badge size="1" variant="soft" color="gray">
              Dismissed
            </Badge>
          </div>
        </div>
      );
    }

    // Revision state
    return (
      <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
        <div
          className={styles.toolHeader}
          onClick={(): void => setIsExpanded((prev) => !prev)}
          role="button"
          tabIndex={0}
          onKeyDown={(e): void => {
            if (e.key === "Enter" || e.key === " ") setIsExpanded((prev) => !prev);
          }}
        >
          <ChevronRightIcon size={12} className={isExpanded ? styles.chevronOpen : styles.chevronClosed} />
          <span className={styles.toolName}>Plan revision requested</span>
          <Badge size="1" variant="soft" color="orange">
            Revision
          </Badge>
        </div>
        {isExpanded && (
          <div className={styles.planRevisionDetail}>
            <span>{answerValue}</span>
          </div>
        )}
      </div>
    );
  }

  // Historical state
  return (
    <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
      <div
        className={planFilePath ? `${styles.toolHeader} ${styles.planHeaderClickable}` : styles.toolHeader}
        onClick={planFilePath ? handleOpenPlanFile : undefined}
      >
        <span className={styles.toolName}>Plan reviewed</span>
      </div>
      {planContent}
    </div>
  );
};
