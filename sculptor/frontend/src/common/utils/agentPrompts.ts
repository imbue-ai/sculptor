// The messages the Commit and Create PR actions send to a workspace's agent,
// built in one place so every entry point sends the same text.

/** A prompt a workspace's agent is sent from one of its actions; each has a git setting and an optional jj one. */
export type AgentPromptKind = "commit" | "pr-creation";

/**
 * The bookmark a jj workspace's messages name: the one on its work, or, until
 * it has one, the one it was created to set (null when none was requested).
 */
export type JjPromptBookmark = { status: "set"; name: string } | { status: "missing"; requestedName: string | null };

/** A jj workspace's target bookmark, and the branch a pull request names as its base once the backend has named it. */
type JjPromptTarget = { bookmark: string; prBaseName: string | null };

/** What a workspace's Commit and Create PR messages say about it, by its version control. */
export type PromptWorkspace =
  | { vcs: "git"; targetBranch: string | null }
  | { vcs: "jj"; bookmark: JjPromptBookmark; target: JjPromptTarget | null };

type CommitPromptWorkspace = { vcs: "git" } | { vcs: "jj"; bookmark: JjPromptBookmark };

const JJ_PREAMBLE = "This is a jj workspace with no git inside, so use jj rather than git.";

const withSuffix = (prompt: string, suffix: string): string => `${prompt}\n\n${suffix}`;

const buildJjCommitSuffix = (bookmark: JjPromptBookmark): string => {
  if (bookmark.status === "set") {
    return `Then move the bookmark \`${bookmark.name}\` onto the change you committed: \`jj bookmark set ${bookmark.name} -r @-\` after \`jj commit\`.`;
  }

  if (bookmark.requestedName !== null) {
    return `Then create the bookmark \`${bookmark.requestedName}\` on the change you committed: \`jj bookmark create ${bookmark.requestedName} -r @-\` after \`jj commit\`.`;
  }
  return "Then create a bookmark on the change you committed: `jj bookmark create <name> -r @-` after `jj commit`.";
};

export const buildCommitMessage = (inputs: { prompt: string; workspace: CommitPromptWorkspace }): string => {
  const { prompt, workspace } = inputs;
  switch (workspace.vcs) {
    case "git":
      return prompt;
    case "jj":
      return withSuffix(prompt, `${JJ_PREAMBLE} ${buildJjCommitSuffix(workspace.bookmark)}`);
  }
};

// Where a jj workspace's pull request goes: the target's base when the backend
// has named it, else whatever branch the target bookmark tracks.
const describeJjPrDestination = (head: string, target: JjPromptTarget | null): string => {
  if (target === null) {
    return `with \`gh pr create --head ${head}\``;
  }

  if (target.prBaseName === null) {
    return `into the branch the target bookmark \`${target.bookmark}\` tracks`;
  }
  return `into \`${target.prBaseName}\` with \`gh pr create --head ${head} --base ${target.prBaseName}\``;
};

const buildJjPrSuffix = (bookmark: JjPromptBookmark, target: JjPromptTarget | null): string => {
  const name = bookmark.status === "set" ? bookmark.name : bookmark.requestedName;
  if (name === null) {
    return (
      "First create a bookmark on your latest described change with `jj bookmark create <name> -r <change>`. " +
      `Push the bookmark with \`jj git push -b <name>\`, then open the pull request from it ${describeJjPrDestination("<name>", target)}.`
    );
  }
  const createFirst =
    bookmark.status === "missing"
      ? `First create the bookmark \`${name}\` on your latest described change with \`jj bookmark create ${name} -r <change>\`. `
      : "";
  return `${createFirst}Push the bookmark \`${name}\` with \`jj git push -b ${name}\`, then open the pull request from \`${name}\` ${describeJjPrDestination(name, target)}.`;
};

export const buildCreatePrMessage = (inputs: { prompt: string; workspace: PromptWorkspace }): string => {
  const { prompt, workspace } = inputs;
  switch (workspace.vcs) {
    case "git":
      // An empty target names no branch, so it gets the same message as no target.
      return workspace.targetBranch
        ? withSuffix(prompt, `Target the pull request against \`${workspace.targetBranch}\`.`)
        : prompt;
    case "jj":
      return withSuffix(prompt, `${JJ_PREAMBLE} ${buildJjPrSuffix(workspace.bookmark, workspace.target)}`);
  }
};
