# Command Palette — keeping in sync with the rest of the UI

The palette duplicates entry points that already exist elsewhere
(workspace right-click menu, settings sidebar, panel toggles, theme
switcher, etc.). To stop those copies from drifting we use a
**descriptor pattern**: each parallel surface consumes a single shared
list of descriptors instead of redefining its rows.

> Drift is a real risk, not theoretical: an earlier revision of MR !1021
> had the palette's "Close workspace" path skip the navigation step that
> the right-click menu did, so closing via Cmd+K removed the tab while
> leaving the workspace contents on screen. Reviewers caught this; the
> fix was to route both surfaces through one hook.

## When you add a new UI surface that the palette should mirror

Pick the lightest mechanism that fits:

### 1. Action descriptor list (right-click menus, palette sub-pages)

Use this when the same set of actions needs to render in both a
context menu and a palette sub-page. Examples already in the tree:

- `contextActions/workspaceActions.ts` — workspace tab right-click +
  `dynamic/workspaceActions.ts`
- `contextActions/agentActions.ts` — agent tab right-click +
  `dynamic/agentActions.ts`

Each descriptor declares the action's id, title, icon, optional
palette-specific overrides (`paletteSubtitle`, `paletteOrder`,
`paletteKeywords`, `paletteShortcut`), and a `perform` callback.
`<WorkspaceContextMenuContent />` projects the list to Radix menu
items; the dynamic provider projects it to `Command` rows. Adding an
entry shows up in both surfaces automatically.

### 2. Shared registry for catalog-style data (settings sections, panels)

Use this when the palette's source data already lives in a registry
that the rest of the UI consumes. Examples:

- `~/pages/settings/sections.ts` exports `SETTINGS_SECTIONS`. The
  Settings page sidebar AND `builtinCommands/settings.ts` read from it,
  so reordering / renaming a section happens in one place.
- `~/components/panels/atoms.ts`'s `panelRegistryAtom` is the source of
  truth for IDE panels. `dynamic/panels.ts` reads it at produce time.

If you're adding a new catalog (e.g. "model presets"), follow the same
shape: define the list in a module owned by the feature, then have
both the in-feature UI and the palette dynamic provider import it.

### 3. Shared imperative handler (close, navigate, mutate)

Use this when there's no list — just a few imperative actions that
need to behave identically regardless of how the user invokes them.
Example:

- `~/components/useWorkspaceTabActions.ts` returns
  `handleClose` / `handleCloseOthers` / `handleCloseAll` plus
  `navigateToNextTab`. The tab bar's X button, the right-click menu,
  the close-tab keybinding, and the Cmd+K palette all consume this
  one hook.

The hook centralizes "close the tab AND navigate to the next one AND
handle pseudo-tabs (Home/Settings)" so neither caller has to reinvent
half of it.

### 4. Action registry for in-component callbacks (`useRegisterCommandAction`)

Use this when a per-component imperative action (e.g. "focus the chat
input") needs to be runnable from the palette. The component calls
`useRegisterCommandAction("chat.focus_input", callback)`; the palette
command body calls `runtime.action.run("chat.focus_input")`. Cleans up
on unmount.

## Anti-patterns to avoid

- **Duplicating a small list** ("just five sections, easy to keep in
  sync") — the next reviewer adds a section to one copy. Lift it.
- **Synthesizing keystrokes from the palette** to drive other UI. The
  action registry exists so we don't dispatch fake KeyboardEvents.
- **Branching palette behavior on `if (route.isWorkspace)` when the
  data already encodes that** — read it from the underlying registry
  (e.g. the panel registry only emits panels on workspace routes) and
  let the palette consume it generically.

## Drift guardrails

`__tests__/settingsSectionDrift.test.ts` walks the shared
`SETTINGS_SECTIONS` list and asserts every entry has a matching palette
command. If you remove a section from the palette without removing it
from the sidebar, this test fails in CI.

If you set up a new shared registry, add an analogous guardrail.
