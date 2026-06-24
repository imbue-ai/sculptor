import { getCurrentUserConfig } from "~/config/user_config";
import { eventBus } from "~/events";
import type { Unsubscribe } from "~/events/bus";

// CI babysitter coordinator (services/ci_babysitter_service/coordinator.py).
// An off-by-default, per-workspace observer that turns CI pipeline failures into
// agent retries, capped at retry_cap (REQ-NFR-062, default 3). It coordinates
// with PR/CI polling (Task 7.1) by consuming pr_status events rather than
// querying CI itself. The actual agent drive is delegated to an injected hook;
// the state machine (default-off, cap, pause, idempotency) lives here.

interface BabysitterState {
  workspaceId: string;
  projectId: string;
  paused: boolean;
  retryCount: number;
  retired: boolean;
  lastDispatchedPipelineFailedId: number | null;
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

// Called to drive a retry (kick the workspace's agent with the failure prompt).
// Injected so the coordinator stays decoupled from the runner/terminal driving.
export type RetryDispatcher = (
  workspaceId: string,
  projectId: string,
  prompt: string,
) => void;

export class CIBabysitterCoordinator {
  private readonly states = new Map<string, BabysitterState>();
  private unsubscribe: Unsubscribe | undefined;

  constructor(private readonly dispatchRetry: RetryDispatcher = () => {}) {}

  private ensureState(workspaceId: string, projectId: string): BabysitterState {
    let state = this.states.get(workspaceId);
    if (state === undefined) {
      state = {
        workspaceId,
        projectId,
        paused: false,
        retryCount: 0,
        retired: false,
        lastDispatchedPipelineFailedId: null,
      };
      this.states.set(workspaceId, state);
    }
    return state;
  }

  getStateSnapshot(workspaceId: string): BabysitterState | undefined {
    return this.states.get(workspaceId);
  }

  setPaused(workspaceId: string, projectId: string, paused: boolean): void {
    this.ensureState(workspaceId, projectId).paused = paused;
  }

  // Decision core: a fresh failed pipeline drives one retry while enabled,
  // un-paused, not retired, and below the cap; reaching the cap retires the
  // workspace. Idempotent on pipeline_id so re-observing the same failure is a
  // no-op.
  onPrStatus(
    workspaceId: string,
    projectId: string,
    status: Record<string, unknown> | null,
  ): void {
    const config = getCurrentUserConfig();
    if (!config.ci_babysitter.enabled || status === null) {
      return;
    }
    const pipelineStatus = status.pipeline_status;
    const pipelineId =
      typeof status.pipeline_id === "number" ? status.pipeline_id : null;
    if (pipelineStatus !== "failed") {
      return;
    }
    const state = this.ensureState(workspaceId, projectId);
    if (state.paused || state.retired) {
      return;
    }
    if (
      pipelineId !== null &&
      pipelineId === state.lastDispatchedPipelineFailedId
    ) {
      return; // already handled this pipeline
    }
    if (state.retryCount >= config.ci_babysitter.retry_cap) {
      state.retired = true;
      return;
    }
    state.retryCount += 1;
    state.lastDispatchedPipelineFailedId = pipelineId;
    if (state.retryCount >= config.ci_babysitter.retry_cap) {
      state.retired = true;
    }
    this.dispatchRetry(
      workspaceId,
      projectId,
      config.ci_babysitter.pipeline_failed_prompt,
    );
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
    return {
      workspaceId,
      paused: state.paused,
      retryCount: state.retryCount,
      retryCap,
      retired: state.retired,
      atCap: state.retryCount >= retryCap,
      disabledReason: null,
      disabledReasonIsTransient: false,
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
