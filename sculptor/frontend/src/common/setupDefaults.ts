// Must match `DEFAULT_WORKSPACE_SETUP_COMMAND` in
// sculptor/services/workspace_service/api.py.
export const DEFAULT_WORKSPACE_SETUP_COMMAND = "git fetch origin 2>/dev/null || true";

// Mirrors `resolve_workspace_setup_command` in
// sculptor/services/workspace_service/api.py:
//   null         → returns the current default (project never configured)
//   ""           → returns null (user explicitly cleared, run nothing)
//   other string → returns as-is (user's custom command)
export const resolveWorkspaceSetupCommand = (stored: string | null | undefined): string | null => {
  if (stored === null || stored === undefined) return DEFAULT_WORKSPACE_SETUP_COMMAND;
  if (stored === "") return null;
  return stored;
};
