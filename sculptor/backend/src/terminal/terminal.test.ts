import { tmpdir } from "node:os";

import { afterEach, describe, expect, it } from "vitest";

import { buildShellEnv, type PtyProcess, spawnPty } from "~/terminal/pty";
import { reapStalePid, TerminalManager } from "~/terminal/manager";

const delay = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

describe("buildShellEnv", () => {
  it("scrubs SESSION_TOKEN and SCULPT_/SCULPTOR_/_PYI_ vars and forces TERM", () => {
    const env = buildShellEnv({}, false, {
      SESSION_TOKEN: "secret",
      SCULPT_API_PORT: "1",
      SCULPTOR_FOLDER: "/x",
      _PYI_THING: "1",
      HOME: "/home/dev",
    } as NodeJS.ProcessEnv);
    expect(env.SESSION_TOKEN).toBeUndefined();
    expect(env.SCULPT_API_PORT).toBeUndefined();
    expect(env.SCULPTOR_FOLDER).toBeUndefined();
    expect(env._PYI_THING).toBeUndefined();
    expect(env.HOME).toBe("/home/dev");
    expect(env.TERM).toBe("xterm-256color");
  });

  it("prepends PATH and respects override", () => {
    const env = buildShellEnv({ PATH: "/extra", FOO: "new" }, false, { PATH: "/usr/bin", FOO: "old" } as NodeJS.ProcessEnv);
    expect(env.PATH).toBe(`/extra:/usr/bin`);
    expect(env.FOO).toBe("old"); // not overridden
    expect(buildShellEnv({ FOO: "new" }, true, { FOO: "old" } as NodeJS.ProcessEnv).FOO).toBe("new");
  });
});

describe("spawnPty", () => {
  const spawned: PtyProcess[] = [];

  afterEach(() => {
    for (const p of spawned) {
      p.kill();
    }
    spawned.length = 0;
  });

  it("streams data, exposes pid, resizes, and exits", async () => {
    const pty = spawnPty({ cwd: tmpdir(), shell: "/bin/sh" });
    spawned.push(pty);
    let output = "";
    let exitCode: number | undefined;
    pty.onData((d) => {
      output += d;
    });
    pty.onExit((e) => {
      exitCode = e.exitCode;
    });
    expect(typeof pty.pid).toBe("number");

    pty.write("echo hello123\n");
    await delay(300);
    expect(output).toContain("hello123");

    expect(() => pty.resize(100, 40)).not.toThrow();

    pty.write("exit\n");
    await delay(300);
    expect(exitCode).toBe(0);
  });
});

describe("TerminalManager", () => {
  let manager: TerminalManager;

  afterEach(() => {
    manager.closeAll();
  });

  it("creates distinct terminals per index, looks them up, and closes them", () => {
    manager = new TerminalManager();
    const t0 = manager.getOrCreateTerminal(0, { cwd: tmpdir(), shell: "/bin/sh" });
    const t0Again = manager.getOrCreateTerminal(0, { cwd: tmpdir(), shell: "/bin/sh" });
    const t1 = manager.getOrCreateTerminal(1, { cwd: tmpdir(), shell: "/bin/sh" });
    expect(t0).toBe(t0Again);
    expect(t0.pid).not.toBe(t1.pid);
    expect(manager.getTerminal(0)).toBe(t0);

    manager.closeTerminal(0);
    expect(manager.getTerminal(0)).toBeUndefined();
  });

  it("reaps a stale pid as a no-op when the pid is gone", () => {
    manager = new TerminalManager();
    expect(() => reapStalePid(2 ** 30)).not.toThrow();
  });
});
