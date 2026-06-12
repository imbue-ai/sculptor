---
name: mock
description: |
  Create interactive HTML mocks for a feature through guided iteration with
  the user. Two modes: exploration (generates 3+ end-to-end variants to help
  the user surface ideas) and confirmation (single coherent mock to
  visually verify an existing design). Can be invoked standalone or from
  `/sculptor-workflow:spec` as input to, or output of, a spec.
argument-hint: [feature description]
---

# Mock

Iterate with the user on HTML mocks of a feature. In **exploration mode**
you generate multiple end-to-end variants to help the user figure out what
they want. In **confirmation mode** you generate a single coherent mock
to visually verify a design that is already specified. Either way, the
user iterates, you update the mocks and log every change, and the two of
you decide together when to stop.

You do NOT commit. You do NOT write production code. The only artifacts
you create are `mocks.html` and `mocks.context.md`.

## First: Rename this agent to "Mock"

Before doing anything else, rename this agent to "Mock" via the
`/sculptor:sculpt-cli` skill so the user can identify this tab at a
glance. This applies whether you were spawned by `/sculptor-workflow:spec`
or invoked directly. Use `sculpt --help` or `sculpt schema` to find
the right rename command.

## Step 1: Load docs config (REQUIRED — do not skip)

**You MUST have the docs config before doing anything else.** Do not
proceed to any later step until the file exists and you have read it.

Check for `.sculptor/docs.md` in the repo root.

- If the file is **missing**, immediately invoke the
  `/sculptor-workflow:setup-repo` skill via the Skill tool. Do NOT
  ask the user whether to run it first — just run it.
- Once the file **exists**, read it for:
  - **Spec Location** — the path pattern used to place mock files
  - **UI Reference** — how to match the app's visual style (may be
    blank)

Mock conventions (what good mocks look like) are **baked into this
skill** — see the *Mock conventions* section below. Don't look for
them in `.sculptor/docs.md`.

## Mock conventions (baked into this skill)

Every mock produced by `/sculptor-workflow:mock` follows these rules:

- **Multiple states in a single HTML file.** Each scenario / state is
  clearly labeled with a short description of what it demonstrates.
  Don't split states across files.
- **Realistic app chrome.** Render the mock inside a plausible app
  window — browser chrome, sidebar, header, navigation — not
  isolated components floating on a blank page.
- **Match the app's existing visual style.** Read the UI Reference in
  `.sculptor/docs.md` (or scan frontend code) before guessing colors,
  spacing, typography.
- **Realistic sample data.** Use plausible names, timestamps, content
  — never `foo`/`bar`/`lorem ipsum`.

## Step 2: Parse the input

`$ARGUMENTS` contains the feature description and, when invoked by
another agent, may include these markers:

- `Mode: exploration` or `Mode: confirmation`
- `Target path:` an absolute or repo-relative mock directory
- `Slug:` a pre-chosen slug
- `Associated spec:` the path of an existing spec. **Required in
  confirmation mode** — the mocks are built from the spec. Absent in
  exploration mode (no spec exists yet).

If the feature description is missing or too vague (1-3 words like
"settings page"), use `mcp__sculptor__ask_user_question` to ask the user
to describe the feature in a sentence or two before continuing.

If mode is **confirmation** and `Associated spec:` is missing, stop and
ask the user via `mcp__sculptor__ask_user_question` for the spec path
before proceeding — confirmation mocks without a spec are meaningless.

## Step 3: Determine mode

If `Mode:` is in the input, use it. Otherwise ask via
`mcp__sculptor__ask_user_question`:

- **Exploration** — "I'll generate 3+ end-to-end variants to help you
  explore ideas before you commit to a direction."
- **Confirmation** — "I'll generate a single coherent mock to visually
  verify an existing design."

Default to exploration unless the input clearly references an existing
spec.

## Step 4: Derive slug and file paths

1. **Slug.** If a slug was provided, use it. Otherwise derive one from
   the feature description: kebab-case, 2-5 words, lowercase,
   alphanumeric + hyphens only. If the derived slug is not obvious from
   the feature description, confirm it with
   `mcp__sculptor__ask_user_question`.
2. **Paths.** If a `Target path:` was provided, use it. Otherwise derive
   from the **Spec Location** pattern in `.sculptor/docs.md`:
   - **Directory-per-spec** pattern (e.g. `specs/<slug>/spec.md`) →
     mocks live at `specs/<slug>/mocks.html` and
     `specs/<slug>/mocks.context.md`.
   - **Flat** pattern (e.g. `docs/<slug>.md`) → mocks live at
     `docs/<slug>.mocks.html` and `docs/<slug>.mocks.context.md`.
3. If `mocks.html` already exists at the target location, ask the user
   via `mcp__sculptor__ask_user_question` whether to extend it, replace
   it, or pick a new slug.

## Step 5: Resolve the visual anchor

Look at the **UI Reference** section of `.sculptor/docs.md`:

- If it points at code, a design system, or Storybook — read the
  referenced material and use it as the visual anchor.
- If it is empty — scan the repo's frontend code via Glob and Grep.
  Look for a component library, design tokens, or existing pages you
  can imitate.
- If the UI Reference is empty **and** the repo has no discoverable
  frontend code (brand-new project, pure backend), STOP and ask the
  user via `mcp__sculptor__ask_user_question`:
  - What visual style the mocks should follow (e.g. clean minimal,
    dashboard, mobile-first)
  - Any reference sites or apps to imitate
  - Target platform (web, mobile web, etc.)

  Do not silently produce an unstyled mock.

## Step 6: Scaffold `mocks.context.md` up front

Before generating any HTML, write `mocks.context.md` with this
structure. The user watches it evolve in Sculptor's diff viewer as you
work:

```markdown
# <Feature Name> — Mock Context

## Description
<paraphrase the feature description and any clarifications from earlier
steps>

## Decisions
(TBD — filled in as the user confirms design directions)

## Rejected Alternatives
(TBD — filled in as the user rules out variants or tweaks)

## Tweaks Log
(empty — appended to on every iteration)
```

The **Decisions** and **Rejected Alternatives** sections are
load-bearing: if the skill was invoked from `/sculptor-workflow:spec`, the spec writer
reads them at handoff to populate the spec's Requirements and User
Scenarios. Keep them short, concrete, and lift-ready.

## Step 7: Initial generation

Write `mocks.html` with the initial mocks.

### Exploration mode

Generate **at least 3 distinct end-to-end approaches**. Variants must
differ in meaningful ways (layout, information density, interaction
model) — not cosmetic nits like a color tweak. Each variant must show
the full feature end-to-end: if the feature has 5 screens, each variant
contains all 5.

Pick the presentation shape based on feature size:

- **Small UI element** (single screen, no flow) — stack variants as
  labeled sections in the page, each with a short heading and one-line
  description of what it demonstrates.
- **Larger arc** (multi-screen flow) — use in-document tabs, one tab
  per variant. Tabs must be self-contained (vanilla JS or CSS-only, no
  external dependencies). Inside each tab, the variant's screens lay
  out top-to-bottom with labels.

### Confirmation mode

**Before generating, read the spec at `Associated spec:` in full.** It
is the primary source of truth — the feature description from
`$ARGUMENTS` is secondary context. Pay particular attention to:

- **Overview / User Scenarios** — drive the screens and states you mock
- **Requirements** — must be visible or implied by the mock
- **Non-Goals** — stay out of the mock
- **Open Questions** — note them; you may surface them during iteration

Generate a single coherent mock with labeled states (e.g. empty state,
loaded, error, permissions-denied, loading). No variants — the design
is already committed in the spec.

### For both modes

The mock must follow the *Mock conventions* baked into this skill
(see Step 1): realistic app chrome, multiple states clearly labeled,
match the visual style from Step 5's resolution, realistic sample
data — no `foo`/`bar`/`lorem ipsum`.

After generating, show the user both file paths in code blocks so they
can open them, then immediately enter Step 8's iteration loop by asking
what they want to change (via `mcp__sculptor__ask_user_question`) and
emitting the checklist footer.

## Step 8: Iterate

This is the main loop. It continues until the user says they are done.

### Turn structure — NON-NEGOTIABLE

Every turn in Step 8 MUST end with both:

1. A **checklist footer** in the text output:
   ```
   Updated mocks.html: yes/no
   Logged tweak in mocks.context.md: yes/no
   Summary: <one line describing what you did this turn>
   ```
2. A call to `mcp__sculptor__ask_user_question` (asking what to tweak
   next, or offering to wrap up — see below).

The text-output footer comes first, then the tool call closes the turn.
Ending a turn without the footer is the primary failure mode of this
skill. Ending without `mcp__sculptor__ask_user_question` is the second.

### On every user answer

1. **Update `mocks.html`** to reflect the requested change.
2. **Append to the Tweaks Log** in `mocks.context.md`:
   ```
   - Requested: <what the user asked for>
     Changed: <what you did>
   ```
3. **If the answer confirms a direction**, add a concrete bullet to
   **Decisions**.
4. **If the user rules out a variant, tweak, or approach**, move it to
   **Rejected Alternatives** with a one-line reason.
5. **Keep rejected variants in `mocks.html`.** Do not delete them.
   `mocks.html` is a historical record of exploration, not just a
   snapshot of the final design.

### When to offer to wrap up

When the user seems satisfied (no new tweaks landing, they say they're
happy, or the conversation is clearly winding down), use
`mcp__sculptor__ask_user_question` to offer:

- **I'm done** — wrap up the mock session
- **Keep iterating** — stay in Step 8
- **Revisit a rejected alternative** — pull a rejected variant back
  for another look

The user always has the final call on when to stop.

## Step 9: Wrap up

When the user says they're done:

1. **Final pass on `mocks.context.md`:**
   - Make sure **Decisions** reflects the final state of the mocks
     (no `(TBD)` left behind — move any residual content to Decisions
     or Rejected Alternatives).
   - Keep the **Tweaks Log** as-is; it's a historical record.
2. **Show the user the final paths** in code blocks:
   - `mocks.html` (all variants, including rejected ones)
   - `mocks.context.md` (Decisions, Rejected Alternatives, Tweaks Log)
3. **Do not commit.** The user commits when they like.

### If invoked from `/sculptor-workflow:spec`

The user's next step is to return to the Spec tab and tell it they're
done. The Spec agent will read `mocks.context.md` and proceed with
the spec using Decisions and Rejected Alternatives as input.

## Rules

- **Use `mcp__sculptor__ask_user_question` for every question.** The
  built-in `AskUserQuestion` tool is blocked in Sculptor. Always use
  `mcp__sculptor__ask_user_question`.
- **Every turn in Step 8 MUST end with the checklist footer AND
  `mcp__sculptor__ask_user_question`.** The footer is the drift-prevention
  anchor; the tool call keeps the ritual intact. Missing either is a
  failure.
- **Do NOT commit.** The mock skill never runs `git commit`. Users
  commit on their own schedule.
- **Do NOT delete rejected variants from `mocks.html`.** They are
  historical record. Rejecting means moving the variant's rationale
  into `mocks.context.md`'s Rejected Alternatives — not deleting the
  HTML.
- **Do NOT skip the docs config.** If `.sculptor/docs.md` is missing,
  invoke `/sculptor-workflow:setup-repo` first.
- **Do NOT produce an unstyled mock.** If the repo has no UI Reference
  and no discoverable frontend code, ask the user for direction before
  generating anything.
- **Do NOT announce upcoming tool calls in text.** Phrases like "Let me
  ask what you think next" or "Here are some options:" followed by a
  tool call are a known failure trigger — the model emits end-of-turn
  instead of the tool call. Say nothing about what you're about to do;
  just do it.
