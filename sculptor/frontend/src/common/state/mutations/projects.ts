/**
 * TanStack Query mutation hooks for per-project (repository) settings.
 *
 * The WS stream is the only writer of project state (`updateProjectsAtom`), so
 * no hook here writes a store: a successful save reaches the screen through the
 * stream, and a failed one leaves the store untouched for the caller to report.
 *
 * `onError` is a mutation-level callback so that it still runs if the caller
 * unmounts before the request fails; per-call `mutate` callbacks do not.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { updateNamingPattern, updateWorkspaceSetupCommand } from "../../../api";
import { MUTATION_SETTLE_TIMEOUT_MS } from "./index";

type ProjectSettingMutationOptions = {
  onError: (error: Error) => void;
};

type WorkspaceSetupCommandVars = {
  projectId: string;
  // null: track the current default. "": run nothing. Any other string: a custom command.
  command: string | null;
};

export const useWorkspaceSetupCommandMutation = ({
  onError,
}: ProjectSettingMutationOptions): UseMutationResult<unknown, Error, WorkspaceSetupCommandVars, unknown> =>
  useMutation({
    mutationFn: (vars: WorkspaceSetupCommandVars) =>
      updateWorkspaceSetupCommand({
        path: { project_id: vars.projectId },
        body: { workspaceSetupCommand: vars.command },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    onError,
  });

type NamingPatternVars = {
  projectId: string;
  // "" clears the override, so the global default applies.
  pattern: string;
};

export const useNamingPatternMutation = ({
  onError,
}: ProjectSettingMutationOptions): UseMutationResult<unknown, Error, NamingPatternVars, unknown> =>
  useMutation({
    mutationFn: (vars: NamingPatternVars) =>
      updateNamingPattern({
        path: { project_id: vars.projectId },
        body: { namingPattern: vars.pattern },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    onError,
  });
