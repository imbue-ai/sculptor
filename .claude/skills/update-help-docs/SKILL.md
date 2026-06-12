---
name: update-help-docs
description: |
  Update the Sculptor help docs (docs/help/ in this repo) to match a
  specific Sculptor release. Must be run from a Sculptor checkout on the
  matching release branch. Audits the markdown against that source,
  rewrites stale text, and recaptures/processes screenshots via the
  /auto-qa-changes harness. Does NOT commit or push — hands back a dirty
  working tree for the user to review.

  Inputs:
  - Required: Sculptor version to target, e.g. "0.27". The skill verifies
    the current branch is release/sculptor-v<version>.0 before proceeding.
---

# Update Sculptor Help Docs

> **Note: docs live in this repo at `docs/help/`.** The Sculptor help docs are maintained here, alongside the code. This skill edits the markdown and images under `docs/help/` in the current checkout.
>
> **Publishing:** `/sculptor:help` fetches the docs live from `imbue-ai/sculptor` on GitHub, so edits you make here go live to users once they land on `main` there. Editing `docs/help/` in a local checkout does not by itself change what `/sculptor:help` returns.

This skill updates the docs under `docs/help/` so their prose and screenshots match the current Sculptor app. The docs are served live to `/sculptor:help`, so accuracy matters: a wrong button name or a stale screenshot ends up in users' answers.

## Inputs

- **Required: Sculptor version.** Format is `<major>.<minor>`, e.g. `0.27`. The skill expects you to already be on `release/sculptor-v<version>.0` in the current checkout. It does not change branches for you — if you're on the wrong branch, it stops and tells you.
The help docs live at `docs/help/` and the images at `docs/help/images/`. All paths in this document — both the docs and source-path references (`sculptor/frontend/src/...`, `sculptor/sculptor/web/skills.py`, etc.) — resolve against the current working directory, which must be the Sculptor checkout on the release branch.

## What you do NOT do

- **Never commit, branch, or push.** This workflow produces an uncommitted diff; the user handles git from there. Confirm this boundary up front if the user hints at automation.
- **Never read the large PNG screenshots directly from your own context.** Always delegate "describe this image" to a subagent — a dozen 2× screenshots will blow out your context window fast.
- **Do not annotate screenshots.** No highlight boxes, no arrows, no spotlight/dim effects, no text labels. Use cropping to direct the reader's eye — see Phase 5.
- **Do not pause to confirm scope mid-run.** Invoking this skill runs the full workflow. Only stop if genuinely blocked (server refuses to start, a destructive action would overwrite user work). "This would take a while" is not a blocker.

## No phase is optional

Phases 1–6 run on every invocation, in order, with no shortcuts.

- A phase's output may be empty (no drift in Phase 2, zero reshoots in Phase 4, zero annotations in Phase 5). That is a valid result of running the phase — it is not a license to skip it.
- Every phase has an end-of-phase gate. You may not advance to the next phase until its gate passes.
- If you find yourself thinking "nothing changed so I can skip ahead", re-read this section. The check step of each phase is what decides "nothing changed"; you do not decide that on vibes.
- Hedging words (*optional*, *if needed*, *when appropriate*) do not appear in this skill's phase descriptions. If you think you see one, re-read the containing sentence — it is almost certainly scoped to a sub-choice inside the phase, not to whether the phase itself runs.

## Preconditions

Before starting, verify every item below. If any fails, stop and tell the user what needs to change — do not proceed, do not switch branches for them.

1. **Current branch matches the version input.** Run `git rev-parse --abbrev-ref HEAD`; it must equal `release/sculptor-v<version>.0` (e.g. version `0.27` → branch `release/sculptor-v0.27.0`). If it doesn't match, tell the user they need to check out that branch first and re-invoke. Don't attempt the checkout yourself — they may have in-flight work on the current branch.
2. **Record the commit SHA** for the Phase 6 report: `git rev-parse HEAD`. Keep it in conversation state.
3. **The working tree is clean enough to review.** Check `git status` for `docs/help/` — the user should be able to tell your changes apart from theirs. If `docs/help/` already has uncommitted changes, ask before proceeding.
4. **`uv`, `python3`, and Pillow (`PIL`) are available** (Pillow is used by the processing script and by the cropping step). The image-processing script is bundled with this skill at `.claude/skills/update-help-docs/scripts/process-screenshots.py` — it lives in the skill, not under `docs/help/`.
5. **The `/auto-qa-changes` skill is available.** Read that skill before starting — Phase 4 launches its harness every run (to drive the per-image audit, even when no reshoot turns out to be needed), so you need the server lifecycle, port handling, and API details that this skill does **not** duplicate.

A note on the branch-match rule: if the user just cut a new release, their local branch list may not have `release/sculptor-v<version>.0` yet. Suggest `git fetch --all --tags && git checkout release/sculptor-v<version>.0` in that case.

## Content guidance

The docs are read by external customers running the installed Sculptor app. Three rules shape what belongs in the prose; apply them both in Phase 2 (what to flag as wrong) and Phase 3 (what to write). Violations of any rule are a WRONG verdict even if the underlying claim is technically accurate.

1. **Use only words the user sees in the UI.** If a concept exists in the code but has no visible name in the app, don't name it in the docs — describe the user-visible behavior instead.

    *Example:* the frontend splits slash-picker entries across `common/builtinSkills.ts` and `common/pseudoSkills.ts`, but the `/` picker renders them identically. Docs should say "built-in commands" (or just list them); never "pseudo-skills".

2. **Experimental and off-by-default features live on a dedicated page, not scattered through the main docs.** If a feature requires a settings toggle, feature flag, or env var to turn on, most users will never encounter it. It belongs under a separate "Experimental features" page (create one if none exists yet); do not sprinkle it through Workspaces / Agents / Interface / Code Review / etc. A reader of a main page should come away understanding only the default-on behavior.

    *Example:* in-place workspaces are off by default. They don't belong in the main Workspaces page. If a main page mentions them, that's a WRONG verdict in Phase 2 — the fix is to move the content to the Experimental page (or trim it), not to refine the wording in place.

3. **No dev-build references.** Customers install a packaged app. Don't mention `uv run`, `just start`, `.dev0` version suffixes, cloning the Sculptor repo, running from source, or anything else that only applies to people developing Sculptor. Any existing dev-flow reference in the docs is a WRONG verdict.

## Phase 1: Survey the help docs

Read every doc-page markdown file under `docs/help/` in full, plus the index at `docs/help/README.md`. At the time of writing the pages are `getting_started.md`, `workspaces.md`, `chat.md`, `terminal.md`, `agents.md`, `changes.md`, `pull_requests.md`, `slash_commands.md`, `command_palette.md`, `settings.md`, and `experimental/container_backend.md` — but do not hard-code this list. Glob `docs/help/**/*.md` and read what is actually there.

While reading, build a list of every factual claim that needs verification. These typically fall into buckets:

- **Named UI elements** — button labels, panel names, tab names, dialog titles
- **Paths on disk** — `~/.sculptor/workspaces/...`, clone vs in-place layout
- **Flows** — the step ordering of "create workspace", "review changes", "add a repo"
- **Keyboard shortcuts** — the `cmd+…` table
- **Slash commands** — the list of built-ins and what each does
- **Image references** — `![alt](images/<name>.png)` lines (paths are relative to `docs/help/`)

Also list `docs/help/images/`. The repo stores only the final padded versions of each image (1200×800 sage-green-padded PNGs) — there is no separate raw/processed split. Note which images are referenced from markdown and which are orphaned.

## Phase 2: Audit text against the Sculptor source

Dispatch **parallel `Explore` subagents**, each owning one or two doc files, to verify the claims you listed in Phase 1. Each subagent should:

- Receive the doc content (or file path) and a list of specific claims to verify
- Return a claim-by-claim verdict: **VERIFIED / WRONG / PARTIAL / MISLEADING**, with the file:line in the Sculptor source that proves it

Parallelism matters: one subagent per 1–2 doc files keeps the main context small and the turnaround fast. Do **not** do the verification yourself in the main thread.

### Where truth lives (starting points, not exhaustive)

Sculptor source conventionally lives under `sculptor/`. Start from these anchors; let the code tell you the rest.

- **Frontend UI:** `sculptor/frontend/src/`
  - Chat: `pages/workspace/components/ChatInput.tsx`, `chat-alpha/TurnFooter.tsx`
  - Workspace chrome: `components/WorkspaceBanner.tsx`, `components/AgentTabs.tsx`, `components/BottomBar.tsx`, `components/RepoSegment.tsx`
  - Panels: `panels/workspacePanels.ts`, `panels/ActionsPanel.tsx`, `panels/ActionDialog.tsx`, `panels/TerminalPanel.tsx`, `panels/useTerminal.ts`
  - Slash commands (source of truth): `common/builtinSkills.ts`, `common/pseudoSkills.ts` + the matcher in `ChatInput.tsx`
  - Keybindings: `common/keybindings/definitions.ts`
  - Settings: `pages/settings/SettingsPage.tsx` and subsections
  - Sidebar icons / test IDs: `components/panels/SidebarIcon.tsx`
- **Backend / paths:** `sculptor/sculptor/utils/build.py` (workspace layout), `sculptor/sculptor/clone_strategy.py`, `sculptor/sculptor/local_terminal_manager.py`, commit API `commit_workspace_changes`
- **Electron main:** `main.ts` (container-backend URL regex, window config)
- **Test IDs:** `sculptor/sculptor/constants.py` — the `ElementIDs` StrEnum

### Produce an audit table

For each doc file, produce a compact table: `Claim | Status | Source` — this is the input to Phase 3. Keep it in conversation state (no need to write to disk). Do not start editing until the table for every file is complete.

### What each verdict means — no "close enough"

For text:

- **VERIFIED** — no text change.
- **WRONG / MISLEADING** — rewrite to match source.
- **PARTIAL** — rewrite. PARTIAL is not "close enough"; `/sculptor:help` ingests these docs verbatim, so partial is wrong.

For images associated with the claim (by being inside the same doc section): any verdict other than VERIFIED marks the image for reshoot in Phase 4. "The image still looks plausible" does not override this — if the claim needed a rewrite, the illustrating image needs a reshoot.

### Add/update/remove decisions

- **Remove** when the feature no longer exists in the code (e.g., a hover tooltip replaced by a slash command). Delete the prose and `rm docs/help/images/<name>.png`.
- **Update** when the concept still exists but the name/wording/path is stale. Prefer the exact string from the source.
- **Add** when a shipped concept is absent from the docs and a user would plausibly ask `/sculptor:help` about it.

### End-of-phase gate (Phase 2)

Before advancing to Phase 3, confirm:

- [ ] Every doc file under `docs/help/**/*.md` (plus the index at `docs/help/README.md`) has an audit table.
- [ ] Every PARTIAL/WRONG/MISLEADING row names the source `file:line` that proves the verdict.
- [ ] Every non-VERIFIED row has an entry on the Phase 4 reshoot candidate list (unless the doc section has no image).

## Phase 3: Rewrite the markdown

Edit each doc in place (prefer `Edit` for surgical changes; use `Write` for rewrites). Style rules observed in the existing docs:

- Second person, short sentences, no emojis
- Button/command names in `**bold**`, file paths and code in backticks
- H1 per page, `---` separators between sections
- Image reference sits immediately above the section it illustrates, using `![alt](images/<name>.png)` (paths are relative to `docs/help/`; the repo stores only the final padded image at `docs/help/images/<name>.png`)
- Written for two audiences simultaneously: a human customer, and the `/sculptor:help` skill that ingests the markdown and answers questions from it — so keep claims literal and verifiable

When the top-level structure changes (a page added or removed), also update `docs/help/README.md` (the index / table of contents, with a one-line description per page).

## Phase 4: Recapture screenshots

Phase 4 always runs. It answers "which images need to be reshot?" — not "should I run this phase?". If the answer is zero, Phase 4 still runs through its preflight (launch harness, seed curated demo, audit each image against its spec) and produces an empty reshoot list.

The reshoot list is deterministic. An image goes on it if ANY of these are true:

- Its claim had a PARTIAL / WRONG / MISLEADING verdict in Phase 2.
- The doc section that references it had text rewritten in Phase 3.
- Its Phase 4.4 spec audit (a subagent-read of the current processed image against the spec below) returns anything other than a clean YES.

"The image still looks plausible" is not a keep reason. "The image would be extra work to reshoot" is not a keep reason.

### 4.1 Known gotchas (read first — these have bitten previous runs)

1. **Headless xterm renders blank.** `xterm.js` uses `@xterm/addon-webgl` which produces a transparent canvas under headless Chromium. The manual-test harness must launch Chromium with `--disable-webgl --disable-webgl2` so xterm falls back to the canvas renderer. If the terminal screenshot is empty or garbled, check `sculptor/sculptor/testing/manual_test_harness.py` for those flags. Headed mode does NOT fix this on macOS.
2. **Default viewport is too small for docs.** The harness defaults to 1400×900. For docs screenshots, launch the server with `--viewport-width 1920 --viewport-height 1200` — fixed-px UI chrome looks proportional rather than chunky.
3. **Don't background the server with `run_in_background`.** The tool timeout kills it. Use `nohup … &` with a pidfile, per the `/auto-qa-changes` skill.
4. **Onboarding modal blocks the home page on a fresh instance.** Dismiss it via its `ONBOARDING_*` testids before trying to reach workspaces.
5. **The default demo repo is unusable.** The harness default `manual_test_repo` / `testing` branch produces a workspace banner reading `manual_test_repo › testing` and file names like `performance-log.txt` and `stuff.txt`. That makes Sculptor look like internal tooling in every docs screenshot. Section 4.3 is mandatory, not a fallback.
6. **Never inspect PNGs from the main thread.** Every "does this screenshot show what I want?" check goes through a subagent: "Describe `/path/to/0012_get.png`, focusing on whether the Actions panel is open on the right edge and whether the Add Action dialog is visible."
7. **The slash-command picker shows the local user's installed skills and commands.** Sculptor scans `~/.claude/skills/` *and* `~/.claude/commands/` on every picker open (see `discover_skills` in `sculptor/sculptor/web/skills.py`) — so whatever the person running the harness has installed leaks into the docs screenshot. If any image in the reshoot list shows the `/` picker open, rename both dirs out of the way and relaunch the harness before capturing:
    ```bash
    mv ~/.claude/skills ~/.claude/skills.docs-hidden 2>/dev/null || true
    mv ~/.claude/commands ~/.claude/commands.docs-hidden 2>/dev/null || true
    # … relaunch harness, capture slash picker, shut harness down …
    mv ~/.claude/skills.docs-hidden ~/.claude/skills 2>/dev/null || true
    mv ~/.claude/commands.docs-hidden ~/.claude/commands 2>/dev/null || true
    ```
    The clean picker should show exactly: six built-ins (`/batch`, `/clear`, `/context`, `/copy`, `/loop`, `/simplify`) plus the four stock `sculptor:*` plugin skills (`fix-bug`, `help`, `sculpt-cli`, `setup-repo`). `discover_skills` also scans the repo's `.claude/skills` and `.claude/commands`, but because 4.3 mandates `--project-path /tmp/sculptor-demo/widget-store` (no `.claude/` dir), the repo scan is a no-op — if the demo path ever changes, re-check this. Plugin skills live under the Sculptor install and stay visible. **Verify before cropping**: dispatch a subagent to read the raw source and confirm no row shows a "Custom" badge and no row has a name outside that set. If any Custom row is visible, the rename didn't take effect — reshoot, don't crop around it. Always restore both dirs before shutting down, even on error paths.

### 4.2 Launch the harness

Use the `/auto-qa-changes` skill for the actual launch — this skill does not re-document the server lifecycle. At minimum you need:

```bash
export SCREENSHOTS_DIR="$PWD/attachments/screenshots"   # or any writable dir
mkdir -p "$SCREENSHOTS_DIR"
SCULPTOR_MANUAL_TEST_HIDE_FAKE_MODELS=1 \
nohup uv run --project sculptor python -m sculptor.testing.manual_test_server \
  --screenshots-dir "$SCREENSHOTS_DIR" \
  --viewport-width 1920 --viewport-height 1200 \
  > /tmp/manual-test-server.log 2>&1 &
echo $! > /tmp/manual-test-server.pid
```

The `SCULPTOR_MANUAL_TEST_HIDE_FAKE_MODELS=1` env var hides the "Fake Claude" and "Fake Claude 2" test-only models from the model picker. The harness normally turns on integration-testing mode (which shows them) so live tests can exercise them; for docs screenshots we want the production model list. This env var is read by `manual_test_harness.py` and flips `TESTING__INTEGRATION_ENABLED=false` only for this run — it does not affect regular integration tests.

Poll the log for the `MANUAL_TEST_CONTROL_PORT=` line to find the port. Hit `/status` until the server is ready. Dismiss onboarding as the first interaction.

### 4.3 Seed a curated demo — required, every run

The harness default (`manual_test_repo` / `testing` branch) is never acceptable in docs screenshots. Always seed a curated repo before launching the harness. This is not a fallback step — it runs unconditionally.

Create `/tmp/sculptor-demo/widget-store/` as a recognizable TypeScript e-commerce sample:

- Real-looking `package.json` (name `widget-store`, a handful of deps), `README.md`, `src/` with a few `.ts` files (e.g. `products.ts`, `cart.ts`, `checkout.ts`), `tests/` with one test.
- `git init`, initial commit on `main`. The banner will show `widget-store › <branch>` — check it before you start capturing.

Launch the harness with `--project-path /tmp/sculptor-demo/widget-store`. Create the workspace with a meaningful name (e.g. `add-search-bar`, `wire-up-checkout`) — not `default`, not `test`, not `<feature>-module`.

Drive the demo so that the following UI states all exist simultaneously — any of them may be needed by images in Phase 4.4 (which derives what to shoot from the current docs, not a hardcoded list here):

- Visible in-progress todos in the Agent tasks panel (mid-run captures need the agent still thinking).
- A diff with at least 2 files changed.
- Terminal pane populated with real output — usually a `git log` or a test run.
- A second agent in the same workspace (spawn it before the first agent finishes so both tabs are visible).

Verify each before proceeding: banner shows `widget-store`, workspace name is meaningful, agent has in-progress todos, diff has ≥2 files, terminal has output, two agent tabs present. If any are missing, fix the setup — do not proceed to 4.5.

### 4.4 Audit each image and build the reshoot list

There is no hardcoded canonical image list in this skill — features come and go, and any list here would rot. The docs repo is the source of truth for which images currently exist; the markdown section that references each image is its spec.

**For every image in `docs/help/images/`:**

1. **Find the markdown reference.** Which doc file + section links `images/<name>.png`? If nothing references it, the image is orphaned — flag it for the Phase 6 report, don't silently delete.
2. **Use the section's prose as the image's spec.** The prose describes what the image must show; don't look elsewhere.
3. **Decide the outcome using Phase 2's verdict on that section:**
    - **Feature removed (Phase 3 deleted the section):** `rm docs/help/images/<name>.png`. No reshoot.
    - **Section rewritten (PARTIAL / WRONG / MISLEADING in Phase 2):** add to reshoot list. The new prose is the new spec.
    - **Section VERIFIED (prose unchanged in Phase 3):** dispatch a per-image subagent to check the image still matches the prose against the current release. If drift without text change, add to reshoot list. Otherwise, no reshoot.

**Spec-audit prompt for VERIFIED sections** (run per image):

> Read the section in `docs/help/<doc-file>` that references `images/<name>.png`, then look at the image at `docs/help/images/<name>.png`. Against the current app at release `<version>`, does the image still accurately depict what the prose describes? Answer YES or NO plus one sentence. If NO, name what's different.

**Then check for coverage gaps.** Walk Phase 2's audit table for user-facing features in the release branch that are NOT covered by any existing doc section. For each such feature that rises to "most customers would ask `/sculptor:help` about this," **surface a proposal in the Phase 6 report** — do not create new doc pages or images inline. Each proposal includes:

- Proposed image name
- Target doc file and section placement
- One-sentence description of what the image would show
- Why it warrants its own image vs. being covered by an existing section

Adding a new page or image is a scope change; let the user decide and re-run the skill (or hand-edit) to add them. Document the gap in the report, not in the diff.

**Special case for the slash-commands image** (if one exists in the docs): gotcha #7 applies — the `~/.claude/skills` and `~/.claude/commands` dirs must be renamed out of the way before the capture so the user's personal skills don't leak into the picker. The picker should show only the built-ins from `common/builtinSkills.ts` + `common/pseudoSkills.ts` and the stock `sculptor:*` plugin skills (audit-table can confirm the exact set for the release).

**Final reshoot list for this run:**

- Every image whose section was rewritten in Phase 3.
- Every VERIFIED image whose spec-audit subagent returned NO.
- Nothing else — proposed new images live in the report, not the diff.

### 4.5 Drive each capture

For every image on the reshoot list:

1. Drive the UI to the desired state with `locate` → `click`/`type`/`hover`/`press` → `wait` (for `CHAT_INPUT`) or `wait_for_hidden` (on `THINKING_INDICATOR`). Each step returns a numbered screenshot in `$SCREENSHOTS_DIR` (e.g., `0012_get.png`).
2. Delegate visual verification to a subagent before proceeding: "Describe `<path>` focusing on X; confirm Y is visible and Z is not." If the subagent does not return a clean match to the 4.4 spec, fix the UI state and reshoot — do not carry a "close enough" frame into Phase 5.
3. Keep the verified raw frame in `$SCREENSHOTS_DIR` for now — do **not** copy it to `docs/help/images/` yet. The repo only stores the final cropped + padded image; Phase 5 produces that and writes it directly to `docs/help/images/<canonical-name>.png`.
4. If a feature was removed, `rm docs/help/images/<name>.png` and delete the `![…](images/<name>.png)` line from the doc.

### 4.6 End-of-phase gate

Before advancing to Phase 5, every item below must be true. If any is false, loop back inside Phase 4 — do not carry partial state forward.

- [ ] The harness was launched with `--project-path /tmp/sculptor-demo/widget-store`, not the default repo.
- [ ] The workspace name is meaningful (e.g. `add-search-bar`), not `default`, `test`, or the prompt topic in snake-case.
- [ ] Every image on the reshoot list has a verified raw capture in `$SCREENSHOTS_DIR` (subagent confirmed it matches the 4.4 spec). Phase 5 will crop, pad, and write the final image to `docs/help/images/`.
- [ ] No banner in any reshot image shows `manual_test_repo` or the `testing` branch.
- [ ] Screenshots were captured at `--viewport-width 1920 --viewport-height 1200`.

## Phase 5: Crop and process

Phase 5 always runs. Every image on the Phase 4 reshoot list is cropped here — the crop directs the reader's eye; there is no other form of emphasis.

### 5.1 Crop every reshot image

**The screenshots in the help docs are cropped views of the running app.** No annotations, no spotlight dim, no arrows, no labels. The cropping is the pointing. Earlier iterations used tight crops around a single control or overlaid highlight boxes — both of those approaches lose the context a reader needs to locate the feature. Don't do either.

**The crop rule.** Every crop must satisfy three things:

1. **The entire subject is visible.** No part of the control, panel, dialog, or row of tabs that the image is meant to illustrate is cut off. If the subject is "the Agent tasks panel," the full panel is in frame — header, content, and bottom. If the subject is the "Commit N changes" button, the whole button with its label is in frame. This is the one rule there's no wiggle on.
2. **Crop along natural UI boundaries.** Panel edges, horizontal dividers, the top of the tab bar, the bottom of the status bar. Never cut through the middle of a button, a label, a tab, or a row of text. If an element straddles your intended bound, expand to include the whole element or contract to exclude it — don't split it.
3. **Enough surrounding context to orient — but no more.** A reader should be able to recognize *where in the app* the subject lives without needing the full window. Usually that means one or two adjacent anchors (a sidebar, an adjacent panel edge, the tab bar above, the status bar below). This is a judgment call — you're not trying to touch viewport edges or hit a specific subject-to-frame ratio, you're trying to answer "can a reader place this?" with the minimum surrounding area needed.

**Exception.** An image whose purpose *is* to show the whole app at a glance — typically the hero/overview image referenced at the top of the docs — is not cropped. The whole viewport is the subject. You can tell from the referencing prose: if the section is an overview of the app or a landing page, don't crop; if the section is about a specific panel, control, or flow, do crop.

**Reference examples to calibrate against:**

- *Code review / commit button:* the whole Files panel (Browse/Changes/Commits tabs, file tree, "Commit N changes" button fully visible), plus enough of the tab bar and sidebar next to it that you can tell it's the left-side panel. Don't crop out the bottom of the panel — the button lives there.
- *Agent tabs:* the tabs row with the chat input above and the status bar below. Not a full-width slice of the app — just enough horizontally that you can see tabs sitting between chat and status.
- *Popover above the chat input (slash picker, mention picker, model picker, etc.):* the popover **plus the full chat input it sits on top of, plus the keyboard hints below**, plus a few lines of chat content above so the reader can place the popover in the conversation. The popover alone is not the subject — the popover anchored to its trigger is. A tight crop around just the popover dialog loses the context that makes the image legible. If the popover is tall (e.g. the slash picker with 10+ rows), let the crop be tall too rather than shrinking the popover.

### 5.2 Mechanics

Do the cropping with Pillow while the harness is still running — you need `locate` for the bounds.

1. For each image, `locate` the subject (use its test ID from `sculptor/sculptor/constants.py`) and any adjacent elements you plan to include for orientation. Viewport coordinates multiply by `device_scale_factor` (2 for the 1920×1200 → 3840×2400 retina PNG) to get image pixels.
2. Compute the crop bounds. Start from the subject's bbox with a small margin, then expand until the three rules in 5.1 are satisfied — no further.
3. Keep the verified raw capture in `$SCREENSHOTS_DIR` until 5.3 writes the final image to `docs/help/images/<name>.png`. The existing `docs/help/images/<name>.png` (if any) is the previous release's final padded image — leave it untouched until 5.3 overwrites it, so a failed crop doesn't lose the prior version.
4. Crop with Pillow, writing the cropped intermediate to a scratch path (not `docs/help/images/` yet — 5.3 produces the padded final there):

    ```python
    from PIL import Image
    img = Image.open(f"{SCREENSHOTS_DIR}/<raw-capture>.png")
    crop = img.crop((left, top, right, bottom))   # image pixels
    crop.save(f"{SCREENSHOTS_DIR}/<name>-cropped.png")
    ```

**Verification is mandatory and iterative — you may NOT skip it.** The main thread cannot inspect the PNG itself; you must dispatch a subagent. Verify the cropped intermediate (before 5.3 pads it) — this is the last point at which the bounds are easy to fix. Use this exact three-question format (not a narrative prompt — the structure is what makes the verdict unambiguous):

> Look at `$SCREENSHOTS_DIR/<name>-cropped.png`. The subject this image is meant to show is **<concrete description, e.g. "the Files panel with Changes tab active and the 'Commit N changes' button visible">**. Answer each question on its own line:
>
> (a) Is the entire subject visible, with nothing cut off? YES or NO. If NO, name exactly what is missing or partially cut.
>
> (b) Are any controls, labels, tabs, or text rows cut through mid-element (not cleanly bounded by a panel edge or divider)? YES or NO. If YES, name where.
>
> (c) Can you tell where in the app the subject lives from the surrounding elements in the crop? YES or NO. If NO, say what context is missing.

**Ship criteria.** Advance only when (a) = YES, (b) = NO, and (c) = YES. Anything else — including a qualified YES such as "mostly visible" or "probably OK but the bottom edge is ambiguous" — means recompute bounds and recrop. Do **not** ship "close enough". Do **not** skip verification because the capture looked fine live — crops are computed from image pixels, which don't match what you saw in the harness, so regressions show up only here.

If iteration 2 still fails: go back a step. The raw capture may not contain what you need (subject too close to a viewport edge, modal obscuring it, etc.). Fix the capture, don't keep shaving pixels off the crop.

### 5.3 Pad to final dimensions and write to `docs/help/images/`

The image-processing script lives with this skill (not under `docs/help/`). For each verified crop, run it directly against the cropped intermediate and write the padded result to `docs/help/images/<name>.png`:

```bash
python3 .claude/skills/update-help-docs/scripts/process-screenshots.py \
  "$SCREENSHOTS_DIR/<name>-cropped.png" \
  "docs/help/images/<name>.png"
```

The script pads the crop with sage green (#A6AA91) to 1200×800 — aspect ratio preserved, image centered. This is the final form that lands in the repo; the markdown references it as `images/<name>.png` (relative from `docs/help/`). There is no separate `processed/` subdir — the repo stores only the padded final.

Run this per image, on demand, as each crop is verified. There is no batch step.

### 5.4 End-of-phase gate

Before advancing to Phase 6, every item below must be true. If any is false, loop back inside Phase 5.

- [ ] Every reshot image except the full-app overview (if any) has been cropped.
- [ ] For each crop, a subagent answered the 5.2 three-question verification (against the cropped intermediate in `$SCREENSHOTS_DIR`) with (a) YES, (b) NO, (c) YES — explicit YES/NO answers, not qualified. Any qualified or negative answer was treated as a fail and the crop was redone. Verifications that were skipped, batched ("all look fine"), or self-assessed from the main thread don't count.
- [ ] No screenshot contains annotations (boxes, arrows, dim, labels).
- [ ] For each verified crop, `process-screenshots.py` was run and the padded 1200×800 result was written to `docs/help/images/<name>.png`.
- [ ] Every `![…](images/<name>.png)` reference in markdown resolves to an existing file under `docs/help/images/`.

## Phase 6: Shut down and report

1. **If you renamed `~/.claude/skills` and/or `~/.claude/commands` for gotcha #7, move them back first.** Do this before killing the server so a crash mid-shutdown doesn't strand the user's installed skills. Verify with `ls ~/.claude/skills ~/.claude/commands` that both are back in place.
2. Kill the manual-test server: `kill "$(cat /tmp/manual-test-server.pid)" && rm /tmp/manual-test-server.pid`.
3. Run `git status` and `git diff --stat docs/help/`. Report both to the user.
4. Summarize, grouped by doc file: what text changed and why (cite the source file and symbol — not line numbers, they rot), which images were reshot/added/deleted. **Open the report by stating which release ref was audited and its commit SHA** (captured in Precondition 2), e.g. "Audited against `release/sculptor-v0.27.0` at commit `a1b2c3d`." The user needs to know exactly what was measured.
5. **Stop.** Do not commit. Do not push. Do not open a PR. Let the user drive git from here.

## Final checklist

This is a repeat of the end-of-phase gates, consolidated. Every box must be ticked before reporting done — untick any box means loop back to the relevant phase.

**Preconditions:**

- [ ] Current branch is `release/sculptor-v<version>.0` (matches the version input).
- [ ] Commit SHA was recorded for the Phase 6 report.

**Phase 2 (audit):**

- [ ] Every `docs/help/**/*.md` file (plus the index at `docs/help/README.md`) has an audit table with per-claim VERIFIED/PARTIAL/WRONG/MISLEADING verdicts.
- [ ] Every non-VERIFIED row cites a source `file:line`.

**Phase 3 (rewrite):**

- [ ] Every claim changed in markdown has a source `file:line` backing it.
- [ ] `docs/help/README.md` reflects any page-level additions/removals.

**Phase 4 (screenshots):**

- [ ] Harness was launched with `--project-path /tmp/sculptor-demo/widget-store`.
- [ ] Workspace name is meaningful (not `default`, not `test`, not the prompt topic in snake-case).
- [ ] Viewport was 1920×1200.
- [ ] No banner in any reshot image shows `manual_test_repo` or the `testing` branch.
- [ ] Every image on the reshoot list was verified by a subagent against its 4.4 spec.

**Phase 5 (crop + process):**

- [ ] Every reshot image except the full-app overview (if any) has been cropped to satisfy the 5.1 rule (entire subject visible, natural UI boundaries, enough context to orient).
- [ ] For each crop, a subagent answered the 5.2 three-question verification (against the cropped intermediate in `$SCREENSHOTS_DIR`) with (a) YES, (b) NO, (c) YES — explicit, not qualified. Anything else triggered a recrop.
- [ ] No screenshot contains annotations (boxes, arrows, dim, labels).
- [ ] `process-screenshots.py` was run for each verified crop and the padded result was written to `docs/help/images/<name>.png`.
- [ ] Every `![…](images/<name>.png)` in markdown resolves to an existing file under `docs/help/images/`.
- [ ] No orphaned images in `docs/help/images/` that aren't referenced from markdown (flag them in the report; don't silently delete).

**Phase 6 (shutdown):**

- [ ] Manual-test server is shut down; pidfile is gone.
- [ ] No commits were created; no pushes were made.
- [ ] Final report opens with the audited ref and commit SHA, and includes `git status` + `git diff --stat` for `docs/help/`.
