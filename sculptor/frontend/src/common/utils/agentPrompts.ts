// The messages the Commit and Create PR actions send to a workspace's agent.
// Every entry point builds its message here, so the button, the menus and the
// palette all send the same text for the same workspace.

export const buildCommitMessage = (inputs: { prompt: string }): string => inputs.prompt;

// An empty target names no branch, so it gets the same message as no target.
export const buildCreatePrMessage = (inputs: { prompt: string; targetBranch: string | null }): string =>
  inputs.targetBranch
    ? `${inputs.prompt}\n\nTarget the pull request against \`${inputs.targetBranch}\`.`
    : inputs.prompt;
