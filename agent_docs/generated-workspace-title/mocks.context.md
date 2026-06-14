# Generated Workspace Title — Mock Context

## Description
Rework the new-workspace modal so the *prompt* is the primary input and
the workspace title becomes a derived artifact, auto-generated from the
prompt (the way the branch name already is). Problems with today's
modal:

- The first input is the title, which steals focus and attention from
  the prompt — we want to drive users into describing their task.
- There's no obvious affordance for re-generating a title.
- First-time experience should feel natural, not like filling in a form.

Related fix folded in: the prompt input should support slash commands
and additional context (@-mentions / file references), like the main
agent chat input (TipTap-based).

Background from the brainstorm that preceded this session:
- The branch field already implements the target pattern:
  derived-until-touched, shuffle-to-regenerate, edit-makes-it-sticky.
- Backend `generate_title_from_prompt` exists (blocking `claude -p`,
  used post-create by the legacy v1 path with a don't-clobber-renames
  guard). A live in-modal preview would need a faster path (debounced
  Haiku call) or generation happens post-create.
- Blank workspace (no prompt) must keep working: falls back to
  "Untitled workspace" + whimsical branch name.

## Decisions
- **Direction: B (final form: sparkle-toggle title).** The title-first
  layout is kept (big heading at top), but the heading is no longer the
  first input: autofocus lands in the prompt, and the generated title
  fills into the heading automatically. No "Tab to edit" affordance —
  clicking into the heading and typing is how the user takes ownership;
  once owned, the title stops tracking the prompt. (The variant began
  as "ghost text"; the ghost/violet text treatments were dropped during
  iteration — see Rejected Alternatives.)
- **Heading placeholder is "✦ Auto-generated title"** (not "Untitled
  workspace") so the default behavior is explicit before any typing.
- **The prompt is the same rich input as agent chat** (TipTap): slash
  commands and @-mention context chips work in the modal. Shown as A's
  slash-menu state and B's @-mention chip state.
- **Generation timing:** fast in-modal generation, debounced on typing
  pause, never blocking submit — if it hasn't landed by ⌘↵, generation
  completes post-create (existing backend path; whimsical branch name
  covers the gap). Blank-prompt workspaces keep today's behavior
  ("Untitled workspace" + whimsical branch).
- Implies a fast in-modal generation path (debounced call on typing
  pause) so the ghost text feels live — post-create-only generation
  doesn't fit this variant.
- **Default state is explicit about auto-generation:** the heading
  placeholder is "✦ Auto-generated title" (dim sparkle + text), not
  "Untitled workspace" — the user's original placeholder idea.
- **Regenerate affordance:** a shuffle button sits next to the ghost
  title (matches the branch field's shuffle), so a bad suggestion can
  be re-rolled without editing.
- **Wording:** prompt placeholder is "Describe a task for your agent —
  or create a blank workspace…". No "generating title…" text — the
  animated icon carries that meaning.
- **The sparkle is an on/off toggle, hugging the title text.** It sits
  just to the right of the text (not at the line's far edge) in every
  state. On = auto mode; off = owned. Typing in the heading toggles it
  off automatically (icon dims to gray); clicking it back on
  regenerates from the prompt. One line, no badge, no text link.
- **Auto titles render in normal black.** The lit sparkle alone
  signals auto vs owned — no special text color.
- **Shimmer over the text, no skeleton.** While generating, the
  shimmer gradient sweeps the existing text in place (the placeholder
  on first generation, the previous title on re-generation) and the
  sparkle animates (pulse/spin). No skeleton bar, no "generating…"
  text.
- **Regenerate icon is a circular refresh** (rotate arrows), used for
  both the title and the branch field — replaces the shuffle icon. The
  button sits beside the sparkle while the title is auto and hides
  once the title is owned (toggle auto back on first).

## Rejected Alternatives
- **A · Prompt-first, derived title line** — demoting the title to a
  small row under the prompt; user preferred keeping the prominent
  heading with ghost text instead.
- **C · No title field** — removing the title from the modal entirely
  (post-create generation only); user wants the title visible before
  create.
- **D · Title as toolbar pill** — moving the title into the pill row
  next to the branch field; not chosen (pill row crowding, title too
  de-emphasized).
- **"Edited" badge + "Reset to auto-generate" text link** — too
  verbose, took two lines; replaced by the sparkle on/off toggle.
- **"Tab to edit" hint** — unnecessary; click-and-type is the
  ownership gesture.
- **Violet-tinted auto-title text** — too loud; normal black text with
  the sparkle as the only auto signal.
- **Skeleton bar + "generating title…" text** — replaced by shimmer
  over the existing text and an animated sparkle.
- **Shuffle icon for regenerate** — replaced by circular refresh
  arrows (title and branch field).

## Tweaks Log
- Requested: initial generation, exploration mode.
  Changed: created `mocks.html` with 4 tabbed variants, each end-to-end
  with labeled states:
  - A · Prompt-first, derived title line (prompt hero; title as a small
    derived row with sparkle/shuffle/edit, mirroring the branch-field
    pattern; hybrid in-modal generation; slash-command popup state)
  - B · Ghost-text title (title-first layout kept; title fills in as
    ghost text with Tab-to-edit; @-mention chip state)
  - C · No title field (prompt-only modal + "Add title" disclosure;
    post-create generation shown landing in the workspace header)
  - D · Title as derived pill in the toolbar (sibling of the branch
    field; inline pill editing)
- Requested: iterate on B (ghost-text title).
  Changed: marked A, C, D as rejected in the tab strip (kept in the
  file for history); B is now the default active tab. Recorded the
  direction in Decisions and the rejections in Rejected Alternatives.
- Requested: (1) make the default state explicit that the title will be
  auto-generated, (2) add a regenerate affordance, (3) refine
  wording/hints.
  Changed: State 1's heading placeholder is now "✦ Auto-generated
  title" (was "Untitled workspace") and the prompt placeholder reads
  "Describe a task for your agent — or create a blank workspace…";
  State 2 adds a "generating title…" note next to the shimmer; State 3
  adds a shuffle (regenerate) button beside the ghost title; State 4's
  reset affordance reworded to "↺ Reset to auto-generate".
- Requested: the edited state is too verbose — no badge, no
  two-line treatment; and clarify what happens to the magic icon when
  editing starts.
  Changed: State 4 is now a single line. Editing removes the leading
  sparkle entirely; a dimmed sparkle toggle sits at the end of the
  heading (tooltip "Auto-title off — click to re-enable"). Removed the
  "edited" badge and the "Reset to auto-generate" text link.
- Requested: anchor the icon on the right side of the title line; when
  the user starts typing, replace it with a reset icon; drop the "Tab
  to edit" hint (click-and-type = ownership); drop the "generating
  title…" text in favor of animating the magic icon.
  Changed: all four B states now use a flex title row with the icon
  slot on the right. State 1: dim sparkle. State 2: animated sparkle
  (pulse/spin) + shimmer, no text. State 3: shuffle + static sparkle,
  no Tab hint. State 4: sparkle replaced by ↺ reset icon (tooltip
  "Reset to auto-title").
- Requested: icon back next to the text (not far right); make the
  sparkle an on/off toggle (typing toggles it off, no icon swap); when
  auto is on, the text color changes; shimmer the old text instead of
  a skeleton.
  Changed: icons now hug the title text. State 2 shimmer sweeps the
  placeholder/previous-title text in place. State 3 renders the auto
  title in violet with the sparkle toggle on + shuffle. State 4 keeps
  the sparkle (dimmed gray = off) with tooltip "Auto-title off — click
  to re-enable"; the ↺ reset icon is gone.
- Requested: drop the violet auto-title text (normal black is fine);
  pick a better regenerate icon for both the title and the branch.
  Changed: auto title now renders in the default heading color — the
  sparkle alone marks auto mode. The shuffle icon is replaced by
  circular refresh arrows everywhere it appears (title row and branch
  field, all variants).
- Requested: done — wrap up.
  Changed: final pass on Decisions (consolidated the toggle model,
  placeholder, rich prompt input, and generation timing); session
  closed. `mocks.html` keeps all 4 variants (B active, A/C/D marked
  rejected).
