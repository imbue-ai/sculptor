# Code

## Code Structure
- **Backend:** `sculptor/sculptor/` (Python — FastAPI server, agents, services, database)
- **Frontend:** `sculptor/frontend/` (TypeScript — Electron + React app, Vite build)
- **Core library:** `imbue_core/` (shared Python library used by backend)
- **CLI tool:** `tools/sculpt/` (Python CLI for interacting with Sculptor)
- **Integration tests:** `sculptor/tests/integration/` (Playwright + pytest)
- **Plugins/skills:** `sculptor/sculptor-plugin/` and `sculptor/sculptor-workflow/` (Claude Code plugins)
- **Build/packaging:** `sculptor/builder/` (Electron Forge packaging)
- **Docs:** `docs/` (style guide, architecture docs)

## Branch Naming
- **Bug-fix branches:** `<name>/bugs/<ticket-id>` (e.g. `dev/bugs/SCU-123`)
- **Feature branches:** `<name>/<feature-description>` (e.g. `dev/skills/fix-bug`)

## Build
- **Full rebuild:** `just rebuild` (clean + install + generate-api)
- **Build frontend:** `just build-frontend`
- **Generate API types:** `just generate-api`

## Run
- **Dev mode (tmux):** `just start` (launches frontend + backend in tmux)
- **Frontend only:** `just frontend` (Electron dev mode)
- **Backend only:** `just backend`

## Pre-commit Verification
- **Format:** `just format`
- **Check (lint + types + ratchets):** `just check`
- **Unit tests:** `just test-unit`

## Publishing Changes
- **Push command:** `git push -u origin <branch>`
- **Create MR/PR (base command):** `gh pr create --base main`
- **Auto-publish allowed:** yes

### Merge defaults
- **Delete source branch on merge:** yes
- **Squash on merge:** no
- **Auto-merge when CI passes:** no
- **Open as draft:** no

### Conventions
- The agent writes the title and body itself — do NOT use `--fill`. Append `--title "<title>" --body "<body>"` (or `--body-file <path>` for a long body) to the base command at runtime.
- Title: one line, imperative, ≤ 70 chars, summarizing the fix (e.g. "Fix login crash when token contains a colon").
- Body: follow the template in the `## Proof of Work` section below — original bug, hypotheses, per-bug repro/expected/before/root cause/fix/test/after.
- No required labels or reviewers.

## Proof of Work

Every PR opened by an autonomous skill must include evidence that the bug
existed and is now fixed. The PR body walks a reviewer through:

1. **Original bug** — exact description (and Linear ticket link if input matched `SCU-<n>`).
2. **Reproduction** — repro steps, plus before-screenshots from `/auto-qa-changes` showing the buggy state.
3. **Hypothesis** — the code path responsible and why.
4. **Fix** — what changed and why it addresses the cause.
5. **Proof the fix works** — after-screenshots from `/auto-qa-changes` showing the correct behavior, plus the failing-test commit hash and the test output now showing pass.

### Optional sections (only when applicable)
- **`## Deferred follow-ups`** — list any adjacent work the agent
  consciously left out of this PR. Because `.sculptor/testing.md` has
  `How to file new tickets` configured, each item MUST also have a
  Linear ticket URL next to it (the agent files them via `/linear`'s
  `create-ticket` entry point). Omit the section entirely if no work
  was deferred.
- **`## Review notes`** — populated by the fix-bug self-review pass
  (Phase A4.5) with any code-review findings the agent declined to
  act on. Required after every autonomous fix-bug run: if the agent
  acted on every finding (or found none), write
  `_(no outstanding review notes)_` so a reviewer knows the review
  pass ran.

### Evidence tooling
- **UI-visible bugs:** use `/auto-qa-changes` to drive the headless browser and capture before/after screenshots.
- **Non-UI bugs:** paste the failing-then-passing output from `/run-integration-test` (or `just test-unit` if a unit test).
- **Other artifacts (optional):** logs, error traces, or curl transcripts when they make the repro clearer.

### Required vs optional
- **Required for every PR:** yes. UI-visible bugs MUST include before/after screenshots. Non-UI bugs MUST include the failing-then-passing test output.

## Dependencies
- **Install all:** `just install`
- **Install frontend:** `just install-frontend`
- **Install test deps:** `just install-test` (Playwright browsers)
- **Python package manager:** `uv`
