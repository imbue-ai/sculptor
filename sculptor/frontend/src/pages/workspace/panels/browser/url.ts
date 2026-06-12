const URL_SCHEME_RE = /^[a-zA-Z][a-zA-Z0-9+\-.]*:\/\//;
const ABSOLUTE_UNIX_PATH_RE = /^\//;
// Windows drive letter (e.g. ``C:\path`` or ``C:/path``).
const ABSOLUTE_WINDOWS_PATH_RE = /^[a-zA-Z]:[\\/]/;
const WHITESPACE_RE = /\s/;

export type NormalizedUrl = { kind: "ok"; url: string } | { kind: "empty" } | { kind: "invalid"; reason: string };

const invalid = (raw: string): NormalizedUrl => ({
  kind: "invalid",
  reason: `"${raw}" is not a valid URL.`,
});

export const normalizeUrlInput = (raw: string): NormalizedUrl => {
  const trimmed = raw.trim();
  if (trimmed === "") return { kind: "empty" };

  let candidate: string;
  if (ABSOLUTE_UNIX_PATH_RE.test(trimmed)) {
    // Absolute file paths can legitimately contain spaces, so we leave
    // whitespace alone for this branch and let ``new URL`` handle it.
    candidate = `file://${trimmed}`;
  } else if (ABSOLUTE_WINDOWS_PATH_RE.test(trimmed)) {
    candidate = `file:///${trimmed.replace(/\\/g, "/")}`;
  } else {
    // Bare host or schemed URL: reject anything that obviously isn't a
    // URL. The renderer's URL parser is more lenient than Node's and
    // will accept strings like ``http://not a url`` by
    // interpreting the space as a path boundary, so we check the input
    // shape ourselves before delegating to ``new URL`` for the final
    // structural check.
    if (WHITESPACE_RE.test(trimmed)) return invalid(trimmed);
    candidate = URL_SCHEME_RE.test(trimmed) ? trimmed : `http://${trimmed}`;
  }

  try {
    new URL(candidate);
  } catch {
    return invalid(trimmed);
  }
  return { kind: "ok", url: candidate };
};
