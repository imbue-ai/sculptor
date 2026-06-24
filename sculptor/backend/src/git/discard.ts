import path from "node:path";

import { runGit } from "~/git/git";

export class PathEscapesWorkspaceError extends Error {
  constructor(public readonly filePath: string) {
    super(`refusing to discard '${filePath}': path escapes the workspace`);
    this.name = "PathEscapesWorkspaceError";
  }
}

// Discards changes to a single file: `git checkout --` for tracked files,
// `git clean -f` for untracked ones (mirroring discard_workspace_file). The
// path is validated to stay inside the workspace working directory.
export async function discardFile(workingDir: string, filePath: string): Promise<void> {
  const resolved = path.resolve(workingDir, filePath);
  const normalizedRoot = path.resolve(workingDir);
  if (resolved !== normalizedRoot && !resolved.startsWith(normalizedRoot + path.sep)) {
    throw new PathEscapesWorkspaceError(filePath);
  }

  const tracked = await runGit(["ls-files", "--error-unmatch", "--", filePath], workingDir);
  if (tracked.exitCode === 0) {
    await runGit(["checkout", "--", filePath], workingDir);
  } else {
    await runGit(["clean", "-f", "--", filePath], workingDir);
  }
}
