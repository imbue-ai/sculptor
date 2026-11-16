import { WorkspaceInitializationStrategy } from "~/api";

/**
 * How a creation mode treats one field of the create request: never sent, sent
 * when filled in, or needed before a create can go ahead.
 */
export type CreationFieldRule = "unused" | "optional" | "required";

/**
 * How a creation mode treats the source it starts from. A mode that takes no
 * source says why on the disabled picker. One that takes a source either fills
 * in the repository's current branch before the user picks one, or leaves it
 * out so the backend starts the workspace from its target.
 */
type SourceFieldRule =
  { rule: "unused"; whyUnused: string } | { rule: "optional" | "required"; seed: "current-branch" | "none" };

type WorkspaceModeRules = {
  /** What the name the workspace creates is: a git branch or a jj bookmark. */
  nameNoun: "branch" | "bookmark";
  /** The new branch or bookmark the workspace creates (`requestedBranchName`). */
  branchName: CreationFieldRule;
  /** The existing branch or bookmark the workspace starts from. */
  sourceBranch: SourceFieldRule;
};

/**
 * Mirrors `_validate_workspace_creation_request` in the backend's `web/app.py`,
 * which rejects a request that breaks these rules.
 */
export const WORKSPACE_MODE_RULES: Readonly<Record<WorkspaceInitializationStrategy, WorkspaceModeRules>> = {
  [WorkspaceInitializationStrategy.IN_PLACE]: {
    nameNoun: "branch",
    branchName: "unused",
    sourceBranch: { rule: "unused", whyUnused: "In-place workspaces use the current branch in your repository" },
  },
  // A clone checks out the source branch, else the repo's current branch, and
  // creates the named branch only when one is given.
  [WorkspaceInitializationStrategy.CLONE]: {
    nameNoun: "branch",
    branchName: "optional",
    sourceBranch: { rule: "optional", seed: "current-branch" },
  },
  // `git worktree add -b <branch name> <source branch>` needs both.
  [WorkspaceInitializationStrategy.WORKTREE]: {
    nameNoun: "branch",
    branchName: "required",
    sourceBranch: { rule: "required", seed: "current-branch" },
  },
  // A jj workspace needs the name of the bookmark it will set; its base defaults to its target.
  [WorkspaceInitializationStrategy.JJ_WORKSPACE]: {
    nameNoun: "bookmark",
    branchName: "required",
    sourceBranch: { rule: "optional", seed: "none" },
  },
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
    sourceBranch: toRequestValue(rules.sourceBranch.rule, inputs.sourceBranch),
  };
};

export const hasRequiredCreationFields = (
  inputs: { mode: WorkspaceInitializationStrategy } & CreationFields,
): boolean => {
  const rules = WORKSPACE_MODE_RULES[inputs.mode];
  const request = toCreateRequestFields(inputs);
  return (
    (rules.branchName !== "required" || request.branchName !== undefined) &&
    (rules.sourceBranch.rule !== "required" || request.sourceBranch !== undefined)
  );
};

/**
 * The source a mode shows before the user picks one: the repository's current
 * branch, or nothing for a mode whose base the backend defaults.
 */
export const defaultSourceFor = (inputs: {
  mode: WorkspaceInitializationStrategy;
  currentBranch: string | undefined;
}): string | undefined => {
  const source = WORKSPACE_MODE_RULES[inputs.mode].sourceBranch;
  return source.rule === "unused" || source.seed === "current-branch" ? inputs.currentBranch : undefined;
};

/** Whether jj can be used, from the dependency status; unknown until the status has arrived. */
export type JjAvailability = "available" | "unavailable" | "unknown";

/**
 * Which version control a repository's new isolated workspaces use. A
 * repository that uses jj for its new workspaces while jj is unavailable
 * creates none: there is no falling back to a git worktree. Until the
 * dependency status says whether jj works, such a repository is still being
 * checked, and creates nothing yet either.
 */
export type RepositoryWorkspaceVcs = "git" | "jj" | "jj-checking" | "jj-unavailable";

export const repositoryWorkspaceVcs = (facts: {
  /** `ProjectJjState.createsJjWorkspaces`: the flag is on, the repository is colocated and jj is available. */
  createsJjWorkspaces: boolean;
  /** The project's stored `useJjForNewWorkspaces` flag. */
  usesJjForNewWorkspaces: boolean;
  jjAvailability: JjAvailability;
}): RepositoryWorkspaceVcs => {
  if (facts.createsJjWorkspaces) return "jj";
  if (!facts.usesJjForNewWorkspaces) return "git";
  switch (facts.jjAvailability) {
    case "available":
      return "git";
    case "unavailable":
      return "jj-unavailable";
    case "unknown":
      return "jj-checking";
  }
};

/** A mode that gives the workspace a checkout of its own: a git worktree or a jj workspace. */
export type IsolatedCreationMode =
  typeof WorkspaceInitializationStrategy.WORKTREE | typeof WorkspaceInitializationStrategy.JJ_WORKSPACE;

/** The mode a repository offers in place of a plain worktree. */
export const isolatedModeFor = (vcs: RepositoryWorkspaceVcs): IsolatedCreationMode =>
  vcs === "git" ? WorkspaceInitializationStrategy.WORKTREE : WorkspaceInitializationStrategy.JJ_WORKSPACE;

/**
 * The mode to create with in a repository, from the mode last used there. A
 * worktree and a jj workspace stand for each other, so the repository's own
 * isolated mode replaces either; clone and in-place stay git under their flags.
 */
export const resolveCreationMode = (inputs: {
  remembered: WorkspaceInitializationStrategy | undefined;
  vcs: RepositoryWorkspaceVcs;
}): WorkspaceInitializationStrategy => {
  switch (inputs.remembered) {
    case WorkspaceInitializationStrategy.CLONE:
    case WorkspaceInitializationStrategy.IN_PLACE:
      return inputs.remembered;
    case WorkspaceInitializationStrategy.WORKTREE:
    case WorkspaceInitializationStrategy.JJ_WORKSPACE:
    case undefined:
      return isolatedModeFor(inputs.vcs);
  }
};

/**
 * The modes the picker lists: the repository's isolated mode, then clone and
 * in-place when their flags are on. A mode whose flag is off stays listed
 * while it is the current value, so the user can always leave it.
 */
export const offeredCreationModes = (inputs: {
  isolatedMode: IsolatedCreationMode;
  value: WorkspaceInitializationStrategy;
  isCloneEnabled: boolean;
  isInPlaceEnabled: boolean;
}): ReadonlyArray<WorkspaceInitializationStrategy> => [
  inputs.isolatedMode,
  ...(inputs.isCloneEnabled || inputs.value === WorkspaceInitializationStrategy.CLONE
    ? [WorkspaceInitializationStrategy.CLONE]
    : []),
  ...(inputs.isInPlaceEnabled || inputs.value === WorkspaceInitializationStrategy.IN_PLACE
    ? [WorkspaceInitializationStrategy.IN_PLACE]
    : []),
];
