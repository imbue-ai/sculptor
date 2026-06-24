import { runGit } from "~/git/git";

// Commit-history shapes, matching CommitInfo / CommitFileInfo in
// web/data_types.py (frontend contract, RW-API-3).

const MAX_COMMITS = 500;

export type CommitFileStatus = "M" | "A" | "D" | "R";

export interface CommitFileInfo {
  path: string;
  status: CommitFileStatus;
  old_path: string | null;
  additions: number;
  deletions: number;
}

export interface CommitInfo {
  hash: string;
  short_hash: string;
  message: string;
  author_name: string;
  timestamp: string;
  parent_hashes: string[];
  files: CommitFileInfo[];
}

export interface CommitHistory {
  commits: CommitInfo[];
  fork_point: string | null;
}

export interface ListCommitsParams {
  workingDir: string;
  sourceGitHash: string;
  targetBranch?: string | null;
}

async function getMergeBase(workingDir: string, targetBranch: string): Promise<string | null> {
  const result = await runGit(["merge-base", "HEAD", targetBranch], workingDir);
  if (result.exitCode !== 0 || result.stdout.trim() === "") {
    return null;
  }
  return result.stdout.trim();
}

// Expand git's compact rename notation in a numstat path to the new path,
// mirroring _expand_numstat_rename_path.
function expandNumstatRenamePath(path: string): string {
  const braceStart = path.indexOf("{");
  if (braceStart !== -1) {
    const braceEnd = path.indexOf("}", braceStart);
    const arrow = path.indexOf(" => ", braceStart);
    if (braceEnd !== -1 && arrow !== -1 && arrow < braceEnd) {
      const prefix = path.slice(0, braceStart);
      const newPart = path.slice(arrow + 4, braceEnd);
      const suffix = path.slice(braceEnd + 1);
      return (prefix + newPart + suffix).replace(/^\/+/, "");
    }
  }
  const arrow = path.indexOf(" => ");
  if (arrow !== -1) {
    return path.slice(arrow + 4);
  }
  return path;
}

function parseNumstatLines(lines: string[]): Map<string, [number, number]> {
  const result = new Map<string, [number, number]>();
  for (const line of lines) {
    const parts = line.split("\t");
    if (parts.length < 3) {
      continue;
    }
    const additions = parts[0] === "-" ? 0 : Number.parseInt(parts[0]!, 10);
    const deletions = parts[1] === "-" ? 0 : Number.parseInt(parts[1]!, 10);
    let path = parts.length === 4 ? parts[3]! : parts[2]!;
    if (path.includes("=>")) {
      path = expandNumstatRenamePath(path);
    }
    result.set(path, [additions, deletions]);
  }
  return result;
}

function parseNameStatusLines(lines: string[]): Map<string, [CommitFileStatus, string | null]> {
  const result = new Map<string, [CommitFileStatus, string | null]>();
  for (const line of lines) {
    const parts = line.split("\t");
    if (parts.length < 2) {
      continue;
    }
    const status = parts[0]!;
    if (status.startsWith("R")) {
      if (parts.length >= 3) {
        result.set(parts[2]!, ["R", parts[1]!]);
      }
    } else {
      const letter = (status[0] ?? "M") as CommitFileStatus;
      result.set(parts[1]!, [letter, null]);
    }
  }
  return result;
}

async function parseLogFileData<T>(
  workingDir: string,
  forkPoint: string,
  flag: string,
  parser: (lines: string[]) => Map<string, T>,
): Promise<Map<string, Map<string, T>>> {
  const result = new Map<string, Map<string, T>>();
  const out = await runGit(
    ["log", `-n${MAX_COMMITS}`, "--format=COMMIT_SEP:%H", flag, "-M", `${forkPoint}..HEAD`],
    workingDir,
  );
  if (out.exitCode !== 0 || out.stdout.trim() === "") {
    return result;
  }
  let currentHash: string | null = null;
  let currentLines: string[] = [];
  for (const line of out.stdout.split("\n")) {
    if (line.startsWith("COMMIT_SEP:")) {
      if (currentHash !== null) {
        result.set(currentHash, parser(currentLines));
      }
      currentHash = line.slice("COMMIT_SEP:".length);
      currentLines = [];
    } else if (line.trim() !== "") {
      currentLines.push(line);
    }
  }
  if (currentHash !== null) {
    result.set(currentHash, parser(currentLines));
  }
  return result;
}

// Commits from HEAD back to the fork point (merge-base with the target branch,
// or source_git_hash). Mirrors get_commit_history + _resolve_fork_point.
export async function listCommits(params: ListCommitsParams): Promise<CommitHistory> {
  const forkPoint =
    params.targetBranch !== undefined && params.targetBranch !== null
      ? ((await getMergeBase(params.workingDir, params.targetBranch)) ?? params.sourceGitHash)
      : params.sourceGitHash;

  const separator = "\x1f";
  const formatStr = `%H${separator}%h${separator}%s${separator}%aN${separator}%aE${separator}%aI${separator}%P`;
  const metaResult = await runGit(
    ["log", `-n${MAX_COMMITS}`, `--format=${formatStr}`, `${forkPoint}..HEAD`],
    params.workingDir,
  );
  if (metaResult.exitCode !== 0 || metaResult.stdout.trim() === "") {
    return { commits: [], fork_point: forkPoint };
  }

  const numstatByHash = await parseLogFileData(params.workingDir, forkPoint, "--numstat", parseNumstatLines);
  const statusByHash = await parseLogFileData(params.workingDir, forkPoint, "--name-status", parseNameStatusLines);

  const commits: CommitInfo[] = [];
  for (const line of metaResult.stdout.trim().split("\n")) {
    const parts = line.split(separator);
    if (parts.length !== 7) {
      continue;
    }
    const hash = parts[0]!;
    const numstat = numstatByHash.get(hash) ?? new Map<string, [number, number]>();
    const statuses = statusByHash.get(hash) ?? new Map<string, [CommitFileStatus, string | null]>();
    const allPaths = [...new Set([...numstat.keys(), ...statuses.keys()])].sort();
    const files: CommitFileInfo[] = allPaths.map((path) => {
      const [additions, deletions] = numstat.get(path) ?? [0, 0];
      const [status, oldPath] = statuses.get(path) ?? (["M", null] as [CommitFileStatus, string | null]);
      return { path, status, old_path: oldPath, additions, deletions };
    });
    commits.push({
      hash,
      short_hash: parts[1]!,
      message: parts[2]!,
      author_name: parts[3]!,
      timestamp: parts[5]!,
      parent_hashes: parts[6] !== "" ? parts[6]!.split(" ") : [],
      files,
    });
  }

  return { commits, fork_point: forkPoint };
}

export class FileNotFoundAtRefError extends Error {
  constructor(
    public readonly ref: string,
    public readonly filePath: string,
  ) {
    super(`file '${filePath}' not found at ref '${ref}'`);
    this.name = "FileNotFoundAtRefError";
  }
}

// File contents at a specific ref via `git show <ref>:<path>`.
export async function readFileAtRef(workingDir: string, ref: string, filePath: string): Promise<string> {
  const result = await runGit(["show", `${ref}:${filePath}`], workingDir);
  if (result.exitCode !== 0) {
    throw new FileNotFoundAtRefError(ref, filePath);
  }
  return result.stdout;
}
