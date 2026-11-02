/**
 * TanStack Query mutation hooks for per-project (repository) settings.
 *
 * The WS stream is the only writer of project state (`updateProjectsAtom`), and
 * these requests resolve only once the frame carrying the updated project has
 * arrived, so no hook here writes a store: success is already on screen, and
 * failure leaves the store untouched for the caller to report.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { updateNamingPattern, updateWorkspaceSetupCommand } from "../../../api";
import { MUTATION_SETTLE_TIMEOUT_MS } from "./index";

type WorkspaceSetupCommandVars = {
  projectId: string;
  // null: track the current default. "": run nothing. Any other string: a custom command.
  command: string | null;
};

/** Save a project's workspace setup command. */
export const useWorkspaceSetupCommandMutation = (): UseMutationResult<
  unknown,
  Error,
  WorkspaceSetupCommandVars,
  unknown
> =>
  useMutation({
    mutationFn: (vars: WorkspaceSetupCommandVars) =>
      updateWorkspaceSetupCommand({
        path: { project_id: vars.projectId },
        body: { workspaceSetupCommand: vars.command },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
  });

type NamingPatternVars = {
  projectId: string;
  // "" clears the override, so the global default applies.
  pattern: string;
};

/** Save a project's branch-naming pattern override. */
export const useNamingPatternMutation = (): UseMutationResult<unknown, Error, NamingPatternVars, unknown> =>
  useMutation({
    mutationFn: (vars: NamingPatternVars) =>
      updateNamingPattern({
        path: { project_id: vars.projectId },
        body: { namingPattern: vars.pattern },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
  });
