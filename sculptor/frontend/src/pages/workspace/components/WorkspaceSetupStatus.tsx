import { Anchor as PopoverAnchor } from "@radix-ui/react-popover";
import { IconButton, Popover, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Pencil, RotateCcw, Square, TerminalIcon } from "lucide-react";
import type { CSSProperties, KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { workspaceSetupOutputAtomFamily } from "~/common/state/atoms/workspaceSetupOutput";
import { workspaceSetupStatusAtomFamily } from "~/common/state/atoms/workspaceSetupStatus";

import bashStyles from "./chat-alpha/bashBlockStyles.module.scss";
import type { BashBlockState } from "./chat-alpha/BashStatusBadge";
import { BashStatusBadge } from "./chat-alpha/BashStatusBadge";
import { formatDuration } from "./chat-alpha/durationUtils";
import { useSetupCommandActions } from "./useSetupCommandActions";
import styles from "./WorkspaceSetupStatus.module.scss";

type WorkspaceSetupStatusProps = {
  workspaceId: string;
};

const SETUP_LABEL = "Setup";
const POPOVER_STYLE: CSSProperties = {
  maxHeight: 380,
  overflow: "hidden",
  padding: 0,
};

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

function durationBetween(startedAt: number | null, finishedAt: number | null): string {
  if (startedAt === null || finishedAt === null) return "";
  return formatDuration(Math.max(0, finishedAt - startedAt));
}

/**
 * The workspace setup command's run status, as a compact segment in the
 * WorkspaceBanner. Setup is a workspace concern shared by every agent in the
 * workspace (one run per workspace, gated on workspace state — not agent
 * type), so it lives in workspace-level chrome rather than the per-agent chat
 * intro or terminal panel.
 *
 * Renders only once a run exists (pending/running/succeeded/failed/legacy);
 * the `null`/`not_configured` onboarding CTA lives in the chat intro
 * (`SetupStatusCard`). The pill carries the badge and the inline
 * cancel/rerun/edit actions; clicking it opens a popover with the command and
 * captured log.
 */
export const WorkspaceSetupStatus = ({ workspaceId }: WorkspaceSetupStatusProps): ReactElement | null => {
  const status = useAtomValue(workspaceSetupStatusAtomFamily(workspaceId));
  const output = useAtomValue(workspaceSetupOutputAtomFamily(workspaceId));
  const { workspace, currentCommand, handleCancel, handleRerun, handleEdit } = useSetupCommandActions(workspaceId);

  const popoverOutputRef = useRef<HTMLDivElement | null>(null);
  const pillRef = useRef<HTMLSpanElement | null>(null);
  const [isPopoverOpen, setIsPopoverOpen] = useState<boolean>(false);
  const togglePopover = useCallback(() => setIsPopoverOpen((prev) => !prev), []);
  const handlePillKeyDown = useCallback((e: KeyboardEvent<HTMLSpanElement>): void => {
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

  // The onboarding/config affordance for the pre-run states lives in the chat
  // intro, so the banner stays quiet until a run actually exists.
  if (status === null || status.status === "not_configured") {
    return null;
  }

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

  if (status.status === "pending") {
    // Queued: inert (no popover) until the run starts. `aria-disabled` keeps
    // the framework's actionability contract honest during the transient gap
    // before the pill turns interactive (mirrors SetupStatusCard / SCU-1215).
    return (
      <span className={`${styles.pill} ${styles.pillInert}`} data-testid="setup-status-card" aria-disabled>
        <TerminalIcon size={13} className={styles.icon} aria-hidden="true" />
        <span className={styles.label}>{SETUP_LABEL}</span>
        <span className={`${bashStyles.badge} ${bashStyles.badgeRunning}`} data-testid="setup-status-badge">
          queued
        </span>
        {editButton}
      </span>
    );
  }

  // "Migrated" rows are terminal-state runs backfilled from the legacy
  // PTY-based setup path: no recorded run_id and no captured command. Showing
  // the project's current command would misleadingly imply we know what ran.
  const isMigrated =
    (status.status === "succeeded" || status.status === "failed" || status.status === "legacy") &&
    (status.runId === null || status.runId === undefined);

  // Prefer the command that actually ran for this workspace over the project's
  // current setting (they can differ); fall back to a placeholder.
  const persistedCommand =
    typeof workspace?.setupCommand === "string" && workspace.setupCommand.length > 0 ? workspace.setupCommand : null;
  const commandRan = persistedCommand ?? (isMigrated ? null : currentCommand);
  const commandForPopover = commandRan ?? (isMigrated ? "(command not recorded)" : "workspace setup");

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
  // Prefix the body with "Exit code N" on failure, matching how Sculptor's
  // bash tool calls render their popover. Stderr is already merged into the
  // captured stream by the runner, so it appears inline like in a terminal.
  const exitCodePrefix =
    status.status === "failed" && typeof status.exitCode === "number" ? `Exit code ${status.exitCode}\n` : "";
  const logText = `${exitCodePrefix}${rawLogText}`;
  const hasLogText = logText.length > 0;
  const canOpenPopover = shouldShowLog;
  const hasCommandChanged = persistedCommand !== null && currentCommand !== null && persistedCommand !== currentCommand;
  // Rerun is gated on the project having a command — the backend reads it from
  // `project.workspace_setup_command` and 422s when blank, so an unguarded
  // button would silently no-op when the user has cleared the setting.
  const isRerunVisible =
    (status.status === "succeeded" || status.status === "failed" || status.status === "legacy") &&
    currentCommand !== null;
  const isError = status.status === "failed";

  const actions = (
    <>
      <BashStatusBadge state={badgeState} isBackground={false} duration={badgeDuration} testId="setup-status-badge" />
      {isRunning && (
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
      )}
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

  const pillClassName = [styles.pill, isError ? styles.pillError : null, isPopoverOpen ? styles.pillOpen : null]
    .filter(Boolean)
    .join(" ");

  // Legacy rows have no captured log, so the pill is non-interactive (no
  // popover) — just the badge and any rerun/edit affordances.
  if (!canOpenPopover) {
    return (
      <span className={`${pillClassName} ${styles.pillInert}`} data-testid="setup-status-card">
        <TerminalIcon size={13} className={styles.icon} aria-hidden="true" />
        <span className={styles.label}>{SETUP_LABEL}</span>
        {actions}
      </span>
    );
  }

  // Anchor + own onClick rather than Popover.Trigger: Trigger composes its
  // toggle via Radix Slot, which is unreliable with the action IconButtons
  // nested in the pill. The anchor pattern (as in AlphaToolPillRow /
  // SetupStatusCard) lets the pill own its click cleanly.
  return (
    <Popover.Root open={isPopoverOpen} onOpenChange={setIsPopoverOpen}>
      <PopoverAnchor asChild>
        <span
          ref={pillRef}
          className={pillClassName}
          data-testid="setup-status-card"
          role="button"
          aria-haspopup="dialog"
          aria-expanded={isPopoverOpen}
          tabIndex={0}
          onClick={togglePopover}
          onKeyDown={handlePillKeyDown}
        >
          <TerminalIcon size={13} className={styles.icon} aria-hidden="true" />
          <span className={styles.label}>{SETUP_LABEL}</span>
          {actions}
        </span>
      </PopoverAnchor>
      <Popover.Content
        side="bottom"
        sideOffset={4}
        align="end"
        collisionPadding={16}
        className={bashStyles.popoverContent}
        onOpenAutoFocus={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => {
          // Clicks inside the pill shouldn't auto-close — let the pill's own
          // onClick toggle it (or the action IconButtons handle themselves).
          if (pillRef.current?.contains(e.target as Node)) e.preventDefault();
        }}
        style={POPOVER_STYLE}
      >
        <div className={bashStyles.popover}>
          <div className={bashStyles.popoverSection}>
            <span className={bashStyles.popoverCommand}>
              <span className={bashStyles.prompt}>$</span> {commandForPopover}
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
