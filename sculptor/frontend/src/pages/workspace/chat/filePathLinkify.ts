/** Extensions (without leading dot) recognized as file paths. */
const KNOWN_EXTENSIONS = new Set([
  "py",
  "ts",
  "tsx",
  "js",
  "jsx",
  "json",
  "yaml",
  "yml",
  "toml",
  "md",
  "html",
  "css",
  "scss",
  "sh",
  "sql",
  "rs",
  "go",
  "rb",
  "java",
  "kt",
  "c",
  "cpp",
  "h",
  "hpp",
  "swift",
  "txt",
  "cfg",
  "ini",
  "env",
  "lock",
  "xml",
]);

// Build extension alternation sorted by length descending so longer extensions
// are matched before shorter ones (e.g. .tsx before .ts, .scss before .css).
const EXT_ALTERNATION = [...KNOWN_EXTENSIONS].sort((a, b) => b.length - a.length).join("|");

// Core path pattern (without anchors) — used by both the global and anchored regexes.
// Requires at least one `/` separator, ends with a known extension,
// optionally followed by `:digits` line number.
const PATH_PATTERN = `/?[\\w.~-]+(?:/[\\w.~-]+)+\\.(?:${EXT_ALTERNATION})(?::\\d+)?`;

/**
 * Global regex for finding file paths within larger text.
 *
 * Boundaries: preceded by start, whitespace, or opening delimiter;
 * followed by end, whitespace, or closing punctuation.
 */
const FILE_PATH_REGEX = new RegExp(`(?:^|(?<=[\\s(\\[,]))` + `(${PATH_PATTERN})` + `(?=$|[\\s)\\],.;:!?])`, "g");

/** Anchored regex for testing if an entire string is a file path. */
const FILE_PATH_ANCHORED = new RegExp(`^${PATH_PATTERN}$`);

export type Segment =
  | { readonly kind: "text"; readonly value: string }
  | { readonly kind: "path"; readonly value: string; readonly navPath: string };

/** Strip a trailing `:<digits>` line-number suffix from a path. */
export const stripLineNumber = (path: string): string => path.replace(/:\d+$/, "");

/**
 * Resolve a raw file path to a navigation path suitable for the diff viewer.
 *
 * Strips the line-number suffix and removes a leading workspace code path
 * prefix from absolute paths.
 */
export const resolveNavPath = (rawPath: string, workspaceCodePath: string | null): string => {
  const stripped = stripLineNumber(rawPath);
  if (!workspaceCodePath) return stripped;
  const prefix = workspaceCodePath.endsWith("/") ? workspaceCodePath : `${workspaceCodePath}/`;
  if (stripped.startsWith(prefix)) return stripped.slice(prefix.length);
  if (stripped === workspaceCodePath) return "";
  return stripped;
};

/**
 * Check whether a raw path resolves to something inside the workspace.
 *
 * Relative paths (no leading `/`) are assumed to be workspace-relative and
 * are accepted. Absolute paths must start with the workspace code path prefix;
 * otherwise they point outside the repo and should not be linkified.
 */
export const isPathInWorkspace = (rawPath: string, workspaceCodePath: string | null): boolean => {
  const stripped = stripLineNumber(rawPath);
  // Relative paths are assumed workspace-relative.
  if (!stripped.startsWith("/")) return true;
  // Absolute paths require a known workspace root for validation.
  if (!workspaceCodePath) return false;
  const prefix = workspaceCodePath.endsWith("/") ? workspaceCodePath : `${workspaceCodePath}/`;
  return stripped.startsWith(prefix) || stripped === workspaceCodePath;
};

/**
 * Test whether an entire string looks like a file path.
 *
 * Used for inline code spans where the full content of the `<code>` element
 * is checked as a single string.
 */
export const isFilePath = (text: string): boolean => {
  const trimmed = text.trim();
  if (!trimmed) return false;
  // Reject URL-like strings
  if (/^https?:\/\//.test(trimmed) || /^ftp:\/\//.test(trimmed)) return false;
  return FILE_PATH_ANCHORED.test(trimmed);
};

/**
 * Split a string into alternating text and path segments.
 *
 * Each path segment includes the display text (`value`, as it appeared in the
 * source including any line-number suffix) and a `navPath` with the line number
 * stripped and workspace prefix removed.
 */
export const splitFilePathSegments = (text: string, workspaceCodePath: string | null): ReadonlyArray<Segment> => {
  if (!text) return [{ kind: "text", value: text }];

  const segments: Array<Segment> = [];
  // Use a fresh regex via matchAll to avoid global-flag statefulness issues.
  const matches = text.matchAll(new RegExp(FILE_PATH_REGEX.source, "g"));
  let lastIndex = 0;

  for (const match of matches) {
    const matchStart = match.index;
    const matchedPath = match[1];

    // Skip URL-like matches
    if (/^https?:\/\//.test(matchedPath) || /^ftp:\/\//.test(matchedPath)) continue;

    // Also skip if the match is preceded by `://` (e.g. embedded in a URL)
    if (matchStart >= 3 && text.slice(matchStart - 3, matchStart).includes("://")) continue;

    // Skip paths that resolve outside the workspace (e.g. /etc/config.yaml)
    if (!isPathInWorkspace(matchedPath, workspaceCodePath)) continue;

    if (matchStart > lastIndex) {
      segments.push({ kind: "text", value: text.slice(lastIndex, matchStart) });
    }

    segments.push({
      kind: "path",
      value: matchedPath,
      navPath: resolveNavPath(matchedPath, workspaceCodePath),
    });

    lastIndex = matchStart + matchedPath.length;
  }

  if (lastIndex < text.length) {
    segments.push({ kind: "text", value: text.slice(lastIndex) });
  }

  if (segments.length === 0) {
    return [{ kind: "text", value: text }];
  }

  return segments;
};
