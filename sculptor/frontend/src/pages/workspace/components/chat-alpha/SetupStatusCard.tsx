import { Anchor as PopoverAnchor } from "@radix-ui/react-popover";
import { IconButton, Popover, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Pencil, Play, RotateCcw, Square, TerminalIcon } from "lucide-react";
import type { CSSProperties, HTMLAttributes, KeyboardEvent, ReactElement, ReactNode } from "react";
import { forwardRef, useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { resolveWorkspaceSetupCommand } from "~/common/setupDefaults";
import { workspaceSetupOutputAtomFamily } from "~/common/state/atoms/workspaceSetupOutput";
import { workspaceSetupStatusAtomFamily } from "~/common/state/atoms/workspaceSetupStatus";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings";
import { useProject } from "~/common/state/hooks/useProjects";
import { useWorkspace } from "~/common/state/hooks/useWorkspace";

import { SetupConfigPrompt } from "../SetupConfigPrompt";
import bashStyles from "./bashBlockStyles.module.scss";
import type { BashBlockState } from "./BashStatusBadge";
import { BashStatusBadge } from "./BashStatusBadge";
import { formatDuration } from "./durationUtils";
import { useCloseOnChatScroll } from "./hooks/useChatScroll";
import styles from "./SetupStatusCard.module.scss";

type SetupStatusCardProps = {
  workspaceId: string;
};

const SETUP_LABEL = "Setup";
const POPOVER_STYLE: CSSProperties = {
  maxHeight: 380,
  overflow: "hidden",
  padding: 0,
};

const postNoBody = async (path: string): Promise<Response> => fetch(path, { method: "POST" });

function useElapsedSinceStart(startedAt: number | null, isRunning: boolean): string {
  const [now, setNow] = useState<number>(() => Date.now() / 1000);
  useEffect(() => {
    if (!isRunning) return;
    const id = setInterval(() => {
      setNow(Date.now() / 1000);
    }, 100);
    return (): void => clearInterval(id);
  }, [isRunning]);
  if (startedAt === null) return "0.0s";
  return formatDuration(Math.max(0, now - startedAt));
}

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
  isOpen?: boolean;
  isError?: boolean;
  interactive?: boolean;
  testId?: string;
} & Omit<HTMLAttributes<HTMLDivElement>, "title">;

// Shared row shell that mirrors AlphaExpandedToolRow's
// `[icon] Label · [title] [aside]` layout but pulls icon size and
// typography from the chat-intro detail rows so this reads as the 5th
// header row in the AlphaChatIntro stack.
//
// forwardRef + props passthrough lets the surrounding code attach a ref
// (used as the popover anchor) and event handlers (click / keydown to
// toggle the popover) without SetupRow having to know about either.
const SetupRow = forwardRef<HTMLDivElement, SetupRowProps>(
  ({ title, aside, isOpen = false, isError = false, interactive = false, testId, className, ...rest }, ref) => {
    const classNames = [styles.row];
    if (isOpen) classNames.push(styles.rowOpen);
    if (isError) classNames.push(styles.rowError);
    if (!interactive) classNames.push(styles.rowNoToggle);
    if (className) classNames.push(className);

    return (
      <div
        ref={ref}
        className={classNames.join(" ")}
        role={interactive ? "button" : undefined}
        aria-haspopup={interactive ? "dialog" : undefined}
        aria-expanded={interactive ? isOpen : undefined}
        tabIndex={interactive ? 0 : undefined}
        data-testid={testId}
        {...rest}
      >
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
  },
);
SetupRow.displayName = "SetupRow";

const CommandTitle = ({ command }: { command: string }): ReactElement => (
  <>
    <span className={styles.rowPrompt} aria-hidden="true">
      $
    </span>{" "}
    {command}
  </>
);

export const SetupStatusCard = ({ workspaceId }: SetupStatusCardProps): ReactElement | null => {
  const status = useAtomValue(workspaceSetupStatusAtomFamily(workspaceId));
  const output = useAtomValue(workspaceSetupOutputAtomFamily(workspaceId));
  const workspace = useWorkspace(workspaceId);
  const project = useProject(workspace?.projectId ?? "");
  const openSettings = useOpenSettings();
  const popoverOutputRef = useRef<HTMLDivElement | null>(null);
  const rowRef = useRef<HTMLDivElement | null>(null);
  const [isPopoverOpen, setIsPopoverOpen] = useState<boolean>(false);
  // Dismiss on chat scroll for consistency with the other chat popovers.
  const closeOnScroll = useCallback((): void => setIsPopoverOpen(false), []);
  useCloseOnChatScroll(closeOnScroll, isPopoverOpen);
  const togglePopover = useCallback(() => setIsPopoverOpen((prev) => !prev), []);
  const handleRowKeyDown = useCallback((e: KeyboardEvent<HTMLDivElement>): void => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      setIsPopoverOpen((prev) => !prev);
    }
  }, []);
  const isRunning = status?.status === "running";
  const startedAt = typeof status?.startedAt === "number" ? status.startedAt : null;
  const finishedAt = typeof status?.finishedAt === "number" ? status.finishedAt : null;
  const isLogTruncated = status?.logTruncated === true;
  const liveElapsed = useElapsedSinceStart(startedAt, isRunning);

  // While the popover is open during a run, autoscroll new chunks into view.
  useEffect(() => {
    if (popoverOutputRef.current && isPopoverOpen && isRunning) {
      popoverOutputRef.current.scrollTop = popoverOutputRef.current.scrollHeight;
    }
  }, [output?.text, isPopoverOpen, isRunning]);

  const handleCancel = useCallback(async () => {
    try {
      await postNoBody(`/api/v1/workspaces/${workspaceId}/setup/cancel`);
    } catch (err) {
      console.error("Failed to cancel setup:", err);
    }
  }, [workspaceId]);

  const handleRerun = useCallback(async () => {
    try {
      await postNoBody(`/api/v1/workspaces/${workspaceId}/setup/rerun`);
    } catch (err) {
      console.error("Failed to rerun setup:", err);
    }
  }, [workspaceId]);

  const handleEdit = useCallback((): void => {
    if (project?.objectId) {
      openSettings("repositories", project.objectId);
    } else {
      openSettings("repositories");
    }
  }, [project?.objectId, openSettings]);

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

  // Mirror the backend's tri-state resolution: a null stored value runs the
  // current default ("git fetch origin ..."), an empty string means the user
  // cleared it (run nothing), any other string is custom.
  const currentCommand = resolveWorkspaceSetupCommand(project?.workspaceSetupCommand);

  if (status === null) {
    return <SetupConfigPrompt />;
  }

  // The workspace was created before a setup command was configured. If the
  // project now has one, offer a one-click Run; otherwise fall back to the
  // configure-CTA.
  if (status.status === "not_configured") {
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
  }

  // "Migrated" workspaces are terminal-state rows backfilled from the legacy
  // PTY-based setup path. They have no recorded run_id and no captured
  // command — falling through to the project's current command would
  // misleadingly imply we know what actually ran. Show a placeholder
  // instead, matching the synthetic-output placeholder in the popover.
  const isMigrated =
    (status.status === "succeeded" || status.status === "failed" || status.status === "legacy") &&
    (status.runId === null || status.runId === undefined);

  // Command resolution priority:
  // 1) the persisted command that ran for this workspace (workspace.setupCommand) —
  //    shows "what was run", which may differ from the project's current setting
  // 2) project.workspaceSetupCommand (current value) — only used pre-run, while
  //    we have not yet persisted what we ran (e.g. status="pending")
  // 3) literal "workspace setup" placeholder (or "(command not recorded)" for
  //    migrated rows where we genuinely don't know what ran)
  const persistedCommand =
    typeof workspace?.setupCommand === "string" && workspace.setupCommand.length > 0 ? workspace.setupCommand : null;
  const commandRan = persistedCommand ?? (isMigrated ? null : currentCommand);
  const commandHeader = commandRan
    ? joinCommandForHeader(commandRan)
    : isMigrated
      ? "(command not recorded)"
      : "workspace setup";
  const titleNode = commandRan ? (
    <Tooltip content={commandRan} side="bottom">
      <span>
        <CommandTitle command={commandHeader} />
      </span>
    </Tooltip>
  ) : (
    <span className={styles.rowPlaceholder}>{commandHeader}</span>
  );

  if (status.status === "pending") {
    // The queued card carries the same `setup-status-card` testid as the
    // interactive (popover-opening) card it becomes once the run starts, but
    // while pending it renders inert — no row click handler. `aria-disabled`
    // makes that transient gap honest: the framework's actionability contract
    // holds a click until the card turns interactive, instead of dispatching it
    // onto the inert row where it is silently dropped (SCU-1215). The early
    // `not_configured`/`legacy` rows are deliberately left alone — they render
    // as plain, non-interactive divs (no role, default cursor) and do not
    // misrepresent themselves, and gating them would also disable the Run/Edit
    // buttons nested inside the same row.
    return (
      <SetupRow
        testId="setup-status-card"
        aria-disabled
        title={titleNode}
        aside={
          <>
            <span className={`${bashStyles.badge} ${bashStyles.badgeRunning}`} data-testid="setup-status-badge">
              queued
            </span>
            {editButton}
          </>
        }
      />
    );
  }

  let badgeState: BashBlockState;
  let badgeDuration: string;
  if (status.status === "running") {
    badgeState = "executing";
    badgeDuration = liveElapsed;
  } else if (status.status === "succeeded") {
    badgeState = "completed";
    badgeDuration = durationBetween(startedAt, finishedAt);
  } else if (status.status === "failed") {
    badgeState = "error";
    badgeDuration = durationBetween(startedAt, finishedAt);
  } else {
    badgeState = "completed";
    badgeDuration = "previous";
  }

  const shouldShowLog = status.status !== "legacy";
  const rawLogText = output?.text ?? "";
  // Prefix the body with "Exit code N\n" on failure, matching how Sculptor's
  // bash tool calls render their popover (success → no prefix; failure →
  // exit code at the top, then output). Stderr is already merged into the
  // captured stream by the runner, so it appears inline like in a terminal.
  const exitCodePrefix =
    status.status === "failed" && typeof status.exitCode === "number" ? `Exit code ${status.exitCode}\n` : "";
  const logText = `${exitCodePrefix}${rawLogText}`;
  // The card is clickable to open the popover for any non-legacy run.
  // Commands that produce no stdout (e.g. the default
  // `git fetch origin 2>/dev/null || true`) still benefit from a
  // popover so the user can confirm the run finished and see the
  // empty-output placeholder, rather than the row silently going inert.
  const canOpenPopover = shouldShowLog;
  const hasLogText = logText.length > 0;
  const hasCommandChanged = persistedCommand !== null && currentCommand !== null && persistedCommand !== currentCommand;
  // Rerun is gated on the project having a command — the backend reads it from
  // `project.workspace_setup_command` and 422s when blank, so an unguarded
  // button would silently no-op when the user has cleared the setting.
  const isRerunVisible =
    (status.status === "succeeded" || status.status === "failed" || status.status === "legacy") &&
    currentCommand !== null;

  const aside = (
    <>
      <BashStatusBadge state={badgeState} isBackground={false} duration={badgeDuration} testId="setup-status-badge" />
      {isRunning ? (
        <Tooltip content="Cancel setup">
          <IconButton
            variant="ghost"
            size="1"
            data-testid="setup-cancel-button"
            onClick={(e) => {
              e.stopPropagation();
              void handleCancel();
            }}
            aria-label="Cancel setup"
          >
            <Square size={12} />
          </IconButton>
        </Tooltip>
      ) : null}
      {isRerunVisible && (
        <Tooltip content={hasCommandChanged ? "Rerun setup (command has changed)" : "Rerun setup"}>
          <IconButton
            variant={hasCommandChanged ? "soft" : "ghost"}
            color={hasCommandChanged ? "amber" : undefined}
            size="1"
            data-testid="setup-rerun-button"
            data-command-changed={hasCommandChanged ? "true" : "false"}
            onClick={(e) => {
              e.stopPropagation();
              void handleRerun();
            }}
            aria-label={hasCommandChanged ? "Rerun setup (command has changed)" : "Rerun setup"}
          >
            <RotateCcw size={12} />
          </IconButton>
        </Tooltip>
      )}
      {editButton}
    </>
  );

  const isError = status.status === "failed";

  if (!canOpenPopover) {
    return <SetupRow testId="setup-status-card" isError={isError} title={titleNode} aside={aside} />;
  }

  // Use PopoverAnchor + the row's own onClick instead of Popover.Trigger.
  // Trigger composes its toggle handler via Radix Slot, which has been
  // unreliable here (likely due to the action IconButtons inside the row
  // interfering with the trigger's event composition / focus management
  // on subsequent opens). The anchor pattern is what AlphaToolPillRow
  // uses and works cleanly: the row owns its click, and
  // onPointerDownOutside keeps clicks inside the row from auto-closing
  // before our click handler runs.
  return (
    <Popover.Root open={isPopoverOpen} onOpenChange={setIsPopoverOpen}>
      <PopoverAnchor asChild>
        <SetupRow
          ref={rowRef}
          testId="setup-status-card"
          isOpen={isPopoverOpen}
          isError={isError}
          interactive
          title={titleNode}
          aside={aside}
          onClick={togglePopover}
          onKeyDown={handleRowKeyDown}
        />
      </PopoverAnchor>
      <Popover.Content
        side="bottom"
        sideOffset={4}
        align="start"
        collisionPadding={16}
        className={bashStyles.popoverContent}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => {
          // Clicks inside the row should not auto-close the popover — let
          // the row's own onClick toggle it (or the action IconButtons
          // handle their own behavior).
          if (rowRef.current?.contains(e.target as Node)) e.preventDefault();
        }}
        style={POPOVER_STYLE}
      >
        <div className={bashStyles.popover}>
          <div className={bashStyles.popoverSection}>
            <span className={bashStyles.popoverCommand}>
              <span className={bashStyles.prompt}>$</span> {commandRan ?? commandHeader}
              <div className={bashStyles.popoverSummary}>workspace setup command</div>
            </span>
          </div>
          {isLogTruncated && (
            <div className={styles.truncationBanner} data-testid="setup-status-truncation">
              Output was truncated. Showing first and last portions.
            </div>
          )}
          <div className={bashStyles.popoverSection}>
            <div ref={popoverOutputRef} className={bashStyles.popoverBody} data-testid="setup-status-output">
              {hasLogText ? logText : <span className={styles.popoverEmpty}>(no output)</span>}
              {isRunning && <span className={bashStyles.streamCursor} />}
            </div>
          </div>
        </div>
      </Popover.Content>
    </Popover.Root>
  );
};

function durationBetween(startedAt: number | null, finishedAt: number | null): string {
  if (startedAt === null || finishedAt === null) return "";
  return formatDuration(Math.max(0, finishedAt - startedAt));
}
