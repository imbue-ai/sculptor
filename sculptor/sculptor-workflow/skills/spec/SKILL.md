---
name: spec
description: |
  Write an implementation spec through guided Q&A before writing code.
  Scaffolds the spec file up front, clarifies the user's goals, then
  explores the codebase and refines through interactive Q&A so the user
  watches the spec evolve in the diff viewer. Offers HTML mocks at the
  start (or mid-Q&A) for UI-heavy features.
  Input: a description of the feature or change to spec out.
---

# Write Spec

Write an implementation spec through conversation. You scaffold the spec
file up front, clarify the user's goals, explore the codebase, and
refine the spec through Q&A — the user watches it take shape in
Sculptor's diff viewer as they answer. You do **not** write
implementation code during this skill — only the spec.

For UI-heavy features you also offer HTML mocks (via the `/sculptor-workflow:mock`
skill, spawned as a separate agent in the same workspace) as input
to the spec, or as confirmation at the end.

## First: Rename this agent to "Spec"

Before doing anything else, rename this agent to "Spec" via the
`/sculptor:sculpt-cli` skill so the user can identify this tab at a
glance (and distinguish it from any "Mock" tab spawned later in the
flow). Use `sculpt --help` or `sculpt schema` to find the right
rename command if you don't already know it.

## The Q&A ritual

Several steps below involve multi-turn conversation with the user —
most obviously **Step 4** (goals) and **Step 7** (fill the spec), but
also any step that asks the user a question via
`mcp__sculptor__ask_user_question`. The rules in this section apply
whenever you're in a Q&A loop. Later steps add step-specific content
(what to ask, how to update the file) on top of these.

### Every turn ends with mcp__sculptor__ask_user_question

**Every turn in a Q&A loop MUST end with an
`mcp__sculptor__ask_user_question` tool call.** This is the single
rule that determines whether the turn succeeded. If you end a turn
without it, you have stopped silently — the user has nothing to
respond to and the skill is stuck.

Before ending any turn, verify: *did this turn emit an
`mcp__sculptor__ask_user_question` call?* If not, emit one now.

The ritual holds regardless of what happened earlier in the turn —
research, answering the user's question, long discussion, a
back-and-forth. Every one of those ends with
`mcp__sculptor__ask_user_question`.

**One narrow exception: spawning a Mock agent.** When you spawn a
mock-creator agent in Step 6, Step 7's escape hatch, or Step 9, the
spawning turn ends with **text instructions** rather than
`mcp__sculptor__ask_user_question`. This is deliberate: the
workspace's "waiting for input" state must belong to the Mock agent
while the user is iterating on mocks, not to the Spec agent —
otherwise the Mock agent's attention signals are masked. The
exception applies only to the mock-spawn turn itself. Once the user
replies, you're in a normal Q&A turn again and the ritual resumes.

### When the user asks a question back or wants to discuss

The user will often:

- Ask a question back (e.g. "How will this work with X?")
- Push back on your options ("none of these fit — what if we did Y?")
- Want to drill into a topic before committing to an answer

This is a feature, not a problem. When it happens, the conversational
frame shifts: you owe the user a response before asking anything new.
**This is the moment the skill fails most often** — the agent goes
into "answer the user" mode and forgets to close the turn with
`mcp__sculptor__ask_user_question`.

Handle it like this:

1. **Engage with what the user said.** Answer their question. Push
   back on their pushback. Do research (Grep, Read) if needed to
   answer concretely.
2. **Update the spec file** to reflect anything new the conversation
   surfaced.
3. **End the turn with `mcp__sculptor__ask_user_question`.** Usually
   this is a follow-up that builds on what you just discussed
   ("Given what I found in `foo.py`, which of these do you prefer?"),
   but it can also be "do you want to keep drilling into this, or
   move on?" — so the user stays in control of the pace.

The turn still ends with you asking. The user drives the conversation;
you drive the spec forward.

### When the user's answer requires research

The silent-stop failure is especially likely when a user's answer
prompts more exploration (Grep, Read, or another round of codebase
digging) before the next question. Research output eats your output
budget, and the final synthesis step — including the
`mcp__sculptor__ask_user_question` call — gets skipped.

Do the research. Then still update the spec file and still emit
`mcp__sculptor__ask_user_question` in the same turn. Research does
not excuse skipping the ritual.

### Do not announce upcoming tool calls in text

When you're about to call `mcp__sculptor__ask_user_question`, do
**not** announce the call in text first. Just make the call.

Any sentence that announces an upcoming tool call — whether it ends
in a colon before a list, or a period before a transition — is a
known failure trigger. The model frequently emits an end-of-turn
token *after the announcement* instead of continuing into the tool
call. Examples of announcement preambles that trigger this:

- "Here are the options:" / "A few approaches:" / "The reasonable
  paths are:"
- "Let me offer the choice to finalize."
- "Let me ask the next round."
- "Now let me pose the remaining questions."
- "A few more questions."
- "Next I'll ask about X."

Delete any such sentence and emit the tool call directly. Options,
questions, and choices go INSIDE the
`mcp__sculptor__ask_user_question` call, not as preamble describing
what you're about to do.

**Context about the prior state is fine** (e.g. "I updated the User
Scenarios section with that flow.", "Grepping turned up one related
helper in `foo.py`."). **Announcements about the next action are
not.** The rule: say nothing about what you're *about to* do — just
do it.

### How to ask

Use the `mcp__sculptor__ask_user_question` tool for every question.
Provide concrete, distinct options grounded in what you found in the
codebase. Sculptor's UI always shows a free-text field alongside the
options, so you do not need to include an explicit "Other" option.
For open-ended questions, provide no options and rely on the
free-text field.

Ask 1-4 questions per round. One sharp question is better than four
padded ones.

## Step 1: Load docs config (REQUIRED — do not skip)

**You MUST have the docs config before doing anything else.** Do not
proceed to any later step until the file exists and you have read it.

Check for `.sculptor/docs.md` in the repo root.

- If the file is **missing**, immediately invoke the
  `/sculptor-workflow:setup-repo` skill via the Skill tool. Do NOT
  ask the user whether to run it first — just run it.
- Once the file **exists**, read it. It tells you:
  - **Spec Location** — where spec files live and how they're named.
    Drives Step 3 (scaffold).
  - **UI Reference** — used if mocks are involved (see Step 6).

Spec structure (which sections the spec contains, how to write each)
is **baked into this skill** — see Step 3 for the scaffold and Step 7
for the writing guidance. Don't look for those in `.sculptor/docs.md`.

## Step 2: Parse the input

`$ARGUMENTS` is the feature description. If it's empty or too vague
(1-3 words like "add caching"), use `mcp__sculptor__ask_user_question`
to ask the user to describe the feature in one or two sentences before
continuing. Follow the Q&A ritual above.

## Step 3: Scaffold the spec

Create the spec file now, before clarifying goals or exploring the
codebase. The user will watch it evolve in Sculptor's diff viewer from
this point on.

1. Derive a slug from the feature: 2-5 kebab-case words, lowercase,
   alphanumeric + hyphens only. Example: `caching-layer`.
2. Use the **Spec Location** path pattern from `.sculptor/docs.md` to
   determine the full path. If the target path already exists, append
   `-2`, `-3`, etc.
3. Write the file with the section scaffold below. Mark every section
   `(TBD — clarifying in Q&A)` except for **Overview**, which you
   populate now by paraphrasing `$ARGUMENTS`:
   - If `$ARGUMENTS` is a sentence or two, paraphrase lightly.
   - If it's a longer prompt, extract the goals-level content and
     drop implementation detail.
   - If it's 1-3 words, write it as-is — Step 4's goals round will
     pull out the actual goals.
4. Show the path in a code block so the user can open it.

Keep Overview **clearly rough** — not polished prose. It's a starting
point, not a committal. The user should read it and think "yes, that's
what I said, but let me sharpen it."

### Spec structure (baked into this skill)

Every spec produced by `/sculptor-workflow:spec` has exactly these
sections, in this order:

```markdown
# <Feature Name>

## Overview
The problem and the motivation. Why this needs to exist. Who it's for.

## User Scenarios
Narrative walkthroughs of key flows, including edge cases. Each
scenario is its own subsection or coherent paragraph. Reference
`REQ-*` IDs inline where a scenario exercises a specific requirement.

## Requirements
Bulleted list of what must be true when the feature is done. Each
requirement is tagged with a `REQ-<CATEGORY>-<N>` identifier (e.g.
`REQ-AUTH-1`), grouped by functional area, written in MUST/SHOULD/MAY
language, and stated as testable behaviour. See *Writing the
Requirements section* in Step 7 for full guidance.

## Non-Goals
What is explicitly out of scope.

## Open Questions
Unresolved decisions or ambiguities. The architect, plan, and review
agents will pick these up later.
```

If mocks exist next to the spec at finalize time, Step 8 prepends a
`## Mocks` section linking to `mocks.html`.

## Step 4: Clarify goals

Establish what the user is actually trying to achieve before you dive
into the code. Follow the Q&A ritual above.

Focus on:

- **Problem / motivation** — what pain, opportunity, or need drives
  this? (The "why now?")
- **Success criteria** — how will the user know this was worth
  building, from a user's perspective?
- **Audience** — whose experience changes, and how?
- **Non-goals** — what are they explicitly NOT trying to do?

Pick 1 to 3 that are genuinely missing from `$ARGUMENTS` and ask via
`mcp__sculptor__ask_user_question`. Skip anything the input already
covers.

**Skip this step entirely if `$ARGUMENTS` already covers problem,
audience, and success.** Manufacturing goals questions against a
well-formed prompt pads the flow and burns trust. Proceed straight to
Step 5.

Multiple rounds are fine if the user wants to keep discussing goals.
The single invariant is:

> **Every question in Step 4 must be about goals, outcomes, audience,
> or scope — never implementation.**

No data models, APIs, file paths, frameworks, libraries, or
architecture questions here. That's Step 7's job. When you catch
yourself about to ask an implementation question, that's the signal to
move on to Step 5 — even if some goals ambiguity remains (later Q&A
can resolve residual gaps).

### After each answer

Edit Overview in place, integrating the user's answer. If the answer
rules something out, put it in the **Non-Goals** section (if the spec
structure has one) or add a "what this is NOT" note to Overview.

## Step 5: Explore the codebase

Use Read, Glob, and Grep to understand the parts of the codebase the
feature will touch, scoped by the goals from Step 4:

- Project structure and key modules relevant to the goals
- Existing patterns and conventions
- Files and systems the feature will change or interact with

Spend real effort. Read actual source files. **Never ask the user
questions whose answers are in the code** — look them up yourself.

## Step 6: Decide how mocks fit in

If the feature might touch UI — screens, flows, visual states, anything
a user sees — consider offering HTML mocks. Mocks often help the user
figure out what they want, especially for UI-heavy features.

Use judgment, not keyword pattern-matching:

- If the feature is clearly UI-heavy, offer mocks.
- If it's unclear, offer mocks. False positives are cheap (user picks
  "no mocks"); false negatives are expensive (user discovers mid-Q&A
  they wish they'd started with mocks).
- If the feature is clearly backend-only (database migration, CLI tool
  with no UI, internal refactor), skip this step entirely and go to
  Step 7.

### Special case: input reads like a mock request

If `$ARGUMENTS` was framed as a mock request (e.g. "mock up the
settings page", "show me some ideas for onboarding"), skip the
question below and enter **mock-first** mode directly, using the
user's phrasing as implicit confirmation. The spec is still the outer
frame — they invoked `/sculptor-workflow:spec`, so they want a spec eventually — but
mocks come first.

### The three options

Use `mcp__sculptor__ask_user_question` with:

1. **Mock first (exploration)** — "I'll spawn a mock-creator agent to
   build 3+ HTML variants so you can see options before we fill out
   the rest of the spec. You'll iterate on mocks in the new tab, then
   we'll use them to complete the spec."
2. **Spec first, mock at the end (confirmation)** — "We'll write the
   spec through Q&A now. At the end, I'll offer to spawn a
   mock-creator agent to visually verify the design."
3. **No mocks** — "Skip mocks entirely; spec-only."

### If the user picks "Mock first"

1. Spawn a new agent in the same workspace via the
   `/sculptor:sculpt-cli` skill, invoking `/sculptor-workflow:mock` there. Seed it with
   a concise feature description drawn from the goal-enriched Overview
   (not the raw `$ARGUMENTS`), plus these markers:
   - `Mode: exploration`
   - `Target path:` the same directory as the spec file
   - `Slug:` the slug you derived in Step 3

   Do NOT pass `Associated spec:` — the spec only has Overview at
   this point. The mock agent's handoff artifact `mocks.context.md`
   feeds the rest of the spec, not the other way around.
2. End this turn with **text instructions** — do NOT call
   `mcp__sculptor__ask_user_question`. Briefly tell the user what
   you spawned, point them at the new "Mock" tab, and let them
   know they can come back to this tab whenever they're ready,
   whether that's because mocking is done, they have questions
   about the mocks that affect the spec, or they want to abandon
   mocks and go straight to spec Q&A. Phrase it naturally — do not
   prescribe specific reply phrases. Then end the turn with no
   tool call.

   Why no `ask_user_question` here: that tool puts the workspace
   into "waiting for input" state, which would mask the Mock
   agent's own attention signals. The Spec agent should be quiet
   until the user returns.

3. When the user comes back, infer from their message which path
   they're taking:

   - **They signal mocking is done / ready to proceed with the spec:**
     - Read `mocks.context.md` at the target path.
     - Use the mock's **Decisions** section to pre-populate the
       spec's Requirements and the mock's flows / Tweaks Log to
       pre-populate User Scenarios. Overview (goals) stays as-is
       unless the mocks sharpened something there.
     - In Step 7, skip questions the mocks already answered; focus
       on non-visual gaps (data model, error states, permissions,
       edge cases). Avoid re-raising anything in **Rejected
       Alternatives**.
   - **They have questions about the mocks that affect the spec:**
     - Read `mocks.context.md` and skim `mocks.html`.
     - Answer their question first, then proceed to Step 7 normally
       with the mocks in your context. If more mock work comes up,
       they can spawn another mock agent separately.
   - **They want to abandon mocks:**
     - Proceed to Step 7 as if no mocks exist. Do NOT delete the
       mock files — leave them as-is.

   If their message is genuinely ambiguous between these paths, ask
   a clarifying question — this is a normal Q&A turn now, so use
   `mcp__sculptor__ask_user_question`.

### If the user picks "Spec first, mock at the end"

Remember that the user wants confirmation mocks at finalize. Proceed
to Step 7 normally. In Step 9 (Refine), emphasize the mock-creator
option.

### If the user picks "No mocks"

Proceed to Step 7. The mid-Q&A escape hatch in Step 7 is still
available if the user changes their mind.

## Step 7: Clarify through Q&A

Your goal is to fill the remaining gaps in the spec. The goal is
**not** to ask a fixed number of questions — it is to arrive at a
clear design. Follow the Q&A ritual above.

### What to ask

- Ground every question in what you found in the codebase — reference
  the file or pattern you observed
- Focus on what's new or ambiguous; don't rehash existing conventions
  unless the feature clearly conflicts with them
- Skip questions whose answers are obvious from the code or from the
  user's initial description or the goals already captured in Overview
- Do NOT ask about the spec structure itself — the sections are
  fixed (see Step 3's *Spec structure*).
- Do NOT ask about low-level implementation details — those belong
  in the architecture and the plan, not in the spec.
- If mocks exist for this feature, do NOT ask questions they already
  answered. Do NOT re-raise anything the mock session put in
  **Rejected Alternatives**.

### After each answer — update the spec file

Edit the spec file in place, integrating the user's answer into the
relevant section. The spec file IS the evolving refined prompt —
there is no separate blockquote or draft file.

- Move content out of `(TBD)` placeholders into proper bullets as
  sections become clear
- Use short, readable sentences and bullet points
- If an answer describes a user flow, add it to User Scenarios. If
  it creates a constraint, add it to Requirements. If it rules
  something out, add it to Non-Goals. If it surfaces an unresolved
  trade-off, add it to Open Questions. If it sharpens the goals,
  update Overview.

Keep edits focused and readable — the user is watching every change
in the diff viewer.

### Writing the Requirements section

Requirements are the load-bearing artifact for downstream phases.
`/sculptor-workflow:architect`, `/sculptor-workflow:plan`,
`/sculptor-workflow:build`, and `/sculptor-workflow:review` all
reference them by ID to show traceability from the spec into the
implementation. Write them with that in mind:

- **Identify each requirement with `REQ-<CATEGORY>-<N>`.** Use ALL-CAPS
  short codes (3-5 letters) for the functional area, sequential
  numbers within each category. Examples: `REQ-AUTH-1`, `REQ-AUTH-2`,
  `REQ-CACHE-1`, `REQ-CACHE-2`. Pick categories that match the
  feature's natural sub-areas.
- **Group by functional area.** List all `REQ-AUTH-*` together, then
  all `REQ-CACHE-*`, etc. Use sub-headings inside Requirements if it
  helps readability.
- **Use MUST / SHOULD / MAY** to signal strength. MUST = required
  for the feature to ship; SHOULD = strongly preferred but not a
  blocker; MAY = nice-to-have, can be deferred.
- **Each requirement is testable.** A reader should be able to write
  a test that pass/fails the requirement. "The login form MUST
  validate email format before submit" is testable; "Login SHOULD
  feel intuitive" is not.
- **What, not how.** Requirements describe behaviour and outcomes,
  not implementation. "The cache MUST persist across restarts" — not
  "Use SQLite for the cache." Implementation belongs in
  `architecture.md` and the plan, not in the spec.
- **Reference existing behaviour that must be preserved.** If the
  feature touches something already working, write a requirement
  that says so explicitly (e.g. `REQ-LEGACY-1: Existing X behaviour
  MUST remain unchanged for users who Y`).

If the user's answer is large, split it across multiple `REQ-*`
items rather than packing several requirements into one bullet.
Smaller requirements are easier to trace.

### Writing the User Scenarios section

Scenarios are narrative walkthroughs of how a user interacts with
the feature. Each scenario tells one coherent story; together they
should cover the happy path plus the meaningful edge cases.

- One scenario per coherent flow. Don't merge unrelated flows into a
  single scenario.
- Lead each scenario with a one-line intent ("User signs in for the
  first time"), then prose or a numbered walk-through.
- Cover edge cases as their own scenarios where they materially
  change behaviour (empty state, error state, permission-denied,
  large data, slow network).
- Reference `REQ-*` IDs in-line where a scenario exercises a
  specific requirement, so the trace from scenario → requirement →
  test is visible.

### Mid-Q&A escape hatch — offer mocks when Q&A turns visual

Sometimes a feature's UI-ness only becomes clear a few rounds into
Q&A — the user starts describing what they see, what appears where,
what the interaction feels like. When this happens, proactively offer
to spawn a mock agent.

This only applies if the user did NOT already pick a mock path in
Step 6, or did pick one and chose "Abandon mocks" later. If a mock
session is already in progress or has produced mocks, don't re-offer.
Also do not offer if the user previously selected "stop offering"
(see below).

Use `mcp__sculptor__ask_user_question`:

- **Yes, spawn a mock agent now** — treat this as if the user picked
  "Mock first" in Step 6. Spawn the agent (see Step 6 for the
  invocation), end this turn with text instructions per Step 6 (no
  `ask_user_question` — see the exception in the Q&A ritual), and
  when the user returns integrate the mocks into the spec and resume
  Q&A.
- **No, keep going in Q&A** — continue with your next substantive
  question this same turn.
- **No, and stop offering** — record this; don't offer again for the
  rest of Step 7.

Trigger on judgment, not keywords. If Q&A has clearly turned visual
and the user doesn't have a mock route planned, offer. Don't offer on
consecutive rounds — space them out.

### When to offer to finalize

After each round, evaluate: is the design clear enough to finalize
the spec?

- **If unclear gaps remain:** ask another round.
- **If the design is clear:** offer the choice between finalizing the
  spec now and continuing Q&A. Briefly summarize what you'd still
  want to clarify if they pick "continue." The user always has the
  final call.

**The finalize question must always be its own
`mcp__sculptor__ask_user_question` call, on a turn of its own.**
Never bundle it with substantive questions in the same call. The user
cannot decide whether to finalize until they have seen every
preceding answer reflected in the spec file.

The correct sequence is:

1. User answers the previous round of substantive questions.
2. You update the spec file to integrate every one of those answers.
3. Only then, on a new turn, emit a standalone
   `mcp__sculptor__ask_user_question` with the single finalize
   question — no other questions attached.

If you still have substantive questions you want to ask, ask those
instead (in their own `mcp__sculptor__ask_user_question` call) — the
finalize offer can wait for the next round.

## Step 8: Finalize

When the user confirms they're ready:

1. Do a final pass on the spec file: remove any remaining `(TBD)`
   markers (convert to Open Questions if still unresolved), polish
   bullets, verify every section listed in Step 3's *Spec structure*
   is present.
2. **Link mocks automatically.** If `mocks.html` exists in the same
   directory as the spec file, add a **Mocks** section at the top
   of the spec (just below the title) with a relative link:

   ```markdown
   ## Mocks

   See [mocks.html](./mocks.html) for interactive HTML mocks
   illustrating the user flows described below.
   ```

   No question asked — if mocks exist next to the spec, the spec
   links to them.
3. Show the spec path in a code block.

## Step 9: Refine

Stay in conversation to refine the spec:

- If the user asks for changes, edit the spec file only. Do not
  touch any other files. Preserve the overall structure. (Exception:
  if you revise mocks in a linked mock session, that happens in a
  separate agent.)
- If the user asks "what are the open questions?", list any
  unresolved decisions or trade-offs still in the spec.
- After significant edits, offer to regenerate the open-questions
  list.

**Do NOT begin implementation** until the user explicitly says so.
When they signal they're done refining, use
`mcp__sculptor__ask_user_question` to offer:

- **Create / revise HTML mocks** — spawn a mock-creator agent via
  `/sculptor:sculpt-cli`, invoking `/sculptor-workflow:mock` in `Mode: confirmation`.
  Seed it with the feature description plus these markers:
  - `Mode: confirmation`
  - `Target path:` the mock directory (same as the spec's directory)
  - `Slug:` the slug used for the spec
  - `Associated spec:` the absolute or repo-relative spec path
    (**required** in confirmation mode — the mock agent reads it as
    the primary source of truth)

  If mocks already exist at the target path, note that in the
  invocation so the agent revises rather than overwrites. End this
  turn with the same text instructions as Step 6 — no
  `mcp__sculptor__ask_user_question` (see the exception in the Q&A
  ritual). The Mock agent self-renames on entry, so you don't need
  to rename it here. Let the user know they can come back when
  mocking is done, when they have questions, or if they want to
  abandon, and infer their path from whatever they send.
- **Implement it here, in this tab** — start building it in this
  same agent, following the spec. Best for small features where the
  spec is enough to drive the work.
- **Kick off the full workflow** — spawn an Architect agent that
  will produce an architecture doc, then chain through Plan, Build,
  and Review in their own tabs. Each phase is gated by a finalize
  prompt except the Build → Review hand-off, which runs as the
  plan's final task. Best for larger features
  where the design and implementation benefit from independent
  agent contexts. Use the `/sculptor:sculpt-cli` skill to spawn a
  fresh agent in this same workspace, invoke `/sculptor-workflow:architect` there,
  seed it with these markers:
  - `Slug:` the slug used for the spec
  - `Spec path:` absolute or repo-relative spec path
  - `Mocks path:` (only if mocks exist) absolute or repo-relative
    path to `mocks.html`

  Rename the new agent to `Architect` via `/sculptor:sculpt-cli`,
  then end this turn with text instructions pointing the user to
  the new tab — no `mcp__sculptor__ask_user_question` (same
  spawn-turn exception as Mocks). The Architect will take it from
  there.
- **Leave as a spec** — stop here

If the user picked "Spec first, mock at the end" in Step 6, mention
that the mock option is the natural next step. If the spec describes
a substantial feature (multiple major components, new data models,
or significant UI surface area), mention that the full workflow is
the natural fit; for small features, default to "Implement it here."

### Before acting: commit the spec

Once the user's choice is one of **Implement it here**, **Kick off
the full workflow**, or **Leave as a spec**, commit the spec file
(and `mocks.html` / `mocks.context.md` if they exist next to it)
before doing anything else. The next agent or the next phase of work
should see a clean, committed baseline.

```bash
git add <spec-path> [<mocks-paths>]
# Skip the commit if there's nothing staged (user may have already
# committed manually):
git diff --cached --quiet || git commit -m "Spec: <slug>

<one-line summary of what this spec proposes>

Co-authored-by: Sculptor <sculptor@imbue.com>"
```

Use a descriptive commit message that includes the slug and a brief
summary. If the spec was previously committed and you're committing
updates, phrase the message as a revision (e.g. `Spec: <slug>
(revised)`).

Do **not** commit anything when the user picks **Create / revise HTML
mocks** — the spec is not yet final from your side; you may still
edit it after the mock session returns.

Act on the user's choice.

## Rules

- Do NOT write implementation code during this skill. The spec file
  is the only file you create or modify. Mock files are created by
  a separately-spawned mock-creator agent, not by you.
- Do NOT skip the docs config. If `.sculptor/docs.md` is missing,
  invoke `/sculptor-workflow:setup-repo` first.
- **Use `mcp__sculptor__ask_user_question` for every question.** The
  built-in `AskUserQuestion` tool is blocked in Sculptor.
- **Follow the Q&A ritual (see above) in every step that asks the
  user a question** — Step 2 (if `$ARGUMENTS` is vague), Step 4
  (goals), Step 6 (mock choice), Step 7 (spec Q&A), Step 9
  (refine). Ending a Q&A turn without
  `mcp__sculptor__ask_user_question` is the primary failure mode of
  this skill.
- **Every question in Step 4 must be about goals, outcomes,
  audience, or scope — never implementation.** If you're about to
  ask an implementation question, stop and move on to Step 5
  instead; implementation discussion belongs in Step 7.
- After every user answer, update the spec file before asking the
  next question.
- The finalize question (Step 7) is always its own
  `mcp__sculptor__ask_user_question` call on its own turn, after the
  spec has been updated with all prior answers. Never bundle it with
  substantive questions.
- When mocks exist next to the spec at Step 8, auto-add the Mocks
  link — do not ask.
- When spawning another agent (a Mock agent in Step 6 / Step 7
  escape hatch / Step 9, or an Architect agent in Step 9), end the
  spawning turn with **text instructions** rather than
  `mcp__sculptor__ask_user_question`. This is the one deliberate
  exception to the Q&A ritual: the workspace's "waiting for input"
  state must belong to the spawned agent until the user returns, so
  the Spec agent stays quiet. When the user replies, infer their
  intent from free-form text rather than prescribing reply phrases.
  Never iterate on mocks (or architecture) yourself — that's the
  spawned agent's job.
