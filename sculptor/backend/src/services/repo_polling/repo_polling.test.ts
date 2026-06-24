import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import type { WorkspaceRow } from "~/db/schema";
import { eventBus } from "~/events";
import type { BusEvent } from "~/events/types";
import { runGit } from "~/git";
import { RepoPollingManager } from "~/services/repo_polling/manager";

describe("RepoPollingManager", () => {
  let repoDir: string;

  beforeEach(async () => {
    repoDir = mkdtempSync(path.join(tmpdir(), "sculptor-repopoll-"));
    await runGit(["init", "-b", "feature-x"], repoDir);
    writeFileSync(path.join(repoDir, "README.md"), "# demo\n");
    await runGit(["add", "-A"], repoDir);
    await runGit(
      ["-c", "user.email=t@t.co", "-c", "user.name=t", "commit", "-m", "init"],
      repoDir,
    );
    // A remote-tracking ref without a real remote, so `git branch -r` lists it.
    await runGit(
      ["update-ref", "refs/remotes/origin/feature-x", "HEAD"],
      repoDir,
    );
  });

  afterEach(() => {
    rmSync(repoDir, { recursive: true, force: true });
  });

  const stubWorkspace = {
    objectId: "ws_1",
    projectId: "prj_1",
  } as WorkspaceRow;

  it("emits branch + remote-branch events for an open workspace", async () => {
    const events: BusEvent[] = [];
    const unsubscribe = eventBus.subscribe((event) => events.push(event));
    const manager = new RepoPollingManager({
      workingDirForWorkspace: () => repoDir,
      intervalMs: 1_000,
    });

    const alive = await manager.pollWorkspace(stubWorkspace);
    unsubscribe();

    expect(alive).toBe(true);
    const branch = events.find((e) => e.kind === "workspace_branch");
    expect(
      (branch as { status?: { current_branch?: string } } | undefined)?.status
        ?.current_branch,
    ).toBe("feature-x");
    const remote = events.find((e) => e.kind === "workspace_remote_branches");
    expect(
      (remote as { status?: { remote_branches?: string[] } } | undefined)
        ?.status?.remote_branches,
    ).toContain("origin/feature-x");
  });

  it("stops polling a workspace whose checkout is torn down", async () => {
    const manager = new RepoPollingManager({
      workingDirForWorkspace: () => path.join(repoDir, "gone"),
      intervalMs: 1_000,
    });
    const alive = await manager.pollWorkspace(stubWorkspace);
    expect(alive).toBe(false);
  });
});
