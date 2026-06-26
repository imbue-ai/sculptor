import { getCurrentUserConfig } from "~/config/user_config";
import { getOrm } from "~/db/orm";
import { getWorkspace } from "~/db/repositories/workspaces";
import { eventBus } from "~/events";
import type { Unsubscribe } from "~/events/bus";
import {
  type BabysitterDriver,
  createDefaultBabysitterDriver,
} from "~/services/ci_babysitter/driver";
import {
  classifyTransitions,
  type PrStatusLike,
  type Transition,
} from "~/services/ci_babysitter/transitions";

// CI babysitter coordinator (services/ci_babysitter_service/coordinator.py).
// An off-by-default, per-workspace observer that turns CI pipeline failures and
// MR/PR merge conflicts into agent retries, capped at retry_cap (default 3).
// It consumes pr_status events from PR/CI polling rather
// than querying CI itself, runs the pure transition classifier on each update,
// and delegates the agent drive to an injected driver. The policy (baseline,
// dedup, pause, cap, retire) lives here; "which agent and how" lives in the
// driver.

interface BabysitterState {
  workspaceId: string;
  projectId: string;
  paused: boolean;
  retryCount: number;
  retired: boolean;
  prevStatus: PrStatusLike | null;
  lastDispatchedPipelineFailedId: number | null;
  lastDispatchedMergeConflict: boolean;
  transientDisabledReason: string | null;
}

export interface BabysitterStateView {
  workspaceId: string;
  paused: boolean;
  retryCount: number;
  retryCap: number;
  retired: boolean;
  atCap: boolean;
  disabledReason: string | null;
  disabledReasonIsTransient: boolean;
}

function pipelineId(status: PrStatusLike): number | null {
  return typeof status.pipeline_id === "number" ? status.pipeline_id : null;
}

export class CIBabysitterCoordinator {
  private readonly states = new Map<string, BabysitterState>();
  private readonly driver: BabysitterDriver;
  private unsubscribe: Unsubscribe | undefined;

  constructor(driver: BabysitterDriver = createDefaultBabysitterDriver()) {
    this.driver = driver;
  }

  private ensureState(workspaceId: string, projectId: string): BabysitterState {
    let state = this.states.get(workspaceId);
    if (state === undefined) {
      state = {
        workspaceId,
        projectId,
        paused: false,
        retryCount: 0,
        retired: false,
        prevStatus: null,
        lastDispatchedPipelineFailedId: null,
        lastDispatchedMergeConflict: false,
        transientDisabledReason: null,
      };
      this.states.set(workspaceId, state);
    }
    return state;
  }

  getStateSnapshot(workspaceId: string): BabysitterState | undefined {
    return this.states.get(workspaceId);
  }

  setPaused(workspaceId: string, projectId: string, paused: boolean): void {
    let resolvedProjectId = projectId;
    if (resolvedProjectId === "") {
      const workspace = getWorkspace(getOrm(), workspaceId);
      resolvedProjectId = workspace?.projectId ?? "";
    }
    this.ensureState(workspaceId, resolvedProjectId).paused = paused;
  }

  // The single entry point: fold one pr_status observation into the per-
  // workspace state and dispatch prompts for actionable transitions. When the
  // babysitter is disabled, no state is created (off by default is invisible).
  onPrStatus(
    workspaceId: string,
    projectId: string,
    status: Record<string, unknown> | null,
  ): void {
    const config = getCurrentUserConfig();
    if (!config.ci_babysitter.enabled || status === null) {
      return;
    }
    const next = status as PrStatusLike;
    const state = this.ensureState(workspaceId, projectId);
    const prev = state.prevStatus;

    // Transient "lost MR" gap: when the workspace's branch flips, polling can't
    // match the workspace to an MR and emits pr_state="none". Treating it as a
    // real transition would clobber prevStatus and make the next poll look like
    // a fresh edge. Suppress: don't update prevStatus and don't dispatch.
    if (next.pr_state === "none" && prev !== null && prev.pr_state !== "none") {
      return;
    }
    state.prevStatus = next;
    // Re-arm the merge-conflict dedup the moment we observe an explicit "no
    // conflict" state, so a later re-conflict re-prompts as expected.
    if (next.has_conflicts === false) {
      state.lastDispatchedMergeConflict = false;
    }

    const transitions = classifyTransitions(prev, next);
    // Lifecycle transitions first, so a same-cycle merge/close retires the
    // babysitter before any pipeline_failed / merge_conflict dispatches a
    // spurious prompt.
    for (const transition of transitions) {
      if (transition === "PIPELINE_PASSED") {
        state.retryCount = 0;
        state.transientDisabledReason = null;
      } else if (transition === "MR_MERGED" || transition === "MR_CLOSED") {
        state.retired = true;
        state.transientDisabledReason = null;
      }
    }
    for (const transition of transitions) {
      if (transition === "PIPELINE_FAILED" || transition === "MERGE_CONFLICT") {
        this.dispatchPrompt(state, transition, next);
      }
    }
  }

  private dispatchPrompt(
    state: BabysitterState,
    transition: Transition,
    next: PrStatusLike,
  ): void {
    const config = getCurrentUserConfig();
    if (!config.ci_babysitter.enabled || state.retired || state.paused) {
      return;
    }
    if (state.retryCount >= config.ci_babysitter.retry_cap) {
      return;
    }
    // Per-id dedup: never resend the same prompt for the same underlying state.
    if (transition === "PIPELINE_FAILED") {
      const id = pipelineId(next);
      if (id !== null && id === state.lastDispatchedPipelineFailedId) {
        return;
      }
    } else if (transition === "MERGE_CONFLICT") {
      if (state.lastDispatchedMergeConflict) {
        return;
      }
    }

    const prompt =
      transition === "PIPELINE_FAILED"
        ? config.ci_babysitter.pipeline_failed_prompt
        : config.ci_babysitter.merge_conflict_prompt;

    const resolved = this.driver.resolve(state.workspaceId, state.projectId);
    if (resolved.kind === "disabled") {
      // No spawn, no task. The reason surfaces to the UI on every status read.
      return;
    }

    this.driver.deliver(state.workspaceId, state.projectId, resolved, prompt);

    // The attempt counts against retry_cap whether or not delivery ultimately
    // lands (a terminal drive may fail later).
    state.retryCount += 1;
    if (transition === "PIPELINE_FAILED") {
      state.lastDispatchedPipelineFailedId = pipelineId(next);
    } else {
      state.lastDispatchedMergeConflict = true;
    }
  }

  buildView(workspaceId: string): BabysitterStateView {
    const config = getCurrentUserConfig();
    const retryCap = config.ci_babysitter.retry_cap;
    const state = this.states.get(workspaceId);
    if (state === undefined) {
      return {
        workspaceId,
        paused: false,
        retryCount: 0,
        retryCap,
        retired: false,
        atCap: false,
        disabledReason: null,
        disabledReasonIsTransient: false,
      };
    }

    // Recompute the persistent reason on every read so it appears before any
    // failure and self-heals when the user changes the MRU or fixes the config.
    let disabledReason: string | null = null;
    let disabledReasonIsTransient = false;
    const resolved = this.driver.resolve(workspaceId, state.projectId);
    if (resolved.kind === "disabled" && !resolved.transient) {
      disabledReason = resolved.reason;
    } else if (state.transientDisabledReason !== null) {
      disabledReason = state.transientDisabledReason;
      disabledReasonIsTransient = true;
    }

    return {
      workspaceId,
      paused: state.paused,
      retryCount: state.retryCount,
      retryCap,
      retired: state.retired,
      atCap: state.retryCount >= retryCap,
      disabledReason,
      disabledReasonIsTransient,
    };
  }

  start(): void {
    if (this.unsubscribe !== undefined) {
      return;
    }
    this.unsubscribe = eventBus.subscribe((event) => {
      if (event.kind === "pr_status") {
        this.onPrStatus(
          event.workspaceId,
          event.projectId ?? "",
          event.status ?? null,
        );
      }
    });
  }

  stop(): void {
    this.unsubscribe?.();
    this.unsubscribe = undefined;
  }
}

let singleton: CIBabysitterCoordinator | undefined;

export function getCIBabysitterCoordinator(): CIBabysitterCoordinator {
  if (singleton === undefined) {
    singleton = new CIBabysitterCoordinator();
  }
  return singleton;
}

export function resetCIBabysitterCoordinatorForTests(): void {
  singleton?.stop();
  singleton = undefined;
}
