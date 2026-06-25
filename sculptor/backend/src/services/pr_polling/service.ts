import { getCurrentUserConfig } from "~/config/user_config";
import { getOrm } from "~/db/orm";
import {
  getRepo,
  getWorkspace,
  listRecentWorkspaces,
} from "~/db/repositories";
import type { WorkspaceRow } from "~/db/schema";
import { workingDirectory } from "~/environment/paths";
import { eventBus } from "~/events";
import { runGit } from "~/git";
import { localPathFromRepo } from "~/services/project";
import {
  type CliRunner,
  defaultCliRunner,
} from "~/services/pr_polling/cli_status";
import {
  BoundedPool,
  computePollDelaySeconds,
  GLOBAL_MIN_POLL_SPACING_SECONDS,
  PollSpacingThrottle,
  WORKER_POOL_SIZE,
} from "~/services/pr_polling/pool";
import { detectProvider } from "~/services/pr_polling/provider";
import { setPrStatus } from "~/services/pr_polling/store";
import { fetchPrStatus, type PrStatusInfo } from "~/services/pr_polling/status";

// PR/CI status polling service (web/pr_polling_service.py). Schedules per-open-
// workspace polls through the bounded pool + global spacing throttle, detects
// the provider from `origin`, queries status via gh/glab, and emits pr_status
// events that feed pr_status_by_workspace_id (Tasks 4.1/4.4).

export interface PrPollingDeps {
  runner: CliRunner;
  throttle: PollSpacingThrottle;
  pool: BoundedPool;
  workingDirForWorkspace: (workspace: WorkspaceRow) => string | null;
}

function defaultWorkingDir(workspace: WorkspaceRow): string | null {
  if (workspace.environmentId === null) {
    return null;
  }
  const repo = getRepo(getOrm(), workspace.projectId);
  const repoHostPath =
    repo !== undefined ? (localPathFromRepo(repo) ?? undefined) : undefined;
  return workingDirectory(
    workspace.environmentId,
    workspace.initializationStrategy,
    repoHostPath,
  );
}

export class PrPollingService {
  private readonly deps: PrPollingDeps;
  private readonly timers = new Set<ReturnType<typeof setTimeout>>();
  private running = false;
  private scheduled = new Set<string>();
  private unsubscribe: (() => void) | undefined;

  constructor(deps: Partial<PrPollingDeps> = {}) {
    this.deps = {
      runner: deps.runner ?? defaultCliRunner,
      throttle:
        deps.throttle ??
        new PollSpacingThrottle(GLOBAL_MIN_POLL_SPACING_SECONDS * 1000),
      pool: deps.pool ?? new BoundedPool(WORKER_POOL_SIZE),
      workingDirForWorkspace: deps.workingDirForWorkspace ?? defaultWorkingDir,
    };
  }

  // Poll one workspace once: resolve its remote + branch, detect the provider,
  // and emit a pr_status event. A workspace without a recognized remote clears
  // its entry. Returns the resulting status (or null when there's no remote).
  async pollWorkspace(workspace: WorkspaceRow): Promise<PrStatusInfo | null> {
    const cwd = this.deps.workingDirForWorkspace(workspace);
    if (cwd === null) {
      return null;
    }
    const origin = await runGit(["remote", "get-url", "origin"], cwd)
      .then((result) => (result.exitCode === 0 ? result.stdout.trim() : null))
      .catch(() => null);
    const provider = detectProvider(origin);
    if (provider === null) {
      this.emit(workspace, null);
      return null;
    }
    const branch = await runGit(["rev-parse", "--abbrev-ref", "HEAD"], cwd)
      .then((result) => (result.exitCode === 0 ? result.stdout.trim() : null))
      .catch(() => null);
    if (branch === null || branch === "" || branch === "HEAD") {
      return null;
    }
    await this.deps.throttle.acquire();
    const status = await this.deps.pool.run(() =>
      fetchPrStatus(
        provider,
        workspace.objectId,
        branch,
        workspace.targetBranch ?? branch,
        cwd,
        this.deps.runner,
      ),
    );
    this.emit(workspace, status);
    return status;
  }

  private emit(workspace: WorkspaceRow, status: PrStatusInfo | null): void {
    // Mirror into the snapshot store so a fresh client gets it on connect.
    setPrStatus(workspace.objectId, status);
    eventBus.publish({
      kind: "pr_status",
      workspaceId: workspace.objectId,
      projectId: workspace.projectId,
      status: status as Record<string, unknown> | null,
    });
  }

  private schedule(workspace: WorkspaceRow, delaySeconds: number): void {
    const timer = setTimeout(() => {
      this.timers.delete(timer);
      if (!this.running) {
        return;
      }
      void this.pollWorkspace(workspace)
        .then((status) => {
          const config = getCurrentUserConfig();
          const isOpen = workspace.isOpen;
          const next = computePollDelaySeconds(
            config,
            isOpen,
            status?.pr_state ?? "none",
          );
          this.schedule(workspace, next);
        })
        .catch(() => {
          // A poll failure already surfaces via error_category; retry on cadence.
          this.schedule(
            workspace,
            computePollDelaySeconds(
              getCurrentUserConfig(),
              workspace.isOpen,
              "none",
            ),
          );
        });
    }, delaySeconds * 1000);
    if (typeof timer.unref === "function") {
      timer.unref();
    }
    this.timers.add(timer);
  }

  start(): void {
    if (this.running || !getCurrentUserConfig().pr_polling_enabled) {
      return;
    }
    this.running = true;
    for (const workspace of listRecentWorkspaces(getOrm()).filter(
      (workspace) => !workspace.isDeleted,
    )) {
      // Stagger the initial polls slightly so they don't all fire at t=0; the
      // throttle enforces the hard spacing once they dispatch.
      this.scheduled.add(workspace.objectId);
      this.schedule(workspace, 0);
    }
    // Poll workspaces created after boot too (the backend starts with none, so
    // every workspace — and its PR button — depends on this).
    this.unsubscribe = eventBus.subscribe((event) => {
      if (event.kind !== "data_model_change") {
        return;
      }
      for (const ref of event.changedEntities ?? []) {
        if (ref.type !== "workspace" || this.scheduled.has(ref.id)) {
          continue;
        }
        const workspace = getWorkspace(getOrm(), ref.id);
        if (workspace !== undefined && !workspace.isDeleted) {
          this.scheduled.add(ref.id);
          this.schedule(workspace, 0);
        }
      }
    });
  }

  stop(): void {
    this.running = false;
    this.unsubscribe?.();
    this.unsubscribe = undefined;
    this.scheduled.clear();
    for (const timer of this.timers) {
      clearTimeout(timer);
    }
    this.timers.clear();
  }
}

let singleton: PrPollingService | undefined;

export function getPrPollingService(): PrPollingService {
  if (singleton === undefined) {
    singleton = new PrPollingService();
  }
  return singleton;
}

export function resetPrPollingServiceForTests(): void {
  singleton?.stop();
  singleton = undefined;
}
