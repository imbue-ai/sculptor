/**
 * TanStack Query mutation hooks for a repository's jj controls.
 *
 * Neither hook writes a store: the stream is the only writer of the project
 * row and of the repository's jj state, so a failed request leaves nothing to
 * roll back, and `onError` reports it. The "use jj" request resolves only
 * after the stream frame that carries the updated project.
 */

import { useMutation, type UseMutationResult } from "@tanstack/react-query";

import { colocateProjectWithJj, updateUseJjForNewWorkspaces } from "../../../api";
import { MUTATION_SETTLE_TIMEOUT_MS } from "./index";

type ProjectJjMutationOptions = {
  onError: (error: Error) => void;
};

type ColocateVars = {
  projectId: string;
};

export const useColocateProjectMutation = ({
  onError,
}: ProjectJjMutationOptions): UseMutationResult<unknown, Error, ColocateVars, unknown> =>
  useMutation({
    mutationFn: (vars: ColocateVars) =>
      colocateProjectWithJj({
        path: { project_id: vars.projectId },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    onError,
  });

type UseJjForNewWorkspacesVars = {
  projectId: string;
  useJjForNewWorkspaces: boolean;
};

export const useUseJjForNewWorkspacesMutation = ({
  onError,
}: ProjectJjMutationOptions): UseMutationResult<unknown, Error, UseJjForNewWorkspacesVars, unknown> =>
  useMutation({
    mutationFn: (vars: UseJjForNewWorkspacesVars) =>
      updateUseJjForNewWorkspaces({
        path: { project_id: vars.projectId },
        body: { useJjForNewWorkspaces: vars.useJjForNewWorkspaces },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    onError,
  });
