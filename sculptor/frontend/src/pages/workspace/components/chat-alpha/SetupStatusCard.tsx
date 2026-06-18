import { IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Pencil, Play, TerminalIcon } from "lucide-react";
import type { HTMLAttributes, ReactElement, ReactNode } from "react";
import { forwardRef } from "react";

import { ElementIds } from "~/api";
import { workspaceSetupStatusAtomFamily } from "~/common/state/atoms/workspaceSetupStatus";

import { SetupConfigPrompt } from "../SetupConfigPrompt";
import { useSetupCommandActions } from "../useSetupCommandActions";
import styles from "./SetupStatusCard.module.scss";

type SetupStatusCardProps = {
  workspaceId: string;
};

const SETUP_LABEL = "Setup";

// Render a multiline command on a single line by joining nonblank lines with
// `&&`. Matches the bash-tool-call convention of showing one command-shaped
// string in the header. Whitespace-only lines and trailing/leading blanks are
// dropped.
function joinCommandForHeader(command: string): string {
  const segments = command
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line.length > 0 && !line.startsWith("#"));
  if (segments.length === 0) return command.trim();
  return segments.join(" && ");
}

type SetupRowProps = {
  title: ReactNode;
  aside: ReactNode;
  testId?: string;
} & Omit<HTMLAttributes<HTMLDivElement>, "title">;

// Shared row shell that mirrors AlphaExpandedToolRow's
// `[icon] Label · [title] [aside]` layout but pulls icon size and
// typography from the chat-intro detail rows so this reads as the 5th
// header row in the AlphaChatIntro stack.
const SetupRow = forwardRef<HTMLDivElement, SetupRowProps>(({ title, aside, testId, className, ...rest }, ref) => {
  const classNames = [styles.row, styles.rowNoToggle];
  if (className) classNames.push(className);

  return (
    <div ref={ref} className={classNames.join(" ")} data-testid={testId} {...rest}>
      <span className={styles.rowLeading}>
        <TerminalIcon size={14} className={styles.rowIcon} aria-hidden="true" />
        <span className={styles.rowLabel}>{SETUP_LABEL}</span>
        <span className={styles.rowSeparator} aria-hidden="true">
          ·
        </span>
      </span>
      <span className={styles.rowTitle}>{title}</span>
      <span className={styles.rowAside}>{aside}</span>
    </div>
  );
});
SetupRow.displayName = "SetupRow";

const CommandTitle = ({ command }: { command: string }): ReactElement => (
  <>
    <span className={styles.rowPrompt} aria-hidden="true">
      $
    </span>{" "}
    {command}
  </>
);

/**
 * The pre-run setup affordance shown in the chat intro: a "configure a setup
 * command" CTA when none is set, or a one-click "Run setup" row when a command
 * exists but this workspace was created before it was configured.
 *
 * Once a run actually exists (pending/running/succeeded/failed/legacy) its
 * status is surfaced in the workspace banner (`WorkspaceSetupStatus`), not
 * here — setup is a workspace concern, not a per-agent one — so this returns
 * null for those states.
 */
export const SetupStatusCard = ({ workspaceId }: SetupStatusCardProps): ReactElement | null => {
  const status = useAtomValue(workspaceSetupStatusAtomFamily(workspaceId));
  const { currentCommand, handleRerun, handleEdit } = useSetupCommandActions(workspaceId);

  const editButton = (
    <Tooltip content="Edit command">
      <IconButton
        variant="ghost"
        size="1"
        data-testid={ElementIds.SETUP_EDIT_BUTTON}
        onClick={(e) => {
          e.stopPropagation();
          handleEdit();
        }}
        aria-label="Edit setup command"
      >
        <Pencil size={12} />
      </IconButton>
    </Tooltip>
  );

  if (status === null) {
    return <SetupConfigPrompt />;
  }

  // A run exists (pending/running/succeeded/failed/legacy): the banner owns it.
  if (status.status !== "not_configured") {
    return null;
  }

  // The workspace was created before a setup command was configured. If the
  // project now has one, offer a one-click Run; otherwise fall back to the
  // configure-CTA.
  if (currentCommand === null) {
    return <SetupConfigPrompt />;
  }

  const runHeader = joinCommandForHeader(currentCommand);
  return (
    <SetupRow
      testId="setup-status-card"
      title={
        <Tooltip content={currentCommand} side="bottom">
          <span>
            <CommandTitle command={runHeader} />
          </span>
        </Tooltip>
      }
      aside={
        <>
          <Tooltip content="Run setup">
            <IconButton
              variant="soft"
              size="1"
              data-testid="setup-run-button"
              onClick={(e) => {
                e.stopPropagation();
                void handleRerun();
              }}
              aria-label="Run setup"
            >
              <Play size={12} />
            </IconButton>
          </Tooltip>
          {editButton}
        </>
      }
    />
  );
};
