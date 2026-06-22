---
name: setup-repo
description: |
  Create or update the repo's Sculptor configs (.sculptor/code.md,
  .sculptor/testing.md, .sculptor/docs.md). These files teach the
  sculptor-workflow skills how to build, run, test, and where to write
  docs in this specific codebase. Run this to set up a new repo, or
  to update the configs when your setup changes.
---

# Setup Repo

Create or update the three Sculptor config files:

- **`.sculptor/code.md`** — codebase structure, branch naming, build/run
  commands, pre-commit verification
- **`.sculptor/testing.md`** — test framework, test strategy, bug tracking,
  manual testing, visual verification
- **`.sculptor/docs.md`** — where specs and their associated docs live,
  where to find UI to imitate (for mocks), which skill to invoke for the
  code-review pass

The configs deliberately cover **locations and operational commands**,
not document structure or writing conventions. Spec, mock, architecture,
and plan structure is baked into the workflow skills — to keep agent
behaviour consistent across repos.

Other skills (`/sculptor-workflow:fix-bug`, `/sculptor-workflow:spec`,
`/sculptor-workflow:mock`, `/sculptor-workflow:architect`,
`/sculptor-workflow:plan`, `/sculptor-workflow:review`) read these
configs.

## Step 1: Check for existing configs

Read `.sculptor/code.md`, `.sculptor/testing.md`, and `.sculptor/docs.md`
from the repo root.

- **If all three exist:** you are updating. Show the user what's currently
  configured and ask what they'd like to change. Skip to **Step 3** to make
  the edits.
- **If some exist but not others:** read the existing ones for context, then
  continue to Step 2 to create the missing ones. You can also offer to
  update the existing ones at the same time.
- **If none exist:** you are setting up from scratch. Continue to Step 2.

## Step 2: Ask the user how to proceed

Ask with your question tool:

> I'd like to set up Sculptor configs for this repo so I can build, test, and
> fix bugs effectively. This is a one-time setup — the configs will be saved
> to `.sculptor/code.md`, `.sculptor/testing.md`, and `.sculptor/docs.md`
> for future use.
>
> How would you like to proceed?
>
> **Option A:** I'll explore the repo to auto-detect your project structure,
> build commands, test framework, and conventions, then confirm with you.
>
> **Option B:** You tell me directly — maybe you already have docs, skills, or
> specific instructions you'd like me to follow.
>
> **Option C:** A mix — I'll auto-detect what I can, then ask you about the
> rest.

**Wait for the user's response before proceeding.**

## Step 3: Gather information

Based on the user's choice, gather the information below. For auto-detection,
look at `package.json`, `pyproject.toml`, `Cargo.toml`, `Makefile`, `justfile`,
`CLAUDE.md`, existing test files, directory structure, and CI config.

**Cap auto-detection effort:** if you haven't found clear answers after reading
~10 files, stop and ask the user.

### Code config information

**Required:**

| Topic | What to learn | Example |
|-------|--------------|---------|
| **Code structure** | Where source code lives, key directories | `src/`, `lib/`, backend vs frontend split |
| **Branch naming** | Convention for new branches (bug fixes, features, etc.) | `<name>/bugs/<ticket-id>`, `fix/<description>`, `<name>/<feature>` |
| **Build** | How to build the project | `npm run build`, `cargo build`, `just rebuild` |
| **Run** | How to run the app locally | `npm run dev`, `just start`, `cargo run` |
| **Pre-commit verification** | Commands to run before committing | `just format && just check && just test-unit` |
| **Publishing changes** | How to push the branch and create an MR/PR, the team's merge-time defaults (delete source branch, squash, auto-merge, draft), and whether autonomous skills are allowed to publish without asking | `git push -u origin <branch>` + `glab mr create --target-branch main --remove-source-branch` (autonomous skills append `--title` / `--description` at runtime); `gh pr create --base main` (autonomous skills append `--title` / `--body`); or "manual only — don't auto-publish" |
| **Proof of work** | What evidence the team requires in every MR/PR body: how to capture before/after screenshots for UI-visible bugs, what test output to paste, and any other artifacts | "Use `/auto-qa-changes` for before/after screenshots, paste the failing-then-passing test output"; "screen recordings via QuickTime"; "test output only — no UI here" |

**Optional** (ask about these — the user may or may not have them):

| Topic | What to learn | Example |
|-------|--------------|---------|
| **Dependencies** | How to install/update dependencies | `npm install`, `uv sync`, `cargo fetch` |
| **Environment setup** | Env vars, config files, or services needed | ".env file required", "needs Postgres running" |
| **Deployment** | How to deploy or release | "Push to main triggers CI deploy" |

**Publishing changes — what to ask:**

This section is read by autonomous workflows (e.g. `/fix-bug --autonomous`) to
decide whether and how to push and open an MR/PR on the user's behalf. Ask
the user enough to fill in:

- **Push command** — usually `git push -u origin <branch>`, but some teams
  push to a different remote.
- **MR/PR tool** — `glab` (GitLab), `gh` (GitHub), or `manual` (no CLI; the
  team opens the MR/PR in the browser).
- **Target branch** — usually `main`, sometimes `master` or a release branch.
- **Title and body** — autonomous skills compose a detailed title and body
  themselves (see `## Proof of Work` below) and pass them via `--title` /
  `--description` (glab) or `--title` / `--body` (gh). The captured command
  is the **base command** only — do NOT include `--fill` in it, because
  `--fill` would substitute a thin commit message and defeat the Proof of
  Work template.
- **Auto-publish allowed** — `yes` or `no`. If `no`, autonomous workflows
  must stop after committing the fix and leave publishing to the user. Default
  to `no` if the user is unsure — they can flip it later.
- **Merge defaults** — properties of the MR/PR set at creation time. Ask each
  as a plain yes/no:
  - **Delete source branch on merge?**
  - **Squash on merge?**
  - **Auto-merge when CI passes?**
  - **Open as draft?**
- **Conventions (optional)** — required labels, reviewers, title format, body
  template.

Assemble the **MR/PR command** from the tool + target branch + merge defaults
using the table below. Write the assembled command into `.sculptor/code.md` so
the autonomous workflow can run it verbatim — don't make the workflow
re-derive flags at runtime.

| Default | `glab mr create` flag | `gh pr create` flag |
|---------|-----------------------|---------------------|
| Target branch | `--target-branch <name>` | `--base <name>` |
| Delete source branch on merge | `--remove-source-branch` | _(set at merge time: `gh pr merge --delete-branch`)_ |
| Squash on merge | `--squash-before-merge` | _(set at merge time: `gh pr merge --squash`)_ |
| Auto-merge when CI passes | _(post-create: `glab mr merge --when-pipeline-succeeds <iid>`)_ | `--auto` (plus `gh pr merge --auto` or repo setting) |
| Open as draft | `--draft` | `--draft` |
| Title (set by agent at runtime) | `--title "<text>"` | `--title "<text>"` |
| Body / description (set by agent at runtime) | `--description "<text>"` (for large bodies, pass `--description "$(cat <file>)"`) | `--body "<text>"` (or `--body-file <file>`) |
| ~~Use last commit as title/body~~ — **do not use for autonomous mode** | ~~`--fill`~~ | ~~`--fill`~~ |

For `gh`, the squash / delete-source-branch defaults can't be set at create
time — they're applied when the PR is merged. Capture them in the Merge
defaults block anyway (so the autonomous workflow can append the right flags
to a later `gh pr merge` call, and so a human reviewer can see the intent).

If the team picks `manual`, write the manual flow as prose under
**Create MR/PR** (e.g. "open the GitLab compare URL printed by `git push`")
and skip the flag table.

**Proof of work — what to ask:**

This section is read by autonomous workflows to decide what evidence to
gather while fixing a bug and what to paste into the MR/PR body. It's the
team's standard for what proves a fix is real. Ask the user enough to fill
in:

- **UI-visible bugs — screenshot tooling.** What does the team use to capture
  before/after screenshots? Common answers:
  - `/auto-qa-changes` (Sculptor's headless-browser harness, ideal for any
    repo with a frontend the skill can drive)
  - OS-level screenshot tools (macOS Screenshot, ShareX) for desktop apps
  - Screen recordings (QuickTime, Loom) when motion matters
- **Non-UI bugs — what artifacts.** Usually the failing-test commit hash plus
  the test runner output showing it now passes. Some teams also want logs,
  a benchmark before/after, or a curl-based repro transcript.
- **Required vs nice-to-have.** Is the evidence MANDATORY for every MR/PR, or
  just expected when applicable? Default to mandatory if the user is unsure
  — it's easy to relax later.

The goal of this section is to make the standard explicit so autonomous
workflows produce MR/PR bodies a reviewer can trust without re-running the
repro themselves.

### Docs config information

**Required:**

| Topic | What to learn | Example |
|-------|--------------|---------|
| **Spec location** | Where spec files live and how they're named | `specs/<slug>/spec.md`, `docs/specs/<slug>.md`, `.sculptor/specs/<slug>.md` |

Spec structure, mock conventions, and architecture structure are
**not** configured here — they're baked into the workflow skills so
agent behaviour stays consistent across repos. Don't ask the user
about them.

**Auto-written (do NOT ask):** `.sculptor/docs.md` also includes a
`## UI Reference` section (empty placeholder with a guiding comment).
The `/sculptor-workflow:mock` skill reads it to learn how to match
your app's visual style. The user can fill it in later.

**Auto-written (do NOT ask):** `.sculptor/docs.md` also includes a
`## Code Review` section naming the skill that
`/sculptor-workflow:review` invokes for the code-review pass.
Auto-detect:

- If `.claude/skills/code-review-checklist/SKILL.md` exists in the
  repo, write `Skill: /code-review-checklist`.
- Otherwise leave the field empty — `/sculptor-workflow:review` will
  skip the code-review pass and only verify requirements coverage and
  tests.

The user can edit either section later.

### Testing config information

**Required:**

| Topic | What to learn | Example |
|-------|--------------|---------|
| **Test strategy** | When to write e2e vs unit tests, and when to skip tests | "Strongly prefer e2e; unit only as last resort" |
| **Test framework** | What framework is used | pytest, jest, cargo test, go test |
| **Test runner command** | How to run a single test file | `pytest path/to/test.py -v` |
| **Single test command** | How to run one specific test | `pytest path/to/test.py::test_name` |
| **E2e test runner** | How to run e2e / browser-driven tests (ask only if the team has e2e tests and they run with a different command or skill than unit tests) | "Use the `/run-integration-test` skill", `npx playwright test`, "same as unit tests" |
| **Test location** | Where test files go | `tests/` next to source, `__tests__/`, etc. |
| **Test conventions** | Naming, fixtures, patterns | "Look at `tests/test_auth.py` as a reference" |

**Optional** (ask about these — the user may or may not have them):

| Topic | What to learn | Example |
|-------|--------------|---------|
| **Bug tracking** | System, how to fetch tickets, how to file new tickets, how to comment on tickets, how to change ticket state, and the state name to use when the agent concludes a bug is unreproducible | "Linear, use `/linear` skill" for all four operations; needs-info state: `Triage` |
| **Manual testing** | How to launch and interact with the app | "Use `/auto-qa-changes` skill" or "`npm run dev`, then open localhost:3000" |
| **Visual verification** | How to verify visual changes | "Annotate screenshots with Pillow" or "just eyeball it" |
| **Test debugging** | How to debug failing tests | "Use `/debug-integration-test` skill" or "read the pytest output" |
| **Test writing skill** | A skill or doc for writing tests | "Use `/write-integration-test` skill" |
| **Test types and locations** | Different categories of tests | "E2e tests in `tests/e2e/`, unit tests next to source" |

## Step 4: Write the configs

Write all three files using the templates below. Only include sections that
are relevant — omit optional sections that don't apply.

### `.sculptor/code.md`

```markdown
# Code

## Code Structure
- **<component>:** `<path>` (<brief description>)

## Branch Naming
- **Bug-fix branches:** <pattern, e.g. `<name>/bugs/<ticket-id>`>
- **Feature branches:** <pattern, e.g. `<name>/<feature-description>`>
- **Example:** <e.g. `jane/bugs/PROJ-42`, `fix/login-crash`>

## Build
- **Full build:** `<command>`

## Run
- **Dev mode:** `<command>`

## Pre-commit Verification
- **Format:** `<command>`
- **Check (lint + types):** `<command>`
- **Unit tests:** `<command>`

## Publishing Changes
- **Push command:** `<command, e.g. git push -u origin <branch>>`
- **Create MR/PR (base command):** `<assembled command WITHOUT --fill, e.g. glab mr create --target-branch main --remove-source-branch>` <!-- autonomous skills append --title / --description (glab) or --title / --body (gh) at runtime -->
- **Auto-publish allowed:** `<yes | no>` <!-- read by autonomous skills; if "no", they stop after committing and let the user publish -->

### Merge defaults
- **Delete source branch on merge:** `<yes | no>`
- **Squash on merge:** `<yes | no>`
- **Auto-merge when CI passes:** `<yes | no>`
- **Open as draft:** `<yes | no>`

### Conventions (optional)
- <required labels, reviewers, title format, body template>

## Proof of Work

Every MR/PR opened by an autonomous skill must include evidence that the
bug existed and is now fixed. The MR/PR body walks a reviewer through:

1. **Original bug** — exact description (and ticket link, if any).
2. **Reproduction** — repro steps, plus before-evidence (screenshots / logs /
   error trace) showing the buggy behavior.
3. **Hypothesis** — what code path was responsible and why.
4. **Fix** — what changed and why it addresses the cause.
5. **Proof the fix works** — after-evidence (screenshots / test output /
   logs) showing the correct behavior, plus a link or hash for the
   failing-test commit.

### Optional sections (only when applicable)
- **`## Deferred follow-ups`** — list any adjacent work the agent
  consciously left out of this MR. If the testing config has a
  "How to file new tickets" entry point, each item MUST also have a
  tracker ticket URL next to it. Omit the section entirely if no
  work was deferred.
- **`## Review notes`** — populated by the fix-bug self-review pass
  with any code-review findings the agent declined to act on.
  Required after every autonomous fix-bug run: if the agent acted on
  every finding (or found none), write `_(no outstanding review
  notes)_` so a reviewer knows the review pass ran.

### Evidence tooling
- **UI-visible bugs:** <e.g. capture before/after with `/auto-qa-changes`>
- **Non-UI bugs:** <e.g. paste the failing-then-passing test output from `/run-integration-test`>
- **Other artifacts (optional):** <e.g. logs, benchmark deltas, curl transcripts>

### Required vs optional
- **Required for every MR/PR:** <yes | no, with conditions> <!-- e.g. "yes for any UI-visible change" -->

## Dependencies (optional)
- **Install:** `<command>`

## Environment Setup (optional)
- <any required env vars, config files, or services>

## Deployment (optional)
- <how to deploy or release>
```

### `.sculptor/docs.md`

Write the file exactly as below, substituting the path pattern from the
user's answer and (if auto-detected) the Code Review skill.

```markdown
# Docs

Locations and operational config for the sculptor-workflow skills.
Document structure (spec sections, architecture sections, mock
conventions, plan layout) is baked into the skills — not configured
here.

## Spec Location
- **Path pattern:** <from the user's answer, e.g. `specs/<slug>/spec.md`>

## UI Reference

<!--
  Optional: tell the `/sculptor-workflow:mock` skill how to match your app's
  visual style. Examples:
    - "Read frontend/src/components/ for the component library."
    - "See docs/design-system.md for tokens and spacing."
    - "Use the Storybook at localhost:6006."
    - "Standalone project — no existing app to match."
  If empty, the mock skill will scan the repo for UI code on its own.
  If there is neither a UI Reference nor discoverable frontend code, the
  mock skill will ask for direction before generating.
-->

## Code Review

The configured skill below is invoked for code-review passes by:
- `/sculptor-workflow:review` at the end of the full feature workflow.
- `/sculptor-workflow:fix-bug`'s self-review phase (Phase 4 interactive
  / Phase A4.5 autonomous), so a fix isn't considered done until its
  diff has been reviewed.

<!--
  Set this to your repo's review skill, e.g. /code-review-checklist.
  If left empty, both /review and fix-bug's self-review phase skip
  the code-review pass.
-->

Skill: <skill-name>
```

### `.sculptor/testing.md`

```markdown
# Testing

## Test Strategy
<when to write e2e vs unit tests, and when to skip tests entirely>

## Test Framework
- **Framework:** <name>
- **Run a test file:** `<command>`
- **Run a single test:** `<command>`
- **Run e2e tests:** <command or skill — omit this line if e2e tests run with the same command as unit tests>
- **Test location:** <where test files go>
- **Conventions:** <naming, fixtures, patterns, or "see <file> as reference">

## Bug Tracking (optional)
- **System:** <name>
- **Ticket ID format:** <pattern, e.g. SCU-123, PROJ-42>
- **How to fetch ticket context:** <instructions or skill name>
- **When to fetch:** <e.g. "whenever input matches ticket format", "always required", "only if user provides a ticket ID">
- **How to file new tickets:** <instructions or skill name + entry point, e.g. "use the `/linear` skill's `create-ticket` entry point"> <!-- read by /fix-bug autonomous mode to file deferred-work follow-ups -->
- **How to comment on tickets:** <instructions or skill name + entry point, e.g. "use the `/linear` skill's `comment` entry point"> <!-- read by /fix-bug autonomous mode to leave evidence on tickets the agent declines to fix -->
- **How to change ticket state:** <instructions or skill name + entry point, e.g. "use the `/linear` skill's `set-state` entry point"> <!-- read by /fix-bug autonomous mode to move tickets to a "needs info" state -->
- **Needs-info state name:** <workflow-state name, e.g. `Triage`, `Needs Info`, `Awaiting Reporter`> <!-- the state /fix-bug autonomous mode moves a ticket to when it concludes the bug is unreproducible from the description -->


## Manual Testing (optional)
- **How to test:** <instructions or skill name>
- **Notes:** <any setup steps, URLs, or caveats>

## Visual Verification (optional)
- **How to verify:** <instructions or skill name>

## Test Debugging (optional)
- **How to debug:** <instructions or skill name>

## Test Writing (optional)
- **How to write tests:** <instructions or skill name>
- **Test types and locations:** <if there are multiple categories>
```

## Step 5: Write, confirm, and commit

### Write the files

Write all three files to `.sculptor/code.md`, `.sculptor/testing.md`, and
`.sculptor/docs.md`.

### Ask the user to review

Use your question tool to ask the user to review the files:

> I've written the config files to `.sculptor/code.md`,
> `.sculptor/testing.md`, and `.sculptor/docs.md`. Please review them and
> let me know if anything needs to be adjusted.

**You MUST ask with your question tool here** — `mcp__sculptor__ask_user_question` if it's available, otherwise the built-in `AskUserQuestion` — not a plain text message. The tool call is what raises the "waiting for input" status that alerts the user.
The tool triggers a UI notification in Sculptor that grabs the user's attention
— without it, the user may not notice the question.

**Wait for the user's response.** If they request changes, update the files
and confirm again.

### Commit

Once the user confirms, commit the files:

```bash
git add .sculptor/code.md .sculptor/testing.md .sculptor/docs.md
git commit -m "Add Sculptor repo config"
```
