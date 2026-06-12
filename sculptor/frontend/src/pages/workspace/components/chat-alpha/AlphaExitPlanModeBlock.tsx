import { Badge } from "@radix-ui/themes";
import { useSetAtom } from "jotai";
import { ChevronRightIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import type { ToolUseBlock } from "~/api";
import { ElementIds } from "~/api";
import { useImbueParams, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { useTaskDetailWithDefaults } from "~/common/state/hooks/useTaskDetail";
import { openFileViewTabAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";

import styles from "./AlphaChatView.module.scss";
import { PulsingDot } from "./pill-animations";

const DISMISSED_ANSWER = "[Dismissed]";
const PLAN_APPROVAL_QUESTION = "Claude has finished planning. How would you like to proceed?";
const APPROVE_PLAN_ANSWER = "Approve plan";

export const AlphaExitPlanModeBlock = ({ toolBlock }: { toolBlock: ToolUseBlock }): ReactElement => {
  const { taskID } = useImbueParams();
  const { workspaceID } = useWorkspacePageParams();
  const { pendingUserQuestion, submittedQuestionAnswers } = useTaskDetailWithDefaults(taskID ?? "");
  const openFileViewTab = useSetAtom(openFileViewTabAtom);
  const [isExpanded, setIsExpanded] = useState(false);

  const isPending = pendingUserQuestion?.toolUseId === toolBlock.id;
  const matchingAnswers = submittedQuestionAnswers[toolBlock.id];

  // The plan file path now flows on the question payload (set by the backend
  // output processor when ExitPlanMode fires). Auto-open is event-driven via
  // openFileFromUiEventAtom; this lookup powers click-to-reopen across the
  // pending → answered → historical states.
  const planFilePath =
    pendingUserQuestion?.planFilePath ??
    submittedQuestionAnswers[toolBlock.id]?.questionData?.planFilePath ??
    undefined;

  useEffect(() => {
    if (matchingAnswers) setIsExpanded(true);
  }, [matchingAnswers]);

  const handleOpenPlanFile = useCallback((): void => {
    if (planFilePath) openFileViewTab({ workspaceId: workspaceID, filePath: planFilePath });
  }, [planFilePath, workspaceID, openFileViewTab]);

  if (isPending) {
    return (
      <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
        <div
          className={styles.toolHeader}
          onClick={planFilePath ? handleOpenPlanFile : undefined}
          style={{ cursor: planFilePath ? "pointer" : undefined }}
        >
          <PulsingDot />
          <span className={styles.toolName}>Plan ready for review</span>
        </div>
      </div>
    );
  }

  if (matchingAnswers) {
    const answerValue = matchingAnswers.answers[PLAN_APPROVAL_QUESTION] ?? "";
    const isDismissed = answerValue === DISMISSED_ANSWER;
    const isApproved = answerValue === APPROVE_PLAN_ANSWER;

    if (isApproved) {
      return (
        <div className={styles.planBlock} data-testid={ElementIds.EXIT_PLAN_MODE_TOOL_BLOCK}>
          <div
            className={styles.toolHeader}
            onClick={planFilePath ? handleOpenPlanFile : undefined}
            style={{ cursor: planFilePath ? "pointer" : undefined }}
          >
            <span className={styles.toolName}>Plan approved</span>
            <Badge size="1" variant="soft" color="green">
              Approved
            </Badge>
          </div>
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
          <div style={{ paddingLeft: "var(--space-4)", paddingTop: "var(--space-1)" }}>
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
        className={styles.toolHeader}
        onClick={planFilePath ? handleOpenPlanFile : undefined}
        style={{ cursor: planFilePath ? "pointer" : undefined }}
      >
        <span className={styles.toolName}>Plan reviewed</span>
      </div>
    </div>
  );
};
