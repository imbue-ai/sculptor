# Mobile New Workspace — Mock Context

## Description

Redesign of the mobile new-workspace landing (`MobileNewWorkspace`). The
current screen vertically centers a hero, a name input, a tiny
`repo · origin/main` meta line, and an oversized full-width Create button —
leaving the screen feeling empty and "jammed in the middle," with a
background that doesn't match the rest of the mobile app.

This is a **confirmation mock** verifying the design we aligned on in chat
(there is no separate spec file — the conversation is the source of truth).

Goals, from user feedback:
- Hero copy "Name your workspace" → **"Create a workspace"**.
- Repo + branch are too small and unlabeled → give them clear labels.
- Surface the **generated branch name** (already computed by the parent as
  `effectiveBranchName`, just not passed to the mobile component) alongside
  the source branch it forks from.
- The Create button is too large → right-size it, and **pin it to the bottom**.
- Better use of vertical space → keep content **vertically centered** (NOT
  top-anchored) but with stronger spacing and grouping.
- **Background** should match the workspace page: base `--gray-2`
  (`--mobile-surface-2`), with contrasting surfaces for the input/card —
  today the page uses `--color-background` (near-black), which reads as a
  different, flatter color than the rest of the app.

## Decisions
- **Background:** page base = `--gray-2` (`--mobile-surface-2`) to match the
  workspace page; controls/cards lifted to `--gray-3`. (Was `--color-background`.)
- **Create button** pinned to the bottom safe area, right-sized (~48px), and
  uses the accent/blue color from the desktop modal (not the old gray solid).
- **No "Name" heading** — the workspace name is an inline "Untitled workspace"
  title (placeholder → filled), mirroring the desktop modal.
- **Options are Repo · Branch · Source** (in that order): Repo selector,
  Branch = the generated/target branch (with a ⇄ regenerate action), Source =
  the source branch, now its own selectable row defaulting to `origin/main`.
- Align the mobile screen to the new desktop create-workspace modal's language.
- **Options shown as stacked pills** (Option A) — full-width Repo/Branch/Source
  pills, keeping the modal's "tap to change" dropdown feel. (Option B, the
  labeled card, was not chosen.)
- **Name title first, pills below** — on mobile, the workspace title sits above
  the option pills (the reverse of the desktop modal, where the pill toolbar is
  on top). Title + pills are one vertically-centered group.
- **No first-prompt field** on mobile — name only (the current create flow
  sends no prompt).
- **No "Keep open" toggle** on mobile — creating navigates straight into the
  new workspace.

## Rejected Alternatives
- **Top-anchored layout** — rejected by user (wanted content centered, button
  pinned bottom).
- **Centered minimal v1** (hero "Create a workspace" + "Name" label + 2-row
  details card, gray button) — superseded after the user shared the desktop
  modal: dropped the Name heading, switched to Repo/Branch/Source + inline
  title + accent button to match the modal.
- **Option B — labeled card** for the three options — not chosen; user preferred
  the stacked pills (Option A). Kept in mocks.html for the record.
- **First-prompt field** and **"Keep open" toggle** — present in the desktop
  modal, deliberately left off mobile.

## Tweaks Log
- Requested: drop the "Name" heading; sections should be Repo, Branch, Source;
  align to the shared desktop create-workspace modal (Repo/Source/Branch
  dropdowns, "Untitled workspace" inline title, accent Create button), noting
  the three dropdowns won't fit in a row on mobile.
  Changed: reworked the redesign into two adaptations — A (stacked dropdown
  pills) and B (labeled Repo/Branch/Source card). Removed the "Name" label in
  favor of an inline "Untitled workspace" title; added a ⇄ regenerate affordance
  on Branch and made Source a selectable row; switched Create to the modal's
  accent/blue. Kept the "Before" column for comparison.
- Requested: use Option A (stacked pills); no first-prompt field; drop the
  "Keep open" toggle; swap the order so the workspace title is above the pills.
  Changed: made Option A the final layout — name title on top, three stacked
  pills (Repo/Branch/Source) below, as one vertically-centered group, accent
  Create pinned to the bottom. Removed the prompt field and Keep-open toggle.
  Demoted Option B (labeled card) to a dimmed "not chosen" record column.
