/**
 * Naming for outbound-link browser tabs so that re-opening the *same* URL reuses
 * its existing tab instead of piling up a fresh one on every click, while
 * distinct URLs still get their own tabs. Every caller that opens a given URL
 * must route through this so they all agree on one tab.
 *
 * This only takes effect in the **web build**, where the browser honours the
 * window name and navigates (and, in most browsers, focuses) the matching tab.
 * In the Electron desktop app every outbound link is routed through the main
 * process to `shell.openExternal`, which drops the name and hands the OS only
 * the URL, so a named target is a harmless no-op there.
 *
 * Tab reuse is mutually exclusive with `noopener` / `noreferrer`: the HTML spec
 * treats either as forcing a fresh (`_blank`) context, so we deliberately open
 * without them. The opened tab therefore keeps a `window.opener` back-reference,
 * so only ever point this at trusted hosts (the user's own git provider).
 */

// Namespaced so a Sculptor tab can never collide with an unrelated window a site
// happened to name after the same URL. The full URL keeps the name unique per
// PR/pipeline (two repos with the same PR number don't share a tab).
const TAB_TARGET_PREFIX = "sculptor:";

export const reusableTabTarget = (url: string): string => `${TAB_TARGET_PREFIX}${url}`;

export const openInReusableTab = (url: string): void => {
  window.open(url, reusableTabTarget(url));
};
