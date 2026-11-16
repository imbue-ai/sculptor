// Which branch a pull request names as its base is the backend's call: it
// streams the base name of every target candidate and of the workspace's own
// target (`WorkspaceTargetBranchesInfo.prBaseNames`), so nothing here parses
// git or jj ref syntax.

/**
 * Whether a pull request into `prBaseName` goes somewhere other than the
 * workspace's target. Until the backend has named the target's base, PR
 * status's own report that it does stands.
 */
export const isPrBaseOtherThanTarget = (inputs: {
  prBaseName: string;
  targetRef: string;
  prBaseNames: Readonly<Record<string, string>>;
}): boolean => inputs.prBaseNames[inputs.targetRef] !== inputs.prBaseName;

/**
 * The target candidate that opens pull requests into `prBaseName`, or null when
 * none does. Pull requests live on a remote, so a candidate qualified by a
 * remote (whose ref is not its bare base name) wins over a local one.
 */
export const findTargetForPrBase = (inputs: {
  prBaseName: string;
  targetBranches: ReadonlyArray<string>;
  prBaseNames: Readonly<Record<string, string>>;
}): string | null => {
  const candidates = inputs.targetBranches.filter((ref) => inputs.prBaseNames[ref] === inputs.prBaseName);
  return candidates.find((ref) => ref !== inputs.prBaseName) ?? candidates[0] ?? null;
};
