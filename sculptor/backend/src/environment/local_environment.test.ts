import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { LocalEnvironment } from "~/environment";

describe("LocalEnvironment paths", () => {
  it("derives the workspace layout for worktree/clone vs in-place", () => {
    const root = "/data/workspaces/abc123";
    const worktree = new LocalEnvironment({ root, initializationStrategy: "WORKTREE" });
    expect(worktree.getWorkingDirectory()).toBe(path.join(root, "code"));
    expect(worktree.getStatePath("tsk_1")).toBe(path.join(root, "state", "tasks", "tsk_1"));
    expect(worktree.getArtifactsPath("tsk_1")).toBe(path.join(root, "artifacts", "tasks", "tsk_1"));
    expect(worktree.getAttachmentsPath()).toBe(path.join(root, "attachments"));
    expect(worktree.getRootPath()).toBe(root);

    const inPlace = new LocalEnvironment({
      root,
      initializationStrategy: "IN_PLACE",
      repoHostPath: "/home/dev/repo",
    });
    expect(inPlace.getWorkingDirectory()).toBe("/home/dev/repo");

    expect(() => new LocalEnvironment({ root, initializationStrategy: "IN_PLACE" }).getWorkingDirectory()).toThrow();
  });
});

describe("LocalEnvironment file ops", () => {
  let dir: string;
  let env: LocalEnvironment;

  beforeEach(() => {
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-env-"));
    env = new LocalEnvironment({ root: dir, initializationStrategy: "WORKTREE" });
  });

  afterEach(() => {
    env.destroy();
    rmSync(dir, { recursive: true, force: true });
  });

  it("round-trips text and binary and reflects existence", async () => {
    const textFile = path.join(dir, "nested", "a.txt");
    expect(await env.exists(textFile)).toBe(false);
    await env.writeFile(textFile, "hello");
    expect(await env.exists(textFile)).toBe(true);
    expect(await env.readTextFile(textFile)).toBe("hello");

    const binFile = path.join(dir, "b.bin");
    await env.writeFile(binFile, new Uint8Array([1, 2, 3]));
    expect(Array.from(await env.readBinaryFile(binFile))).toEqual([1, 2, 3]);

    await env.deleteFileOrDirectory(path.join(dir, "nested"));
    expect(await env.exists(textFile)).toBe(false);
  });
});

describe("LocalEnvironment process ops", () => {
  let dir: string;
  let env: LocalEnvironment;

  beforeEach(() => {
    dir = realpathSync(mkdtempSync(path.join(tmpdir(), "sculptor-env-proc-")));
    // IN_PLACE so the working directory is `dir` (which exists) — the worktree
    // `dir/code` is created by the git layer (Task 3.2), not here.
    env = new LocalEnvironment({ root: dir, initializationStrategy: "IN_PLACE", repoHostPath: dir });
  });

  afterEach(() => {
    env.destroy();
    rmSync(dir, { recursive: true, force: true });
  });

  it("runs a process to completion capturing exit code and output", async () => {
    const result = await env.runProcessToCompletion(["sh", "-c", "printf out; printf err 1>&2; exit 3"]);
    expect(result.exitCode).toBe(3);
    expect(result.stdout).toBe("out");
    expect(result.stderr).toBe("err");
  });

  it("runs a process with the working directory as cwd by default", async () => {
    const result = await env.runProcessToCompletion(["sh", "-c", "pwd"]);
    expect(result.stdout.trim()).toBe(dir);
  });

  it("spawns a background process and kills it on destroy", () => {
    const handle = env.runProcessInBackground(["sleep", "30"]);
    expect(typeof handle.pid).toBe("number");
    expect(env.isAlive(handle)).toBe(true);
    env.destroy();
    expect(handle.child.killed).toBe(true);
  });
});
