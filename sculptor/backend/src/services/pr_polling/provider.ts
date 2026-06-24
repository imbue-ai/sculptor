// Detect the git host provider from an `origin` remote URL (REQ-INT-001).
// Handles the SSH scp-like form (git@host:owner/repo), ssh:// URLs, and
// https:// URLs. Anything that isn't recognizably GitHub or GitLab is null.

export type GitProvider = "github" | "gitlab";

function parseHost(originUrl: string): string | null {
  const trimmed = originUrl.trim();
  // scp-like: [user@]host:path  (no scheme)
  const scp = /^(?:[^@/]+@)?([^/:]+):(?!\/\/)/.exec(trimmed);
  if (scp !== null) {
    return scp[1]!.toLowerCase();
  }
  try {
    return new URL(trimmed).hostname.toLowerCase();
  } catch {
    return null;
  }
}

export function detectProvider(
  originUrl: string | null | undefined,
): GitProvider | null {
  if (originUrl === null || originUrl === undefined || originUrl === "") {
    return null;
  }
  const host = parseHost(originUrl);
  if (host === null) {
    return null;
  }
  if (
    host === "github.com" ||
    host.endsWith(".github.com") ||
    host.includes("github")
  ) {
    return "github";
  }
  if (
    host === "gitlab.com" ||
    host.endsWith(".gitlab.com") ||
    host.includes("gitlab")
  ) {
    return "gitlab";
  }
  return null;
}
