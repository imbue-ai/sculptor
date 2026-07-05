import * as HoverCard from "@radix-ui/react-hover-card";
import { IconButton, Theme, Tooltip } from "@radix-ui/themes";
import { useAtom, useStore } from "jotai";
import { Check, Square } from "lucide-react";
import type { ComponentType, CSSProperties, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatMessage, TaskStatus } from "~/api";
import { AgentTaskStatus, ArtifactType, ElementIds } from "~/api";
import { useCapabilityGate } from "~/common/hooks/useCapabilityGate.ts";
import { useKeybindingDisplayText } from "~/common/keybindings/useKeybinding.ts";
import { isCancellableAtomFamily } from "~/common/state/atoms/interruptState.ts";
import {
  activeTurnIdAtomFamily,
  liveTaskTurnIdAtomFamily,
  tasksPhaseAtomFamily,
} from "~/common/state/atoms/statusPillTasks.ts";
import { useInterruptAgent } from "~/common/state/hooks/useInterruptAgent.ts";
import { useTaskDetailWithDefaults } from "~/common/state/hooks/useTaskDetail.ts";
import { useTaskSupportsInterruption } from "~/common/state/hooks/useTaskHelpers.ts";
import { useThemeSuccessColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { Toast } from "~/components/Toast.tsx";

import { AgentTasksPanel } from "./AgentTasksPanel.tsx";
import { useChatTask } from "./ChatTaskContext.tsx";
import type { AnimationProps } from "./pillAnimations";
import { ANIMATION_POOL, pickAnimationIndex, SpinnerAnimation } from "./pillAnimations";
import styles from "./StatusPill.module.scss";
import type { AgentState } from "./useAgentStatus.ts";
import { useAgentStatus } from "./useAgentStatus.ts";
import { useElapsedTime } from "./useElapsedTime.ts";

type StatusPillProps = {
  taskStatus: TaskStatus | null;
  // `isAutoCompacting` drives the "Compacting" pill state, fed by the
  // AutoCompacting* message pair via the `is_auto_compacting` derivation. Every
  // harness that compacts (Claude and pi) feeds it.
  isAutoCompacting: boolean;
  isStreaming: boolean;
  inProgressChatMessage: ChatMessage | null;
  workingUserMessageId: string | null;
  // Number of background tasks in flight (task_started without matching
  // task_notification). When > 0 the pill shows a "waiting" label instead
  // of claiming the agent is thinking — see SCU-387.
  pendingBackgroundTaskCount?: number;
};

// States in which the tasks UI should override the status label. Compacting,
// stopping, and stopped keep their own labels because they reflect lifecycle
// events that aren't related to the agent's todo list.
const TASKS_OVERRIDE_STATES: ReadonlySet<AgentState> = new Set(["thinking", "streaming", "calling_tools"]);

// Cap the in-progress task name shown in the pill. The popover renders the
// full text — the pill only needs enough to identify which item is running.
const PILL_TASK_NAME_MAX_LENGTH = 36;

// How long to keep showing "All tasks complete" before reverting to the
// ordinary status label.
const ALL_COMPLETE_LINGER_MS = 5000;

// HoverCard delays for the tasks popover. Open is short enough that a
// deliberate hover feels instant; close is a touch longer so a brief mouse
// dip off the pill doesn't snap the popover shut.
const POPOVER_OPEN_DELAY_MS = 150;
const POPOVER_CLOSE_DELAY_MS = 200;

const truncateTaskName = (text: string): string =>
  text.length > PILL_TASK_NAME_MAX_LENGTH ? `${text.slice(0, PILL_TASK_NAME_MAX_LENGTH - 1).trimEnd()}\u2026` : text;

export const StatusPill = ({
  taskStatus,
  isAutoCompacting,
  isStreaming,
  inProgressChatMessage,
  workingUserMessageId,
  pendingBackgroundTaskCount,
}: StatusPillProps): ReactElement | null => {
  // The owning chat panel's agent — Stop and the PLAN-artifact tasks below
  // must follow the panel, not the route.
  const { workspaceId: workspaceID, taskId: taskID } = useChatTask();
  const { isInterrupting: isStoppingTask, interrupt, toast, setToast } = useInterruptAgent(workspaceID, taskID);
  // Stable callback so the memoized <Toast> below bails out instead of
  // re-rendering on every unrelated parent render. (SCU-1455)
  const handleToastOpenChange = useCallback(
    (open: boolean) => {
      if (!open) setToast(null);
    },
    [setToast],
  );
  const interruptHint = useKeybindingDisplayText("interrupt_agent");
  const store = useStore();
  // Pick a new animation each time the pill transitions from hidden to visible.
  // Tracked in state (with a previous-value guard, adjusted during render) so the
  // chosen index drives the rendered animation without reading a ref mid-render.
  const [animationIndex, setAnimationIndex] = useState<number>(pickAnimationIndex);
  const [isVisiblePrev, setIsVisiblePrev] = useState(false);

  const {
    state,
    label,
    isCancellable,
    isVisible: isAgentActive,
  } = useAgentStatus({
    taskStatus,
    isAutoCompacting,
    isStreaming,
    inProgressChatMessage,
    workingUserMessageId,
    isStoppingTask,
    pendingBackgroundTaskCount,
  });

  // Hide the Stop affordance entirely when the harness can't honor a mid-turn
  // interrupt (pi drops InterruptProcessUserMessage) — a dead Stop button is
  // worse than none. `?? true` keeps it visible until the task loads; Claude
  // reports true, pi false. `canStop` gates both the clickable button and the
  // `isCancellable` mirror that arms the Ctrl+C keybinding, so neither path
  // fires for a non-interruptible harness.
  const canBeInterrupted = useTaskSupportsInterruption(taskID) ?? true;
  const canStop = isCancellable && canBeInterrupted;
  // When the agent is cancellable but the harness can't honor a mid-turn
  // interrupt, the Stop control is shown disabled-with-tooltip rather than hidden.
  const stopGate = useCapabilityGate(canBeInterrupted, ElementIds.CAPABILITY_DISABLED_STOP);

  // Pull tasks from the PLAN artifact. When tasks exist and the pill is
  // in an active state, the pill's label is replaced with the current
  // in-progress task, and hover/click reveals a popover with the full list.
  const { artifacts } = useTaskDetailWithDefaults(taskID);
  const successColor = useThemeSuccessColor();
  const tasks = artifacts[ArtifactType.PLAN]?.tasks ?? null;
  const hasTasks = tasks !== null && tasks.length > 0;
  const hasInProgress = tasks !== null && tasks.some((t) => t.status === AgentTaskStatus.IN_PROGRESS);
  const completedCount = tasks?.filter((t) => t.status === AgentTaskStatus.COMPLETED).length ?? 0;
  const totalCount = tasks?.length ?? 0;
  const isAllComplete = hasTasks && completedCount === totalCount;

  // Latch the most recent non-null `workingUserMessageId` (the "active turn"
  // — also used downstream to key the elapsed timer). This is the right
  // identity to test artifact freshness against, because we want carryover to
  // count as stale once a new turn starts, even after that new turn finishes
  // and `workingUserMessageId` goes back to null. Persisted per-task so the
  // staleness verdict survives tab switches and app restarts.
  const [activeTurnId, setActiveTurnId] = useAtom(activeTurnIdAtomFamily(taskID));
  useEffect(() => {
    if (workingUserMessageId !== null && workingUserMessageId !== activeTurnId) {
      setActiveTurnId(workingUserMessageId);
    }
  }, [workingUserMessageId, activeTurnId, setActiveTurnId]);

  // Track which turn the artifact was last "live" in (i.e. had an in-progress
  // task). Once a new turn starts and the agent emits no new TodoWrite, the
  // carried-over all-complete artifact is stale — showing "X of N done" for it
  // would misleadingly imply it belongs to the new turn. Persisted alongside
  // activeTurnId so the comparison is stable across remounts and restarts.
  const [liveTaskTurnId, setLiveTaskTurnId] = useAtom(liveTaskTurnIdAtomFamily(taskID));
  useEffect(() => {
    if (hasInProgress && activeTurnId !== null && liveTaskTurnId !== activeTurnId) {
      setLiveTaskTurnId(activeTurnId);
    }
  }, [hasInProgress, activeTurnId, liveTaskTurnId, setLiveTaskTurnId]);
  const isStaleCarryover = isAllComplete && activeTurnId !== null && liveTaskTurnId !== activeTurnId;
  const hasFreshTasks = hasTasks && !isStaleCarryover;

  // Keep the pill on screen whenever the agent is in a non-idle state OR
  // there are tasks worth surfacing, so users can still hover/click the
  // popover after the turn completes. Stale carryover doesn't keep the pill
  // alive across an empty new turn.
  const isVisible = isAgentActive || hasFreshTasks;

  // Engagement state controls whether the pill renders the tasks UI vs. the
  // ordinary thinking/streaming/calling_tools status.
  //  - `idle`: artifact is stale (or never existed in this turn) — fall back
  //    to the normal status label.
  //  - `active`: a task is in progress — show tasks UI.
  //  - `lingering`: every task just completed this turn — show the
  //    "all complete" count briefly, then fall back to `idle`.
  // Survives workspace-tab switches (Jotai atom outlives component unmount).
  // Not persisted to localStorage: re-derives correctly on restart from the
  // artifact + persisted turn ids via the effects below.
  const [tasksPhase, setTasksPhase] = useAtom(tasksPhaseAtomFamily(taskID));

  // Reset to `idle` when a new user turn begins (a new non-null
  // workingUserMessageId), so a stale completed list from the previous turn
  // doesn't show "All tasks complete" while the agent is just starting to
  // think. A transition to null (turn finishing) does NOT reset — that
  // would cut the post-completion linger short. We key off `activeTurnId`
  // (the latched id) rather than a local ref so that this still fires
  // correctly after a remount, where a local ref would have just been
  // re-initialised to the current workingUserMessageId.
  useEffect(() => {
    if (workingUserMessageId !== null && workingUserMessageId !== activeTurnId) {
      setTasksPhase("idle");
    }
  }, [workingUserMessageId, activeTurnId, setTasksPhase]);

  // Drive phase transitions from the artifact. Only enter `active` when we
  // observe an in-progress task; only enter `lingering` from `active` (so a
  // pre-completed artifact never lights up).
  useEffect(() => {
    if (hasInProgress && tasksPhase !== "active") {
      setTasksPhase("active");
    } else if (isAllComplete && tasksPhase === "active") {
      setTasksPhase("lingering");
    }
  }, [hasInProgress, isAllComplete, tasksPhase, setTasksPhase]);

  // Auto-revert `lingering` to `idle` after the celebration window. Kept in
  // its own effect (rather than scheduling the timer inside the transition
  // above) because including `tasksPhase` in the scheduling effect's deps
  // tears the timer down on the very next render when phase flips to
  // `lingering`. This effect's cleanup only fires when phase leaves
  // `lingering`, which is exactly when we want to drop the timer.
  useEffect(() => {
    if (tasksPhase !== "lingering") return;
    const id = window.setTimeout(() => setTasksPhase("idle"), ALL_COMPLETE_LINGER_MS);
    return (): void => window.clearTimeout(id);
  }, [tasksPhase, setTasksPhase]);

  // `shouldShowTasks` gates the displayLabel override: only swap the lifecycle
  // label for a task-derived one when the phase machine has actually engaged.
  // `isPopoverEnabled` gates the popover trigger — available any time the pill
  // itself is up, so users can hover/click to discover the tasks affordance
  // (via the EmptyState before tasks exist, and to review tasks post-turn).
  const shouldShowTasks = tasksPhase !== "idle" && TASKS_OVERRIDE_STATES.has(state);
  const isPopoverEnabled = isVisible;

  // Mirror `isCancellable` into a per-task atom so the Ctrl+C keybinding in
  // ChatInput fires under exactly the same conditions that render the
  // clickable Stop button below. Cleared on unmount so the keybinding
  // doesn't fire when the pill isn't on screen.
  useEffect(() => {
    const a = isCancellableAtomFamily(taskID);
    store.set(a, canStop);
    return (): void => {
      store.set(a, false);
    };
  }, [store, taskID, canStop]);

  // Pick a new animation each time the pill becomes visible. Adjusting state
  // during render (guarded by the previous-visibility value) re-renders
  // immediately with the fresh index — no effect, no stale intermediate frame.
  if (isVisible !== isVisiblePrev) {
    setIsVisiblePrev(isVisible);
    if (isVisible) {
      setAnimationIndex(pickAnimationIndex());
    }
  }

  // Elapsed time keeps ticking only while the agent is in a non-idle, non-stopped
  // state; once the turn ends the displayed value freezes (the pill itself may
  // remain visible because there are still tasks to surface).
  const isTicking = isAgentActive && state !== "stopped";
  // The pill now stays visible between turns (because of tasks), so
  // `isVisible` no longer flips false to reset the timer — we drive the reset
  // off `activeTurnId` instead. While `workingUserMessageId` is null
  // (post-turn idle) we keep the previous turn's key so the frozen value
  // remains on display; a new non-null id rotates the key, which
  // `useElapsedTime` treats as a fresh session.
  const elapsedKey = `${taskID}-${activeTurnId ?? "init"}`;
  const { elapsed } = useElapsedTime(isVisible, isTicking, elapsedKey);

  // Hover + click-to-pin popover state for the tasks view.
  const [isHoverOpen, setIsHoverOpen] = useState(false);
  const [isPinned, setIsPinned] = useState(false);
  // Suppress the popover while the cursor is over the Stop button so the
  // tasks UI doesn't pop open under the Stop tooltip.
  const [isHoveringStop, setIsHoveringStop] = useState(false);
  const triggerRef = useRef<HTMLDivElement>(null);

  // Drop pin and hover when the popover trigger no longer applies (e.g. the
  // agent stops), so the popover doesn't get stuck open across state
  // transitions. Adjusting during render (guarded by the previous-enabled
  // value) resets the flags before paint, avoiding the extra effect render.
  const [isPopoverEnabledPrev, setIsPopoverEnabledPrev] = useState(isPopoverEnabled);
  if (isPopoverEnabled !== isPopoverEnabledPrev) {
    setIsPopoverEnabledPrev(isPopoverEnabled);
    if (!isPopoverEnabled) {
      setIsPinned(false);
      setIsHoverOpen(false);
    }
  }

  // A pinned popover stays open until the user clicks outside it or clicks
  // the pill again to toggle it off.
  const isPopoverOpen = isPopoverEnabled && !isHoveringStop && (isHoverOpen || isPinned);

  if (!isVisible) return null;

  const Animation: ComponentType<AnimationProps> | null =
    state === "stopped" || state === "idle"
      ? null
      : state === "compacting"
        ? SpinnerAnimation
        : ANIMATION_POOL[animationIndex];

  const pillClassName = state === "compacting" ? `${styles.pill} ${styles.pillCompacting}` : styles.pill;

  let displayLabel = label;
  // When the pill is showing the count summary, the elapsed timer is more
  // misleading than useful (it's "time since the turn started," which doesn't
  // map cleanly to "tasks complete"). Hide it in those modes.
  let shouldShowElapsed = true;
  if (shouldShowTasks && tasks !== null) {
    const inProgress = tasks.filter((t) => t.status === AgentTaskStatus.IN_PROGRESS);
    // Show the count summary both during the linger phase and on the single
    // render between "every task just completed" and the effect transitioning
    // phase to lingering, so the user never sees a "Waiting on agent..." flash.
    if (tasksPhase === "lingering" || isAllComplete) {
      displayLabel = `${completedCount} of ${totalCount} done`;
      shouldShowElapsed = false;
    } else if (inProgress.length === 1) {
      // 1-based position of the in-progress task in the list, so the user
      // sees "3 / 8 Doing the thing".
      const inProgressIndex = tasks.findIndex((t) => t.status === AgentTaskStatus.IN_PROGRESS);
      displayLabel = `${inProgressIndex + 1} / ${totalCount} \u00b7 ${truncateTaskName(inProgress[0].subject)}`;
    } else if (inProgress.length > 1) {
      displayLabel = `Working on ${inProgress.length} tasks...`;
    }
    // No else: the remaining state (active phase with zero in-progress and not
    // all-complete, e.g. all-PENDING) is effectively unreachable; fall back to
    // the underlying lifecycle `label` rather than a generic placeholder.
  } else if (!isAgentActive && hasFreshTasks) {
    // Post-turn: the agent is idle but the pill is still up because there are
    // tasks worth surfacing. Show a compact summary as the resting label.
    displayLabel = `${completedCount} of ${totalCount} done`;
    shouldShowElapsed = false;
  }

  const successColorVars = {
    "--color-success": `var(--${successColor}-9)`,
    "--color-success-bg": `var(--${successColor}-2)`,
    "--color-success-border": `var(--${successColor}-5)`,
  } as CSSProperties;

  const pillContents = (
    <div
      ref={triggerRef}
      className={pillClassName}
      data-testid={ElementIds.STATUS_PILL}
      // ``data-state`` is reserved by Radix: HoverCard.Trigger (which wraps
      // this div via ``asChild``) injects its own ``data-state`` through the
      // Slot prop-merge. Expose the agent-lifecycle phase under a distinct
      // attribute so the test selector (and any future CSS) can target it
      // without depending on Slot's merge precedence.
      data-agent-state={state}
      onClick={
        isPopoverEnabled
          ? (e): void => {
              // Don't toggle pin when the user clicks the Stop button.
              if ((e.target as HTMLElement).closest(`.${styles.stopButton}`)) return;
              setIsPinned((p) => !p);
            }
          : undefined
      }
      style={isPopoverEnabled ? { cursor: "pointer" } : undefined}
    >
      <span className={styles.iconSlot} data-testid={Animation ? ElementIds.STATUS_PILL_ANIMATION : undefined}>
        {Animation ? <Animation /> : <Check size={16} strokeWidth={2} style={{ color: "var(--gray-9)" }} />}
      </span>
      <span
        className={styles.label}
        data-testid={ElementIds.STATUS_PILL_LABEL}
        title={displayLabel !== label ? displayLabel : undefined}
      >
        {displayLabel}
      </span>
      {shouldShowElapsed && (
        <span className={styles.elapsed} data-testid={ElementIds.STATUS_PILL_ELAPSED}>
          {elapsed}
        </span>
      )}
      {isCancellable &&
        (stopGate.enabled ? (
          <Tooltip content={interruptHint ? `Stop (${interruptHint})` : "Stop"}>
            <IconButton
              size="1"
              variant="ghost"
              className={styles.stopButton}
              onClick={(e): void => {
                e.stopPropagation();
                void interrupt();
              }}
              onPointerEnter={(): void => setIsHoveringStop(true)}
              onPointerLeave={(): void => setIsHoveringStop(false)}
              disabled={isStoppingTask}
              data-testid={ElementIds.STATUS_PILL_STOP}
            >
              <Square size={4} fill="currentColor" />
            </IconButton>
          </Tooltip>
        ) : (
          // Radix Tooltip does not fire on a `disabled` button, so the hover
          // target, test hook, and popover-suppress handlers live on the span.
          <Tooltip content={stopGate.tooltip}>
            <span
              data-testid={stopGate.elementId}
              style={{ display: "inline-flex" }}
              onPointerEnter={(): void => setIsHoveringStop(true)}
              onPointerLeave={(): void => setIsHoveringStop(false)}
            >
              <IconButton size="1" variant="ghost" className={styles.stopButton} disabled aria-disabled>
                <Square size={4} fill="currentColor" />
              </IconButton>
            </span>
          </Tooltip>
        ))}
    </div>
  );

  return (
    <>
      <div className={styles.pillAnchor}>
        {isPopoverEnabled ? (
          <HoverCard.Root
            open={isPopoverOpen}
            onOpenChange={setIsHoverOpen}
            openDelay={POPOVER_OPEN_DELAY_MS}
            closeDelay={POPOVER_CLOSE_DELAY_MS}
          >
            <HoverCard.Trigger asChild>{pillContents}</HoverCard.Trigger>
            <HoverCard.Portal>
              {/* Theme wrapper re-establishes the Radix Themes CSS-var scope
                  inside the portal (which lives outside the app's <Theme>),
                  so tokens like --shadow-5 and --color-panel-solid resolve
                  to the same values as the alpha tool popovers. */}
              <Theme asChild>
                <HoverCard.Content
                  side="top"
                  align="end"
                  sideOffset={8}
                  // Clicking outside dismisses the pinned popover. The pill
                  // itself is "outside" the content, but it has its own
                  // toggle handler — prevent default there so the dismiss
                  // doesn't fight the click-to-toggle.
                  onPointerDownOutside={(e): void => {
                    if (triggerRef.current?.contains(e.target as Node)) {
                      e.preventDefault();
                      return;
                    }
                    setIsPinned(false);
                  }}
                  className={`${styles.popoverContent}${hasTasks ? "" : ` ${styles.popoverContentEmpty}`}`}
                  style={successColorVars}
                >
                  <div className={styles.popoverHeader}>
                    <span>Agent tasks</span>
                  </div>
                  <AgentTasksPanel tasks={tasks} />
                </HoverCard.Content>
              </Theme>
            </HoverCard.Portal>
          </HoverCard.Root>
        ) : (
          pillContents
        )}
      </div>
      <Toast open={!!toast} onOpenChange={handleToastOpenChange} title={toast?.title} type={toast?.type} />
    </>
  );
};
