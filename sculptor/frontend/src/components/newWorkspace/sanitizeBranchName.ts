/**
 * Strip the characters and forms git rejects in branch names as the user types,
 * so the pill mostly shows a name the create call can accept. Mirrors git's ref
 * rules for the cases that are safe to strip mid-word: whitespace collapses to a
 * hyphen; the reserved ref characters are dropped; runs of dots and of slashes
 * collapse (git forbids ".." and "//"); a leading dot, slash, or dash is removed,
 * as is a dot that starts a path component (git forbids a component beginning
 * with ".").
 *
 * Trailing-position violations — a trailing "." or "/", or a ".lock" suffix — are
 * deliberately left alone: stripping them on every keystroke would eat the
 * separator the user is partway through typing (e.g. "feature/" or "release-1.").
 * The create call rejects those instead.
 */
export const sanitizeBranchName = (raw: string): string =>
  raw
    .replace(/\s+/g, "-")
    .replace(/[~^:?*[\]\\@{}]/g, "")
    .replace(/\.{2,}/g, ".")
    .replace(/\/\.+/g, "/")
    .replace(/\/{2,}/g, "/")
    .replace(/^[./-]+/, "");
