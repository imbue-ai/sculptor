# Sculptor mock templates

A starter kit for HTML mocks that look like the real Sculptor app, used by
`/sculptor-workflow:mock` (pointed here from the UI Reference in
`.sculptor/docs.md`).

## Files

- **`sculptor-shell.html`** — self-contained starter: exact Radix dark
  tokens, the app's real fonts (loaded from `sculptor/frontend/node_modules`
  via relative paths), an app-shell backdrop (sidebar / topbar / panels /
  composer), and mock recreations of the app's dialog language —
  PaletteDialog shell, Cmd+K list rows, a Raycast-style bottom bar with an
  actions popover, a Radix AlertDialog, buttons and switches. States are
  routed with `?state=<name>`; `?bare=1` hides the state-switcher chrome.
- **`shoot.mjs`** — renders states to PNGs at the app's viewport
  (1440x900 @2x). `node .sculptor/mock_templates/shoot.mjs <mocks.html>
  <out-dir> <state> [state...]`.

## How to use

1. Copy `sculptor-shell.html` to the mock location (normally
   `agent_docs/<slug>/mocks.html`). Both files assume they live exactly two
   directories below the repo root — the font and playwright imports are
   relative (`../../sculptor/frontend/node_modules/...`).
2. Replace the example dialog states with the feature's states; reuse the
   component classes rather than inventing new visual language. Add a
   `body[data-state=...]` routing rule and a chrome link per state.
3. Render screenshots with `shoot.mjs` and post them inline in chat as
   `<img src="/absolute/path.png">` tags.
4. **Never overwrite a PNG already posted to chat** — earlier messages
   reference the file on disk, so overwriting rewrites history. Bump a
   version suffix in the output names each iteration round instead.

## Where the values came from (for extending the kit)

- Color/spacing/typography tokens: `@radix-ui/themes/tokens/base.css` and
  `tokens/colors/{gray,indigo,tomato}.css` (dark scales), matching the app's
  default theme (gray accent, gray gray-scale, dark, medium radius, 100%
  scaling). Custom tokens (shadows, z-index, durations) from
  `sculptor/frontend/src/styles/tokens.css`.
- Dialog shells: `src/components/PaletteDialog/PaletteDialog.module.scss`
  and `src/components/CommandPalette/CommandPalette.module.scss` — sizes,
  paddings, and colors are copied 1:1, so keep those in sync if the real
  components change.
- Icons: inline SVGs with lucide path data (stroke 2, round caps), 16px in
  rows, 13-14px in bars/menus.
- Verified against live captures from the `/auto-qa-changes` harness; if the
  app's theme defaults change, recapture and re-tune.
