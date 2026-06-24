import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";

import { parse as parseToml } from "smol-toml";

import { getSculptorFolder } from "~/config/sculptor_folder";

// Terminal-agent registry (services/terminal_agent_registry/registry.py).
// Registrations are ordinary user-owned TOML files under
// {sculptor_folder}/terminal_agents, RE-READ ON DEMAND (REQ-INT-030): the
// list is never cached for the process lifetime so edits are picked up (params
// are stamped at agent creation, so running agents are unaffected). The
// registration_id IS the filename stem (claude-code.toml -> "claude-code").

const REGISTRATIONS_DIR_NAME = "terminal_agents";
const REGISTRATION_ID_PATTERN = /^[a-z0-9][a-z0-9_-]*$/;
const PLACEHOLDER_PATTERN = /\{[^}]*\}/g;

export const SESSION_ID_PLACEHOLDER = "{session_id}";
export const SCULPTOR_DIRECTORY_PLACEHOLDER = "{sculptor_directory}";
export const TERMINAL_AGENTS_DIRECTORY_PLACEHOLDER =
  "{terminal_agents_directory}";

const DIRECTORY_PLACEHOLDERS = new Set([
  SCULPTOR_DIRECTORY_PLACEHOLDER,
  TERMINAL_AGENTS_DIRECTORY_PLACEHOLDER,
]);
const LAUNCH_COMMAND_PLACEHOLDERS = DIRECTORY_PLACEHOLDERS;
const RESUME_COMMAND_PLACEHOLDERS = new Set([
  ...DIRECTORY_PLACEHOLDERS,
  SESSION_ID_PLACEHOLDER,
]);

export interface TerminalAgentRegistration {
  registrationId: string;
  displayName: string;
  // May contain the directory placeholders; rendered with literal replacement.
  launchCommand: string;
  // May contain {session_id} plus the directory placeholders.
  resumeCommandTemplate: string | null;
  acceptsAutomatedPrompts: boolean;
}

export function getRegistrationsDir(): string {
  return path.join(getSculptorFolder(), REGISTRATIONS_DIR_NAME);
}

function rejectUnknownPlaceholders(
  command: string,
  allowed: ReadonlySet<string>,
  field: string,
): void {
  const unknown = [
    ...new Set(
      (command.match(PLACEHOLDER_PATTERN) ?? []).filter((p) => !allowed.has(p)),
    ),
  ].sort();
  if (unknown.length > 0) {
    throw new Error(
      `${field} contains unsupported placeholder(s) ${unknown.join(", ")}; allowed: ${[...allowed].sort().join(", ")}`,
    );
  }
}

function parseRegistration(
  registrationId: string,
  data: Record<string, unknown>,
): TerminalAgentRegistration {
  const displayName = data.display_name;
  const launchCommand = data.launch_command;
  if (typeof displayName !== "string" || typeof launchCommand !== "string") {
    throw new Error("display_name and launch_command are required strings");
  }
  const resumeCommandTemplate =
    typeof data.resume_command_template === "string"
      ? data.resume_command_template
      : null;
  rejectUnknownPlaceholders(
    launchCommand,
    LAUNCH_COMMAND_PLACEHOLDERS,
    "launch_command",
  );
  if (resumeCommandTemplate !== null) {
    rejectUnknownPlaceholders(
      resumeCommandTemplate,
      RESUME_COMMAND_PLACEHOLDERS,
      "resume_command_template",
    );
  }
  return {
    registrationId,
    displayName,
    launchCommand,
    resumeCommandTemplate,
    acceptsAutomatedPrompts: data.accepts_automated_prompts === true,
  };
}

// List all registrations, re-reading the directory each call (REQ-INT-030). A
// malformed or mis-named file is skipped rather than failing the whole list.
export function listRegistrations(): TerminalAgentRegistration[] {
  const dir = getRegistrationsDir();
  if (!existsSync(dir)) {
    return [];
  }
  const registrations: TerminalAgentRegistration[] = [];
  for (const fileName of readdirSync(dir).sort()) {
    if (!fileName.endsWith(".toml")) {
      continue;
    }
    const registrationId = fileName.slice(0, -".toml".length);
    if (!REGISTRATION_ID_PATTERN.test(registrationId)) {
      continue;
    }
    try {
      const data = parseToml(
        readFileSync(path.join(dir, fileName), "utf8"),
      ) as Record<string, unknown>;
      registrations.push(parseRegistration(registrationId, data));
    } catch {
      // Skip unreadable / invalid registrations (logged in Python; here we just
      // exclude them so one bad file can't break the picker).
    }
  }
  return registrations;
}

export function getRegistration(
  registrationId: string,
): TerminalAgentRegistration | null {
  return (
    listRegistrations().find(
      (registration) => registration.registrationId === registrationId,
    ) ?? null
  );
}

export interface RenderContext {
  sculptorDirectory: string;
  terminalAgentsDirectory: string;
  sessionId?: string;
}

// Render a registration command by LITERAL string replacement (REQ-INT-031),
// NOT a format/template engine: a value containing `{}` or `%` passes through
// unharmed. {session_id} is only substituted when a session id is supplied.
export function renderTerminalCommand(
  template: string,
  context: RenderContext,
): string {
  let rendered = template
    .split(SCULPTOR_DIRECTORY_PLACEHOLDER)
    .join(context.sculptorDirectory)
    .split(TERMINAL_AGENTS_DIRECTORY_PLACEHOLDER)
    .join(context.terminalAgentsDirectory);
  if (context.sessionId !== undefined) {
    rendered = rendered.split(SESSION_ID_PLACEHOLDER).join(context.sessionId);
  }
  return rendered;
}
