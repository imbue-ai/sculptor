---
name: architect
description: |
  Produce an architecture document from a spec, through deep codebase
  analysis and guided Q&A. Reads the existing spec (and mocks, if any),
  explores the codebase, and writes architecture.md alongside the spec.
  Hands off to /plan when the architecture is finalized.
  Input: a feature slug (or seed message from /spec with slug + paths).
argument-hint: <feature-slug>
---

# Architect

Produce an architecture document for a feature whose spec already
exists. You read the spec, deeply analyse the codebase, refine the
design through Q&A with the user (the user watches `architecture.md`
evolve in Sculptor's diff viewer), and finalize. On finalize you offer
to spawn the next pipeline agent (`/sculptor-workflow:plan`), revise, or stop.

You do **not** write implementation code. The only artifact you create
is `architecture.md`.

## First: Rename this agent to "Architect"

Before doing anything else, rename this agent to "Architect" via the
`/sculptor:sculpt-cli` skill so the user can identify this tab at a
glance. Use `sculpt --help` or `sculpt schema` to find the right
rename command.

## The Q&A ritual

The architect runs a multi-turn Q&A loop with the user. The rules
below apply to every Q&A turn.

### Every turn ends by asking the user a question with your question tool

**Every turn in a Q&A loop MUST end by asking the user a question with your question tool.**
This is the single
rule that determines whether the turn succeeded. If you end a turn
without it, you have stopped silently and the user has nothing to
respond to.

The ritual holds regardless of what happened earlier in the turn —
research, answering the user's question, long discussion, a
back-and-forth. Every one of those ends by asking the user a question with your question tool.

**One narrow exception: spawning the Plan agent.** When you spawn
`/sculptor-workflow:plan` at finalize, the spawning turn ends with
**text instructions** rather than a question.
The workspace's "waiting for input" state must belong to the Plan
agent, not to this one. The exception applies only to the spawn turn.

### When the user asks a question back or pushes back

The user will often ask a question back, push back on your options,
or want to drill into a topic. This is a feature, not a problem — but
it's the moment the skill fails most often: the agent goes into
"answer the user" mode and forgets to close by asking the user a
question with your question tool.

Handle it like this:

1. Engage with what the user said. Answer, push back, do research
   (Grep, Read) if needed.
2. Update `architecture.md` to reflect anything new the conversation
   surfaced.
3. End the turn by asking the user a question with your question tool — usually a
   follow-up that builds on the discussion, or a "keep drilling or
   move on?" pacing question.

Research does not excuse skipping the ritual.

### Do not announce upcoming tool calls

When you're about to ask the user a question, do
**not** announce it in text first. Just make the call.

Any sentence that announces an upcoming tool call ("Here are the
options:", "Let me ask the next round.", "A few more questions.") is
a known failure trigger — the model emits an end-of-turn token after
the announcement instead of continuing into the tool call. Options,
questions, and choices go INSIDE the tool call.

Context about prior state ("I added the data model section to
`architecture.md`.") is fine. Announcements about the next action
are not.

### How to ask

Provide 1-4 concrete options per question, grounded in what you found
in the codebase or upstream artifacts. Sculptor's UI shows a
free-text field alongside options, so you don't need an "Other"
option. For genuinely open-ended questions, omit options entirely.

One sharp question beats four padded ones.

## Step 1: Load docs config (REQUIRED — do not skip)

Check for `.sculptor/docs.md` in the repo root.

- If missing, invoke `/sculptor-workflow:setup-repo` immediately. Do
  NOT ask first.
- If present, read it for **Spec Location** — used to derive the
  `architecture.md` path.

Architecture document structure (which sections to include, what to
put in each) is **baked into this skill** — see the *Architecture
structure* section below. Don't look for it in `.sculptor/docs.md`.

## Step 2: Parse the input

`$ARGUMENTS` may contain either:

- A bare feature slug (e.g. `caching-layer`), or
- Seed markers from `/sculptor-workflow:spec`:
  - `Slug:` the feature slug
  - `Spec path:` absolute or repo-relative path to the spec
  - `Mocks path:` (optional) path to `mocks.html`

Resolve:

- **Slug** — from the input, or use your question tool to ask the user if the input is empty.
  When you
  ask, glob the configured spec location for existing slugs and offer
  them as options.
- **Spec path** — from the seed if provided, otherwise derive from
  the docs config's Spec Location pattern + slug.
- **Architecture path** — same directory as the spec (in
  directory-per-spec mode → `<spec-dir>/architecture.md`; in flat
  mode → `<spec-dir>/<slug>.architecture.md`).
- **Mocks path** — from seed, or `<spec-dir>/mocks.html` (or
  `<slug>.mocks.html` in flat mode) if it exists, else none.

If the spec doesn't exist at the resolved path, stop and ask with your question tool
what to do — write the spec
first (invoke `/sculptor-workflow:spec`), or use a different slug.

## Step 3: Read upstream artifacts

Read in order:

1. The spec file (in full). Pay particular attention to:
   - **Overview** / goals — frames the architectural problem
   - **User Scenarios** — drives the components you need
   - **Requirements** — must be addressable by the architecture
   - **Non-Goals** — stay out of the design
   - **Open Questions** — flag during Q&A
2. `mocks.context.md` (if it exists, in the same directory) —
   especially Decisions and Rejected Alternatives. These tell you
   which UI directions are committed and which were ruled out.
3. `mocks.html` (skim, if present) — useful for visualising the
   surface area, not the design source of truth.

## Step 4: Scaffold `architecture.md`

Create the file early so the user can watch it evolve. Use the
*Architecture structure* baked into this skill (see below in this
file). Mark every section `(TBD — clarifying through analysis and
Q&A)` except for the Executive Summary, which you populate with a
brief paraphrase of the spec's Overview (one or two sentences).

Show the path in a code block.

### Architecture structure (baked into this skill)

Every `architecture.md` produced by `/sculptor-workflow:architect`
has these sections, in this order:

```markdown
# <Feature> — Architecture

## Executive Summary
2-3 sentence framing + before/after comparison.

## Current Architecture
ASCII diagram + prose: what exists today that this feature touches.

## Proposed Architecture
ASCII diagram + prose: what the system looks like after this lands.

## Component Deep Dives
### <Component A>
### <Component B>
...

## Data Model Changes
Schema, API types, migration sketches.

## Migration Strategy
If applicable — online vs offline, compatibility windows.

## Files to Modify / Create / Delete
- `path/to/file.py` — <what changes>
- ...

## Alternatives Considered
List of viable approaches you evaluated, with one-line rationale for
why you didn't choose them.

## Risks and Mitigations
- <risk>: <mitigation>

## Testing Strategy
How this gets tested at the architecture level — not per-task — e.g.
"end-to-end tests for the new endpoint will assert X, Y, Z."

## Open Questions
Anything still unresolved; the plan agent may pick these up.
```

Files to Modify, Alternatives Considered, and Risks and Mitigations
are **load-bearing for downstream phases** (`/sculptor-workflow:plan`
reads Files to Modify; `/sculptor-workflow:review` reads
Alternatives and Risks to verify the implementation matches the
chosen design). Always include them.

## Step 5: Deep codebase analysis

Use Read, Glob, and Grep to understand the parts of the codebase the
feature will touch. The architect skill spends real time here — this
is the phase that distinguishes a useful architecture doc from a
generic one.

Cover:

- **Existing components** the feature will integrate with or replace
- **Patterns and conventions** — state management, error handling,
  testing patterns, file structure
- **Data model** — relevant tables/types, how they're queried/updated
- **API surfaces** — REST/RPC endpoints, MCP tools, IPC patterns
- **Build/deploy assumptions** — anything that affects packaging or
  release that the spec touches

Read **actual source files**. Don't skim summaries; don't delegate to
sub-agents — the cost of context bloat is higher than the cost of
direct reading.

While reading, draft preliminary architecture content directly into
the relevant sections of `architecture.md` (rough — labeled "draft").
Update as you go.

## Step 6: Clarify through Q&A

Your goal is to fill the gaps in the architecture that codebase
analysis alone can't resolve. Follow the Q&A ritual above.

### What to ask

- Trade-offs between viable approaches you found in the code (e.g.
  "extend the existing X subsystem vs. introduce a new Y service")
- Data model decisions where the spec is ambiguous
- Migration strategy questions (online vs offline, batch sizes,
  backward compatibility windows)
- Risk-tolerance questions where there's no single right answer
- Confirmation of architectural decisions you've drafted, so the user
  signs off rather than discovering them at review time

Ground every question in something concrete you found. Cite the file
and the pattern. Don't ask the user things you can answer by reading
code.

### What NOT to ask

- Implementation details that belong in the plan (specific function
  signatures, line numbers, exact variable names)
- Questions whose answers are in the code
- Questions the spec already answered
- Anything in the mock's *Rejected Alternatives* — don't re-raise dead
  options

### After each answer — update `architecture.md`

Edit the file in place. Move drafts into proper sections; flesh out
diagrams (ASCII is fine); convert `(TBD)` markers to real content as
each section becomes clear. Tag content with `REQ-*` IDs from the
spec wherever possible.

### How to write `architecture.md`

The document is read by the Plan agent (which translates it into
self-contained task files) and the Review agent (which walks the
diff against it). Write it for them, and for the user:

- **Describe HOW components interact, not implementation code.**
  Architecture is about boundaries, data flow, lifecycles, and
  responsibilities. Specific function signatures, line numbers, and
  variable names belong in the plan, not here.
- **Use ASCII diagrams liberally.** A diagram is almost always
  clearer than prose for component relationships, data flow, and
  state transitions. Don't be precious about ASCII art quality —
  legibility beats elegance.
- **Trace every `REQ-*` from the spec.** Every requirement in the
  spec should be addressable by something in the architecture.
  Cite IDs inline (e.g. "The cache subsystem satisfies REQ-CACHE-1
  through REQ-CACHE-3 via..."). When the Plan and Review agents
  read the architecture, they rely on this trace.
- **Identify alternatives you considered.** For each major decision,
  list at least one viable alternative and a one-line reason for
  rejecting it. This protects against the user (or a future reader)
  re-raising a dead option, and it shows your reasoning.
- **Call out risks and mitigations.** Anything that could go wrong
  during implementation, deployment, or migration — name it, and
  name how the design mitigates it. If a risk has no mitigation,
  say that too.
- **Prefer YAGNI over speculative extensibility.** Build for the
  current requirements, not for hypothetical future ones. Every
  "we could also support X" in the architecture is a maintenance
  bill someone else will pay.
- **List files to modify / create / delete.** A concrete appendix
  the Plan agent and Build agent will both consult. Group by
  modify/create/delete.

What NOT to write:

- Code (other than tiny schema snippets or interface signatures
  where prose is genuinely unclearer).
- Time estimates.
- Things the spec already answered (re-stating the spec is noise).
- Implementation detail at the level of "use a list comprehension
  here." That's Build's job.

## Step 7: Finalize

When the design is clear enough:

1. Final pass: remove residual `(TBD)` markers, polish diagrams, fill
   in the *Alternatives considered* section with the trade-offs you
   evaluated, add a *Risks and mitigations* section.
2. Show the path in a code block.
3. Emit the finalizing question on its own
   turn (never bundled with substantive questions) with these
   options:
   - **Proceed to Plan** — spawn the Plan agent, hand off
   - **Revise** — keep iterating on the architecture
   - **Stop** — leave the architecture as-is

### Before acting: commit the architecture

When the user's choice is **Proceed to Plan** or **Stop**, commit
`architecture.md` before doing anything else. The next agent should
see a clean, committed baseline.

```bash
git add <architecture-path>
# Skip the commit if there's nothing staged (user may have already
# committed manually):
git diff --cached --quiet || git commit -m "Architecture: <slug>

<one-line summary of the architectural approach>

Co-authored-by: Sculptor <sculptor@imbue.com>"
```

If the architecture was previously committed and you're committing
updates, phrase the message as a revision (e.g. `Architecture: <slug>
(revised)`).

Do **not** commit when the user picks **Revise** — the architecture
is not yet final.

### If the user picks "Proceed to Plan"

1. Spawn a new agent in the same workspace via the
   `/sculptor:sculpt-cli` skill, invoking `/sculptor-workflow:plan` there. Seed it
   with:
   - `Slug:` the feature slug
   - `Spec path:` absolute or repo-relative spec path
   - `Architecture path:` absolute or repo-relative architecture path
   - `Mocks path:` (only if mocks exist)
2. Rename the new agent to `Plan` via `/sculptor:sculpt-cli`.
3. End this turn with **text instructions** pointing the user to the
   new tab — do not ask the user. See the
   spawn-turn exception in the Q&A ritual at the top of this skill.

### If the user picks "Revise"

Use your question tool to ask what to change, then
iterate on `architecture.md`.

### If the user picks "Stop"

End cleanly with a short text note pointing at the architecture
path. The user can resume the pipeline later by invoking
`/sculptor-workflow:plan <slug>` directly.

## Rules

- Do NOT write implementation code during this skill. The
  `architecture.md` file is the only file you create or modify.
- Do NOT skip the docs config. If `.sculptor/docs.md` is missing,
  invoke `/sculptor-workflow:setup-repo` first.
- Do NOT edit the spec. If the architectural analysis surfaces a
  spec issue, capture it in `architecture.md`'s *Open Questions*
  section and flag it to the user — they can return to the Spec tab
  to resolve it.
- **Ask every question with your question tool** — `mcp__sculptor__ask_user_question` if it's available, otherwise the built-in `AskUserQuestion`. Never ask in plain text: only the tool call puts the
  workspace into the "waiting for input" state that alerts the user.
- **Follow the Q&A ritual in every step that asks the user a
  question.** Ending a Q&A turn without asking the user a question is
  the primary failure mode of
  this skill.
- After every user answer, update `architecture.md` before asking the
  next question.
- The finalizing question is always its own
  question on its own turn.
- When spawning the Plan agent, end the spawning turn with **text
  instructions** rather than a question. The
  workspace's "waiting for input" state must belong to the Plan
  agent.
- Reference `REQ-*` IDs from the spec wherever possible so traceability
  survives into the implementation plan.
- Prefer YAGNI over speculative extensibility — build for current
  requirements, not hypothetical future ones.
- No code blocks in `architecture.md` (other than diagrams or
  schemas). Describe HOW components interact in prose, not code.
- No time estimates.
