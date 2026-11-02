import { WorkspaceInitializationStrategy } from "~/api";

/**
 * How a creation mode treats one field of the create request: never sent, sent
 * when filled in, or needed before a create can go ahead.
 */
export type CreationFieldRule = "unused" | "optional" | "required";

type WorkspaceModeRules = {
  /** The new branch the workspace checks out (`requestedBranchName`). */
  branchName: CreationFieldRule;
  /** The existing branch the workspace starts from. */
  sourceBranch: CreationFieldRule;
};

/**
 * Mirrors `_validate_workspace_creation_request` in the backend's `web/app.py`,
 * which rejects a request that breaks these rules.
 */
export const WORKSPACE_MODE_RULES: Readonly<Record<WorkspaceInitializationStrategy, WorkspaceModeRules>> = {
  // In-place works on the repo's current branch.
  [WorkspaceInitializationStrategy.IN_PLACE]: { branchName: "unused", sourceBranch: "unused" },
  // A clone checks out the source branch, else the repo's current branch, and
  // creates the named branch only when one is given.
  [WorkspaceInitializationStrategy.CLONE]: { branchName: "optional", sourceBranch: "optional" },
  // `git worktree add -b <branch name> <source branch>` needs both.
  [WorkspaceInitializationStrategy.WORKTREE]: { branchName: "required", sourceBranch: "required" },
};

type CreationFields = {
  branchName: string | undefined;
  sourceBranch: string | undefined;
};

const toRequestValue = (rule: CreationFieldRule, value: string | undefined): string | undefined =>
  rule === "unused" ? undefined : value?.trim() || undefined;

/**
 * The fields as the create request carries them: trimmed, with blank values and
 * the fields the mode does not use left out.
 */
export const toCreateRequestFields = (
  inputs: { mode: WorkspaceInitializationStrategy } & CreationFields,
): CreationFields => {
  const rules = WORKSPACE_MODE_RULES[inputs.mode];
  return {
    branchName: toRequestValue(rules.branchName, inputs.branchName),
    sourceBranch: toRequestValue(rules.sourceBranch, inputs.sourceBranch),
  };
};

export const hasRequiredCreationFields = (
  inputs: { mode: WorkspaceInitializationStrategy } & CreationFields,
): boolean => {
  const rules = WORKSPACE_MODE_RULES[inputs.mode];
  const request = toCreateRequestFields(inputs);
  return (
    (rules.branchName !== "required" || request.branchName !== undefined) &&
    (rules.sourceBranch !== "required" || request.sourceBranch !== undefined)
  );
};
