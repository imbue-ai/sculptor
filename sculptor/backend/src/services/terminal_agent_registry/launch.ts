import { getSculptorFolder } from "~/config/sculptor_folder";
import {
  getRegistration,
  getRegistrationsDir,
  renderTerminalCommand,
  type TerminalAgentRegistration,
} from "~/services/terminal_agent_registry/registry";

// Stamp a registered terminal agent's resolved params at agent creation
// (REQ-INT-031). The launch command is rendered by literal substitution NOW, so
// a later TOML edit does not retroactively change a running agent — the stamped
// command is persisted into the agent's config and reused on resume.

export interface StampedTerminalAgentParams {
  registrationId: string;
  displayName: string;
  // The launch command with directory placeholders already substituted.
  launchCommand: string;
  // The resume template (still carrying {session_id}, filled per-resume) or null.
  resumeCommandTemplate: string | null;
  acceptsAutomatedPrompts: boolean;
}

function directoryContext(): {
  sculptorDirectory: string;
  terminalAgentsDirectory: string;
} {
  return {
    sculptorDirectory: getSculptorFolder(),
    terminalAgentsDirectory: getRegistrationsDir(),
  };
}

// Resolve + stamp the registration's launch params at creation time. Returns
// null when the registration id is unknown.
export function stampTerminalAgentParams(
  registrationId: string,
): StampedTerminalAgentParams | null {
  const registration: TerminalAgentRegistration | null =
    getRegistration(registrationId);
  if (registration === null) {
    return null;
  }
  const context = directoryContext();
  return {
    registrationId: registration.registrationId,
    displayName: registration.displayName,
    launchCommand: renderTerminalCommand(registration.launchCommand, context),
    resumeCommandTemplate: registration.resumeCommandTemplate,
    acceptsAutomatedPrompts: registration.acceptsAutomatedPrompts,
  };
}

// Render the resume command for a stamped agent, substituting the live session
// id (literal replacement, REQ-INT-031). Returns null when the registration has
// no resume template.
export function renderResumeCommand(
  params: StampedTerminalAgentParams,
  sessionId: string,
): string | null {
  if (params.resumeCommandTemplate === null) {
    return null;
  }
  return renderTerminalCommand(params.resumeCommandTemplate, {
    ...directoryContext(),
    sessionId,
  });
}
