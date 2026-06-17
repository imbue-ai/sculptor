# Compact Workspace Layout — Notes for Early Testers

Thanks for taking this for a spin! This branch is a fairly large redesign of the
Sculptor workspace page around a uniform **panel/section** model. The goal is a
*compact, clean* workspace: less chrome, fewer always-visible icons, and a layout
where every piece of content — chat, terminal, files, diffs — is a panel you can
place, move, split, and resize however you like.

I'm sharing it early because I want real reactions before it hardens. Please poke
at it, break it, and tell me what you think.

Branch: `bryden/scu-1474-compact-workspace-layout`

---

## Read this first (setting expectations)

- **It's a work in progress.** This is a functional spike, not a finished
  feature. The old layout (`DockingLayout`) is replaced outright by the new
  `CompactLayout` — there's no toggle back, and that's intentional for now.
- **Some things were dropped on purpose; others just didn't make this cut.**
  A few examples of deliberate drops: the PR/MR button no longer has a dropdown,
  and the dedicated chat split-view was removed (you now get side-by-side chats
  by opening two agent panels instead). Several secondary icons were removed from
  the file browser and diff viewer — those are tracked in
  [`removed-icons.md`](./removed-icons.md) and the plan is to relocate them into
  overflow menus later, not to lose them.
- **The sidebar is deliberately the simplest version.** I started with a
  bare-bones vertical nav so the structure is in place; I'm hoping to collaborate
  with Gabe on the visual + interaction polish. Don't read the current styling as
  final.
- **Several hotkeys are still missing or incomplete.** Pane navigation exists
  (see below) but the full keyboard story isn't done. If a shortcut you expect
  isn't there yet, that's known.
- **There will be bugs.** Especially around the newer mechanics: splitting
  sections, dragging tabs between sections, and switching workspaces. If
  something looks wrong, it might be — please flag it.
- **Closing an agent or terminal tab now ends it.** The close (X) deletes the
  agent (or kills the terminal) after a confirmation — there's no "reopen
  existing" pool anymore. Every tab has a close button, including a workspace's
  only agent; deleting the last agent spins up a fresh one so the workspace
  always has a chat.

---

## Running it from source

Early testers will check out this branch and run it locally. Here's the short
version. (Full details live in
[`docs/development/getting_started.md`](../../docs/development/getting_started.md).)

### 1. Prerequisites (macOS, via Homebrew)

```bash
brew install tmux just uv watchman
# also install nvm: https://github.com/nvm-sh/nvm
```

### 2. Get the branch

If you don't have the repo yet:

```bash
git clone git@github.com:imbue-ai/sculptor.git
cd sculptor
git checkout bryden/scu-1474-compact-workspace-layout
```

If you already have a checkout:

```bash
git fetch origin
git checkout bryden/scu-1474-compact-workspace-layout
```

### 3. Build

```bash
just clean rebuild
```

### 4. Run

```bash
just start          # frontend + backend together in a tmux session
```

Or run them in separate terminals:

```bash
just backend
just frontend
```

### 5. When you pull updates to the branch

```bash
just rebuild
```

### 6. If your layout gets into a weird state

Layout state (which panels are open, where, and their sizes) is persisted **per
workspace in localStorage**, so it survives restarts. If you manage to wedge a
layout and want a clean slate, clear the app's local storage (Electron DevTools →
Application → Local Storage). To reset Sculptor's data/database entirely, back up
the dev data folder:

```bash
mv .dev_sculptor .dev_sculptor.bkp
```

---

## What's new — the things worth poking at

### 1. The sidebar (navigation)

The horizontal workspace tab bar is gone. In its place is a **vertical nav
sidebar** on the left:

- Top: Home / Search / New Workspace as a vertical list.
- Middle: your repos as collapsible headers, with each repo's workspaces grouped
  beneath it.
- Bottom: Settings and Help, anchored down.
- Hover a repo or workspace row to reveal its actions (new workspace, settings,
  the three-dot menu, delete). Right-click also works.
- Hovering a workspace **prefetches** its data so opening it feels instant, and
  a **peek overlay** pops up beside the row.
- You can collapse the whole sidebar from the toggle near the window controls.

Again — this is the *simplest* iteration on purpose. I'm most interested in
whether the structure makes sense, not whether it's pretty yet.

### 2. Panel changes (the heart of the redesign)

Everything is now a panel living in one of four sections — **Left, Center, Right,
Bottom** — and they all behave the same way:

- **Add panels** with the **"+"** on any section. It opens a Cmd+K-style picker:
  a fast "New agent" row, a "Choose agent type…" option, "New terminal", and the
  Files/Changes/Commits panels.
- **Agents and terminals are just panels.** Open two agents side by side by
  putting one in Center and one in Right. Terminals are no longer pinned to the
  bottom — drop one anywhere.
- **Split a section** (horizontal or vertical) from a tab's right-click menu, and
  **drag tabs between sections** to rearrange. Empty sections collapse on their
  own.
- **Files / Changes / Commits are now three separate panels**, each using a
  **master-detail** layout: a file tree on the left, the selected file's diff on
  the right — all inside the panel, one file at a time.
- **Pane navigation** via the keyboard: `Ctrl+Alt+Arrow` to move focus between
  sections, `Ctrl+Tab` / `Ctrl+Shift+Tab` to cycle tabs in the focused pane.
  Each section can also be maximized.
- The top bar gained quick toggles for the Left section, Right section, and
  Terminal, plus a couple of new settings (share panel sizes across workspaces;
  put the tab strip at the top or bottom).

This is the area most likely to surprise you — please try the splitting and
drag-and-drop and tell me where it feels off.

### 3. Performance work

A chunk of this branch is about making the app feel faster, especially when
moving between workspaces:

- Workspace switching no longer "flashes" the previous layout — the new layout is
  restored before the first paint.
- Open workspaces are kept "warm" (their data stays cached and is prefetched in
  the background), so switching back is quick.
- Reduced unnecessary re-renders, killed a double-render of diffs, and made stale
  in-flight fetches abort when you switch tasks.

There's also some dev-only tooling behind this (a frame-by-frame capture tool and
a React render-count comparison harness) — not user-facing, but it's how the perf
changes were measured.

---

## The feedback I'm after

The big questions, in order of how much I care about them:

1. **What feels like a step forward** compared to the old Sculptor? What's better
   now?
2. **What feels like a step backward?** Is anything harder than it should be, or
   slower, or more confusing than before?
3. **What still feels missing?** What did you reach for and not find?

A few smaller prompts if you're not sure where to start:

- **Sidebar:** does the repo → workspace grouping make navigating easier or
  harder? Did you miss the old horizontal tabs?
- **Panels:** did you discover splitting / drag-and-drop on your own? Did the
  master-detail Files/Changes/Commits feel natural? Did you end up fighting the
  layout to get the arrangement you wanted?
- **Performance:** does switching between workspaces feel snappier? Any spots
  where it still stutters or flashes?
- Anything that felt **broken**, plus rough repro steps if you can.

Don't polish your notes — raw reactions and gut feelings are exactly what's
useful at this stage.
