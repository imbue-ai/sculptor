import { useCallback, useEffect, useRef, useState } from "react";

import type { ChatMessage, TaskStatus } from "~/api";
import type { BlockUnion } from "~/common/Guards";
import { isTextBlock } from "~/common/Guards";

export type AgentState =
  | "thinking"
  | "streaming"
  | "calling_tools"
  | "compacting"
  | "stopping"
  | "stopped"
  | "waiting_for_background"
  | "idle";

export type AgentStatusResult = {
  state: AgentState;
  label: string;
  isCancellable: boolean;
  isVisible: boolean;
};

export type UseAgentStatusProps = {
  taskStatus: TaskStatus | null;
  isAutoCompacting: boolean;
  isStreaming: boolean;
  inProgressChatMessage: ChatMessage | null;
  workingUserMessageId: string | null;
  isStoppingTask: boolean;
  // Number of background tasks (Bash / Agent / Task with run_in_background)
  // whose ``task_started`` arrived but whose ``task_notification`` has not.
  // While this is non-zero AND the task is otherwise in an "active" state,
  // the harness is genuinely idle waiting for the bg notification — show a
  // "waiting" label instead of claiming the agent is thinking. See SCU-387.
  pendingBackgroundTaskCount?: number;
};

const DEBOUNCE_MS = 500;
const STOPPED_LINGER_MS = 1500;

const STATE_CONFIG: Record<AgentState, { label: string; isCancellable: boolean }> = {
  thinking: { label: "Thinking...", isCancellable: true },
  streaming: { label: "Streaming...", isCancellable: true },
  calling_tools: { label: "Calling tools...", isCancellable: true },
  compacting: { label: "Compacting...", isCancellable: false },
  stopping: { label: "Stopping...", isCancellable: false },
  stopped: { label: "Stopped", isCancellable: false },
  waiting_for_background: { label: "Waiting for background tasks...", isCancellable: true },
  idle: { label: "", isCancellable: false },
};

// Lifecycle states that imply the agent is doing visible work. When a
// background task is in flight we override these (and only these) to a
// "waiting" label, so the pill still distinguishes interrupt-style states
// like compacting / stopping which are about the agent itself, not a bg task.
const ACTIVE_OVERRIDABLE_STATES: ReadonlySet<AgentState> = new Set(["thinking", "streaming", "calling_tools"]);

const deriveRawState = (props: UseAgentStatusProps): AgentState => {
  const {
    isAutoCompacting,
    isStoppingTask,
    isStreaming,
    inProgressChatMessage,
    taskStatus,
    workingUserMessageId,
    pendingBackgroundTaskCount = 0,
  } = props;

  if (isAutoCompacting) {
    return "compacting";
  }

  if (isStoppingTask) {
    return "stopping";
  }

  // Suppress the indicator while the task is WAITING — i.e. an
  // AskUserQuestion or ExitPlanMode panel is showing, or the agent is
  // sitting in plan mode. The held MCP `tools/call` keeps the request
  // alive (so `isStreaming` / inProgressChatMessage may still look
  // active), but the agent isn't actually doing anything until the user
  // responds, and the AUQ panel itself already conveys "needs input".
  if (taskStatus === "WAITING") {
    return "idle";
  }

  let activeState: AgentState = "idle";
  if (isStreaming && inProgressChatMessage) {
    const content = inProgressChatMessage.content;
    if (content.length > 0) {
      const lastBlock: BlockUnion = content[content.length - 1];
      if (isTextBlock(lastBlock)) {
        activeState = "streaming";
      } else if (lastBlock.type === "tool_use") {
        activeState = "calling_tools";
      } else {
        activeState = "thinking";
      }
    } else {
      activeState = "thinking";
    }
  } else if (isStreaming) {
    activeState = "thinking";
  } else if (taskStatus === "RUNNING" && workingUserMessageId !== null) {
    activeState = "thinking";
  }

  // When a background task is in flight, the harness keeps the parent
  // request alive (waiting for the eventual task_notification) — taskStatus
  // stays RUNNING and the in-progress message stays set even though the
  // agent itself has finished its turn. Override the active lifecycle
  // states to a "waiting" label so the pill reflects what's actually
  // happening (SCU-387).
  if (pendingBackgroundTaskCount > 0 && ACTIVE_OVERRIDABLE_STATES.has(activeState)) {
    return "waiting_for_background";
  }

  return activeState;
};

export const useAgentStatus = (props: UseAgentStatusProps): AgentStatusResult => {
  const rawState = deriveRawState(props);

  const [displayedState, setDisplayedState] = useState<AgentState>(rawState);
  const lastChangeTimeRef = useRef<number>(0);
  const pendingTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Start the debounce clock at mount. Kept out of useRef's initializer so
  // render stays free of impure calls (Date.now()); the ref is only read from
  // effects, which run after this one sets it.
  useEffect(() => {
    lastChangeTimeRef.current = Date.now();
  }, []);

  const applyState = useCallback((state: AgentState) => {
    setDisplayedState(state);
    lastChangeTimeRef.current = Date.now();
  }, []);

  useEffect(() => {
    if (rawState === displayedState) {
      // No change needed; clear any pending timeout
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
        pendingTimeoutRef.current = null;
      }
      return;
    }

    // Entering compaction is a deliberate lifecycle signal, not the
    // high-frequency thinking/streaming/calling_tools flicker the debounce
    // smooths — apply it immediately. A debounced compacting transition can be
    // cleared by the next active-state transition before its timer fires (when
    // a brief compaction ends within the debounce window), so the "Compacting"
    // chrome would never reach the displayed state.
    if (rawState === "compacting") {
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
        pendingTimeoutRef.current = null;
      }
      // eslint-disable-next-line react-hooks/set-state-in-effect
      applyState(rawState);
      return;
    }

    // When stopping transitions to idle, show "Stopped" briefly first.
    // Timer-driven state machine: this synchronous transition kicks off the
    // 1500ms "Stopped" linger timer below. Deriving it during render would
    // require reproducing the debounce timing impurely and risks the behavior.
    if (rawState === "idle" && displayedState === "stopping") {
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
      }
      applyState("stopped");
      pendingTimeoutRef.current = setTimeout(() => {
        pendingTimeoutRef.current = null;
        applyState("idle");
      }, STOPPED_LINGER_MS);
      return;
    }

    // "stopped" lingers until its timeout fires (unless a new active state arrives)
    if (rawState === "idle" && displayedState === "stopped") {
      return;
    }

    const elapsed = Date.now() - lastChangeTimeRef.current;

    if (elapsed >= DEBOUNCE_MS) {
      // Enough time has passed; apply immediately
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
        pendingTimeoutRef.current = null;
      }
      applyState(rawState);
    } else {
      // Schedule for remaining time
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
      }
      const remaining = DEBOUNCE_MS - elapsed;
      pendingTimeoutRef.current = setTimeout(() => {
        pendingTimeoutRef.current = null;
        applyState(rawState);
      }, remaining);
    }
  }, [rawState, displayedState, applyState]);

  // Clean up timeout on unmount
  useEffect(() => {
    return (): void => {
      if (pendingTimeoutRef.current !== null) {
        clearTimeout(pendingTimeoutRef.current);
      }
    };
  }, []);

  const config = STATE_CONFIG[displayedState];

  return {
    state: displayedState,
    label: config.label,
    isCancellable: config.isCancellable,
    isVisible: displayedState !== "idle",
  };
};
