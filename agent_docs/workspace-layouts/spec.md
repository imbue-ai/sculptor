# Workspace Layouts

## Overview

Sculptor's workspace UI is built from panel sections (left, bottom,
right, etc.) that hold panels such as files, changes, commits, the
terminal, and the browser. Today, the arrangement of these panels —
which are open, where they sit, and their sizes — is essentially fixed
or remembered ad hoc per workspace.

This feature introduces **named layouts**: reusable, savable
arrangements of panels that a user can switch between, save, remove,
and set as a default for new workspaces. All of this behaviour should
be reachable from the cmd+k command palette.

Sculptor ships with a set of built-in default layouts:

- **Sculptor Default** — files, changes, and commits in the left
  section; the terminal in the bottom section (hidden by default); the
  browser in the right section (hidden by default).
- **Review** — same as Sculptor Default, except the changes panel is
  open by default.
- **QA** — the browser is open on the right; the left section and
  bottom section are closed.

A layout captures *everything* about the arrangement: which panels are
open, their section placement, and their percentage sizes.

The user wants to be able to:

- **Switch** between layouts ("Switch layout" command).
- **Save** the current arrangement as a (new or existing) layout.
- **Remove** a saved layout.
- **Set a default** layout that new workspaces start with (likely
  configured in settings).

_(This Overview is a rough first pass — we'll sharpen it through Q&A.)_

## User Scenarios

(TBD — clarifying in Q&A)

## Requirements

(TBD — clarifying in Q&A)

## Non-Goals

(TBD — clarifying in Q&A)

## Open Questions

(TBD — clarifying in Q&A)
