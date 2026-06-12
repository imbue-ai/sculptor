import type { MouseEvent as ReactMouseEvent } from "react";

// Anchor-handling primitives shared by `ReadOnlyPreview` and `MarkdownDiff`.
//
// Sculptor renders user-authored `.md` content inside an Electron
// BrowserWindow whose page already has its own routing (built on URL
// fragments) and an aggressive `will-navigate` / `setWindowOpenHandler`
// (`src/electron/main.ts`) that forwards external URLs to `shell.openExternal`.
//
// The combination means a *bare* `<a href="…">` click in markdown is
// dangerous in three different ways:
//
//   1. `<a href="https://…">` → in-window navigation away from the React
//      app shell (would also be `shell.openExternal`-routed by
//      `will-navigate`, but only AFTER the React app starts unloading).
//      Fix: `target="_blank"` makes the click route through
//      `setWindowOpenHandler` cleanly, before the React shell sees it.
//
//   2. `<a href="#section">` → updates `location.hash`, which Sculptor's
//      own router consumes — the user gets ejected from the current view
//      with no obvious way back. Fix: `preventDefault()` on click and do an
//      in-place `scrollIntoView` instead.
//
//   3. `<a href="./neighbor.md">` (or `/path` etc.) → resolves against the
//      app URL and either gets shipped to `shell.openExternal` (which then
//      tries to open `http://localhost:…/neighbor.md` in the OS browser,
//      404'ing or showing the dev server's index page) or hijacks the
//      app's own router. Fix: `preventDefault()` on click; we don't have a
//      file-link navigation story yet.

// Match RFC 3986 scheme followed by `:`. Anything that matches is treated
// as an external URL — `safeUrlTransform` upstream has already filtered out
// the dangerous schemes, so by the time we see one here it's known-safe.
const SCHEME_RE = /^[a-z][a-z0-9+.-]*:/i;

export const hasExternalProtocol = (href: string): boolean => SCHEME_RE.test(href);

// Wrapper marker: set `data-markdown-body` on the outer container of both
// `ReadOnlyPreview` and `MarkdownDiff` so the fragment-scroll lookup can
// scope its `[id="…"]` query to the right region — the same id might
// exist elsewhere in the app shell (e.g. an `id="install"` somewhere in
// settings would otherwise be a valid scroll target for a TOC click).
const MARKDOWN_BODY_SELECTOR = "[data-markdown-body]";

// `onClick` handler applied to every anchor whose href has no protocol —
// fragment-only links *and* relative paths. Both shapes get
// `preventDefault()` so the click cannot reach Sculptor's router or the
// Electron navigation handlers. Fragment links additionally try to scroll
// to a matching `[id="…"]` inside the same markdown body. Today no plugin
// adds id attributes to headings (tracked in SCU-767), so the scroll is a
// no-op; the contract is wired up so it lights up the moment ids exist.
export const handleInternalMarkdownAnchorClick = (event: ReactMouseEvent<HTMLAnchorElement>): void => {
  event.preventDefault();
  const href = event.currentTarget.getAttribute("href") ?? "";
  if (!href.startsWith("#")) return;
  const id = href.slice(1);
  if (id === "") return;
  const body = event.currentTarget.closest(MARKDOWN_BODY_SELECTOR);
  const dest = body?.querySelector(`[id="${CSS.escape(id)}"]`);
  if (dest instanceof HTMLElement) {
    dest.scrollIntoView({ behavior: "smooth", block: "start" });
  }
};
