# Task 2.1: Copy the shared design foundation (tokens, scrollbar mixin, overrides)

## Goal

Bring the shared styling foundation the rest of the rewrite depends on — design
tokens, the thin-scrollbar mixin, and Radix overrides — from the `scu-1474`
prototype into the live frontend, merging additively with what's already on
`main`. Everything else in `design_extraction.md` builds on these tokens, so they
come first.

## Stories addressed

None directly — this is the styling foundation for all `SEC-*`/`SIDE-*`/`PANEL-*`
visuals.

## Background

**Project:** Sculptor frontend (TS + React + Vite) under `sculptor/frontend/src`.
We are rewriting the workspace shell into the section/panel model from
`agent_docs/ui_refresh/goals.md`, copying **styling and shape** (not behavior) from
the throwaway branch `bryden/scu-1474-compact-workspace-layout`.

**What to copy** (`agent_docs/ui_refresh/design_extraction.md` → "Shared foundation
(copy first)"):
- `styles/tokens.css` — durations (`--duration-*`), z-index (`--z-*`), shadows
  (`--shadow-*`), scrollbar tokens.
- `index.css` additions — app zoom/height, Inter font, `.icon-xs…xl` sizing,
  `body.sculptor-resizing webview { pointer-events: none }`, search highlight.
- `styles/radix-overrides.css`.
- `styles/_scrollbar.scss` — the `@include thin-scrollbar` mixin used by every
  scroll area.
- Radix Themes scales (`@radix-ui/themes`: `--gray-*`, `--accent-*`, `--space-*`,
  `--radius-*`, `--font-size-*`, `--font-weight-*`) are already available via the
  Radix Themes provider; just rely on them.

The current frontend already has `src/styles/` and `src/index.css`. Some tokens may
already exist on `main`; this task **merges additively** — add the tokens/mixins
the rewrite needs without clobbering existing ones.

## Files to modify/create

- `sculptor/frontend/src/styles/tokens.css` — create or extend with the prototype's
  `--duration-*`/`--z-*`/`--shadow-*`/scrollbar tokens.
- `sculptor/frontend/src/styles/_scrollbar.scss` — add the `thin-scrollbar` mixin.
- `sculptor/frontend/src/styles/radix-overrides.css` — add the overrides.
- `sculptor/frontend/src/index.css` — merge the additions (zoom/height, icon
  sizing, `sculptor-resizing` rule, search highlight) if not already present.
- Ensure the token/override files are imported where global styles load (check
  `src/Main.tsx` / `src/App.tsx` / existing `index.css` imports).

## Implementation details

1. Inspect the prototype files to copy from:
   `git show bryden/scu-1474-compact-workspace-layout:sculptor/frontend/src/styles/tokens.css`
   (and the same for `_scrollbar.scss`, `styles/radix-overrides.css`, `index.css`).
2. Diff each against the current `main` version and **add only the missing
   tokens/rules**. Do not duplicate variables that already exist; do not remove
   existing ones.
3. Per `design_extraction.md` → "Do not copy": **do not** bring over the one-off
   hacks — hardcoded 11px font sizes, `margin: 0 !important` Radix ghost overrides,
   or `field-sizing: content` (Chromium-only). Keep the `getTitleBarLeftPadding()`
   helper approach (copied with the sidebar in Task 2.2), not inlined padding
   constants.
4. Confirm the global stylesheets are imported once at app entry so tokens resolve
   everywhere.

## Testing suggestions

- This is styling only — verify visually, not with automated tests
  (`.sculptor/testing.md`: purely visual states use screenshots, not
  layout-asserting tests).
- After Task 2.2+ render the sidebar/sections, confirm tokens resolve (no missing
  `var(--…)`), e.g. via `/storybook-screenshot` or `/auto-qa-changes` once there is
  something to view.

## Gotchas

- Additive merge — don't clobber existing tokens or you'll regress unrelated UI.
- Don't copy the prototype's "do not copy" hacks.
- Token files must be imported globally or `var(--…)` references silently fall back.

## Verification checklist

- [ ] `--duration-*`, `--z-*`, `--shadow-*`, and scrollbar tokens are available.
- [ ] `thin-scrollbar` mixin exists and is importable from `styles/_scrollbar.scss`.
- [ ] `radix-overrides.css` + `index.css` additions merged without removing
  existing rules.
- [ ] No "do not copy" hacks were brought over.
- [ ] `just check` passes (lint/format on the new style files).
