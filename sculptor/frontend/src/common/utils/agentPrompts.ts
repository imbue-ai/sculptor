// The messages the Commit and Create PR actions send to a workspace's agent,
// built in one place so every entry point sends the same text.

export const buildCommitMessage = (inputs: { prompt: string }): string => inputs.prompt;

// An empty target names no branch, so it gets the same message as no target.
export const buildCreatePrMessage = (inputs: { prompt: string; targetBranch: string | null }): string =>
  inputs.targetBranch
    ? `${inputs.prompt}\n\nTarget the pull request against \`${inputs.targetBranch}\`.`
    : inputs.prompt;
