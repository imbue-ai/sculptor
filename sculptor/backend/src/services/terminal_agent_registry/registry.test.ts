import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG } from "~/config/sculptor_folder";
import {
  renderResumeCommand,
  stampTerminalAgentParams,
} from "~/services/terminal_agent_registry/launch";
import {
  getRegistrationsDir,
  listRegistrations,
  renderTerminalCommand,
} from "~/services/terminal_agent_registry/registry";

describe("terminal-agent registry", () => {
  let dir: string;
  let previousFolder: string | undefined;

  beforeEach(() => {
    previousFolder = process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    dir = mkdtempSync(path.join(tmpdir(), "sculptor-tareg-"));
    process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = dir;
  });

  afterEach(() => {
    if (previousFolder === undefined) {
      delete process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG];
    } else {
      process.env[SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG] = previousFolder;
    }
    rmSync(dir, { recursive: true, force: true });
  });

  function writeRegistration(fileName: string, body: string): void {
    const regDir = getRegistrationsDir();
    mkdirSync(regDir, { recursive: true });
    writeFileSync(path.join(regDir, fileName), body);
  }

  it("returns [] when no registrations directory exists", () => {
    expect(listRegistrations()).toEqual([]);
  });

  it("discovers a TOML registration with the id from the filename stem", () => {
    writeRegistration(
      "claude-code.toml",
      'display_name = "Claude Code"\nlaunch_command = "claude"\naccepts_automated_prompts = true\n',
    );
    const registrations = listRegistrations();
    expect(registrations).toHaveLength(1);
    expect(registrations[0]).toMatchObject({
      registrationId: "claude-code",
      displayName: "Claude Code",
      launchCommand: "claude",
      acceptsAutomatedPrompts: true,
    });
  });

  it("re-reads on demand — a newly written file appears without restart", () => {
    expect(listRegistrations()).toHaveLength(0);
    writeRegistration(
      "foo.toml",
      'display_name = "Foo"\nlaunch_command = "foo"\n',
    );
    expect(listRegistrations()).toHaveLength(1);
  });

  it("skips invalid registration ids and malformed files", () => {
    writeRegistration(
      "Bad_Id.toml",
      'display_name = "x"\nlaunch_command = "x"\n',
    ); // uppercase id
    writeRegistration("broken.toml", "this is = not valid toml ===");
    writeRegistration(
      "ok.toml",
      'display_name = "Ok"\nlaunch_command = "ok"\n',
    );
    expect(listRegistrations().map((r) => r.registrationId)).toEqual(["ok"]);
  });

  it("rejects a command with an unsupported placeholder", () => {
    writeRegistration(
      "bad.toml",
      'display_name = "x"\nlaunch_command = "x {nope}"\n',
    );
    expect(listRegistrations()).toHaveLength(0);
  });

  it("substitutes placeholders by LITERAL replacement (REQ-INT-031)", () => {
    // A value containing format-like braces/percent must pass through unharmed.
    const rendered = renderTerminalCommand(
      "run {sculptor_directory}/x --fmt '{}' --pct '%s' --sid {session_id}",
      {
        sculptorDirectory: "/home/u/.sculptor",
        terminalAgentsDirectory: "/home/u/.sculptor/terminal_agents",
        sessionId: "sess_42",
      },
    );
    expect(rendered).toBe(
      "run /home/u/.sculptor/x --fmt '{}' --pct '%s' --sid sess_42",
    );
  });

  it("stamps params at creation and renders the resume command with the session id", () => {
    writeRegistration(
      "claude-code.toml",
      'display_name = "Claude Code"\nlaunch_command = "claude --dir {terminal_agents_directory}"\n' +
        'resume_command_template = "claude --resume {session_id} --dir {terminal_agents_directory}"\n',
    );
    const stamped = stampTerminalAgentParams("claude-code");
    expect(stamped).not.toBeNull();
    expect(stamped!.launchCommand).toBe(
      `claude --dir ${getRegistrationsDir()}`,
    );
    // Resume template keeps {session_id} until resume, then is filled literally.
    expect(stamped!.resumeCommandTemplate).toContain("{session_id}");
    expect(renderResumeCommand(stamped!, "sess_9")).toBe(
      `claude --resume sess_9 --dir ${getRegistrationsDir()}`,
    );
  });

  it("returns null when stamping an unknown registration", () => {
    expect(stampTerminalAgentParams("nope")).toBeNull();
  });
});
