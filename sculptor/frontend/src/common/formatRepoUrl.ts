/**
 * Trims a git repository URL down to the most disambiguating fragment for
 * display next to a project's name. Used by the entity mention picker so
 * the user sees `imbue-ai/sculptor` rather than the full
 * `https://github.com/imbue-ai/sculptor.git`.
 *
 *  - HTTP(S): `https://host/org/repo[.git]` → `org/repo`
 *  - SSH:     `git@host:org/repo[.git]`     → `org/repo`
 *  - SSH://:  `ssh://git@host/org/repo[.git]` → `org/repo`
 *  - file://: `file:///abs/path/to/repo`    → `parent/leaf` (last 2 segments)
 *  - bare path: same `parent/leaf` treatment
 *  - missing/empty/unrecognised: returns the original input as-is so
 *    nothing useful gets hidden.
 */
export const formatRepoUrl = (url: string | null | undefined): string => {
  if (url === null || url === undefined || url === "") return "";

  const sshMatch = url.match(/^git@[^:]+:(.+)$/);
  if (sshMatch !== null) {
    return stripGitSuffix(sshMatch[1]);
  }

  if (url.startsWith("file://")) {
    const path = url.slice("file://".length);
    return lastTwoSegments(path);
  }

  if (url.startsWith("http://") || url.startsWith("https://") || url.startsWith("ssh://")) {
    try {
      const parsed = new URL(url);
      const path = parsed.pathname.replace(/^\/+/, "");
      return stripGitSuffix(path);
    } catch {
      return url;
    }
  }

  if (url.startsWith("/") || url.startsWith("~")) {
    return lastTwoSegments(url);
  }

  return url;
};

const stripGitSuffix = (value: string): string => (value.endsWith(".git") ? value.slice(0, -4) : value);

const lastTwoSegments = (path: string): string => {
  const segments = path.replace(/\/+$/, "").split("/").filter(Boolean);
  if (segments.length === 0) return path;
  if (segments.length === 1) return segments[0];
  return `${segments[segments.length - 2]}/${segments[segments.length - 1]}`;
};
