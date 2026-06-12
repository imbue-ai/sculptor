---
name: fix-bug
description: Fix a bug using test-driven development.
when_to_use: |
  Invoke when the user describes a bug, pastes an error, or references a bug ticket ID.
  Input: a description of the bug to fix, or a bug ticket ID. Prefix the input
  with `--autonomous` to run end-to-end with no user questions, hypothesis
  exploration, and (if the repo's config allows it) automatic publishing.
  The workflow enforces TDD — write a failing test first, then fix the code, then verify.
  Prefer this skill over ad-hoc bug fixes whenever the bug can be expressed as a
  reproducible test.
---

# Fix Bug (Test-Driven)

Fix a bug using a strict TDD workflow: understand the bug, prove it with a
failing test, fix the code, verify.

This skill has **two modes**:

- **Interactive (default):** ask the user whenever the bug is unclear, confirm
  understanding before writing any code, confirm test kind, etc.
- **Autonomous:** never ask the user. Explore the codebase, form hypotheses,
  classify the ticket into one of four outcomes (REPRODUCED / STALE /
  ALREADY-FIXED / UNREPRODUCIBLE), and act accordingly. For REPRODUCED:
  fix the proven bug(s), run a self-review pass, enumerate deferred-work
  follow-ups, then (if the repo's `.sculptor/code.md` Publishing Changes
  section permits it) push and open an MR/PR. For the other outcomes:
  report the outcome with evidence (via the testing config's ticket
  entry points if configured) and do NOT push. Triggered when the input
  begins with `--autonomous` (or `autonomous` as the first token).

Steps 1–3 below are shared by both modes. After Step 3, **autonomous mode jumps
to the "Autonomous Workflow" section near the end** of this file. Interactive
mode continues into Phase 1.

## Step 1: Load config (REQUIRED — do not skip)

**You MUST have all three config files before doing anything else.** Do not
proceed to any later step until all three files exist and you have read them.

Check for `.sculptor/code.md`, `.sculptor/testing.md`, and `.sculptor/docs.md`
in the repo root.

- If **any of the three files is missing**, immediately invoke the
  `/sculptor-workflow:setup-repo` skill via the Skill tool. Do NOT ask the
  user whether to run it first — just run it. Do NOT attempt to fix the bug
  without these files. Do NOT try to infer the information yourself — the
  setup skill exists specifically to gather this information correctly
  through conversation with the user.
- Once **all three files exist**, read them. Their contents drive every step
  below:
  - **`.sculptor/code.md`**: codebase structure, branch naming, build/run
    commands, pre-commit verification, publishing changes, proof-of-work
    standards
  - **`.sculptor/testing.md`**: test framework, test strategy, bug tracking
    (fetch / file / comment / state-change entry points), manual testing,
    visual verification
  - **`.sculptor/docs.md`**: in particular the `## Code Review` section,
    which names the skill that the post-fix review pass invokes (see Phase 4
    and Phase A4.5 below). If the section is empty or absent, the review
    pass is skipped — see "Code review fallback" notes inline.

## Step 2: Create a branch

Check the current branch with `git branch --show-current`.
- If the current branch is **not** the default branch, skip branch creation and
  work on the current branch.
- If the current branch **is** the default branch, create a new branch using
  the code config's **Branch Naming** convention. If the config has no
  branch naming section:
  - **Interactive mode:** use `mcp__sculptor__ask_user_question` to ask the user.
  - **Autonomous mode:** generate a reasonable slug from the bug description
    (lowercased, kebab-case, ticket ID prefix if present), e.g.
    `auto/bugs/SCU-123-login-crash` or `auto/bugs/login-crash`.

```bash
git checkout -b <branch-name>
```

## Step 3: Fetch bug ticket context

If the testing config has a **Bug Tracking** section, follow its instructions.
The config specifies:

- What bug ticket IDs look like (e.g. `SCU-123`, `PROJ-42`)
- Whether a ticket is always required, or only when the input matches the
  ticket ID format
- How to fetch the ticket's context (e.g. invoke a skill, call an API)

If the input matches the ticket ID format, fetch the ticket's title,
description, and comments, and use that context as the bug description for the
rest of the workflow.

If the config says a ticket is always required but no ticket ID was provided:
- **Interactive mode:** use `mcp__sculptor__ask_user_question` to ask for the
  ticket ID or whether they want to proceed without one.
- **Autonomous mode:** proceed without a ticket. Note in the final MR/PR body
  that no ticket was provided.

If the testing config has no **Bug Tracking** section, skip this step.

**If running in autonomous mode, jump now to the [Autonomous Workflow](#autonomous-workflow)
section.** The interactive Phase 1–4 below does not apply.

## Phase 1: Understand the Bug

Before writing any code, get full clarity on what is broken.

### Gather information

1. **Ask the user questions** using `mcp__sculptor__ask_user_question` if the description is
   vague or incomplete. Don't guess — ask about:
   - Exact steps to reproduce
   - What the user expected to happen
   - What actually happened (the buggy behavior)
   - Error messages, logs, or screenshots
   - Whether it's intermittent or consistent
   - Edge cases or interactions with other features

2. **Read the relevant source code** to understand how the feature currently
   works. Trace the code path to build a mental model of where the bug likely
   lives.

3. **Reproduce the bug** (if the testing config has a **Manual Testing**
   section). Follow the config's instructions to launch the app and visually
   confirm the bug. Take screenshots at each step — you will show them to the
   user in the confirmation step. If there are no manual testing instructions,
   skip visual reproduction.

### Decide what kind of test to write

Follow the testing config's **Test Strategy** section. The test strategy is
mandatory policy, not a suggestion — you MUST follow its rules about what kind
of test to write.

### Getting user confirmation (MANDATORY — you MUST stop here and wait)

Write out your understanding as a summary:

- What the current (buggy) behavior is, with repro steps
- What the desired (correct) behavior should be
- Whether this is behavioral or purely visual
- If behavioral: the **test kind** (e.g. e2e, backend unit, frontend
  unit) and the **test file path** where you plan to write the test, with a
  brief explanation of why you chose that kind and location based on the
  testing config's **Test Strategy**. Be explicit — do not leave the test kind
  implicit in the file path.

**If you reproduced the bug visually:** include the screenshots inline with
`<img>` tags. Walk the user through each screenshot, explaining what you did
and what you observed.

**You MUST use the `mcp__sculptor__ask_user_question` tool here** — do NOT use a plain text
message. The tool triggers a UI notification that grabs the user's attention.
Ask:
> "Does this match your understanding? Is the test location correct? Please
> confirm so I can proceed."

Then **STOP. Do not proceed to Phase 2. Do not write any code.** Wait for the
user's explicit response via the `mcp__sculptor__ask_user_question` tool result.

## Phase 2: Write a Failing Test

Write a test that asserts the **desired** (correct) behavior. Since the bug
hasn't been fixed yet, this test should **fail**.

### Lock in the Phase 1 commitment (MANDATORY — do not skip)

Before writing anything, restate the commitment from Phase 1 verbatim:

> "In Phase 1 I confirmed I would write a **\<test kind\>** test at
> **\<test file path\>**. I will write that exact test now."

**The test kind and file path are locked.** You MUST NOT re-read the testing
config's **Test Strategy** and re-derive the decision. The user already
confirmed it. Re-opening the decision here is the most common failure mode for
this skill — do not do it.

### If you hit an obstacle that seems to require deviating

If, while writing the test, you believe you need to change the test kind (e.g.
fall back from an end-to-end test to a unit test), you MUST stop and use
`mcp__sculptor__ask_user_question` before writing anything different. In the question:

- Name the **specific obstacle** you hit (e.g. "the bug only reproduces when
  \<X\>, and the end-to-end test framework cannot do \<Y\>"). "Difficult,"
  "slow," "flaky," or "inconvenient" are NOT valid obstacles — re-read the
  testing config's definition of when fallback is allowed.
- State the **new test kind and path** you are proposing.
- Wait for explicit user approval before writing the different test.

Do NOT decide to deviate on your own. Do NOT silently write a different kind
of test than what was confirmed.

### Writing the test

Follow the testing config's instructions for:
- Which test framework to use (for the locked-in test kind)
- What conventions to follow (naming, fixtures, setup)
- Whether to invoke a skill or write directly

If the config references a skill for writing tests of the locked-in kind,
invoke that skill. If not, read an existing test file in the repo as a
reference and follow its patterns.

**Test design:**
- The test should exercise the exact scenario described by the user.
- Write assertions that would **pass once the bug is fixed** and **fail with
  the current buggy code**.
- Keep the test focused — test only the buggy behavior, not unrelated
  functionality.

### Confirm the test fails

Run the test using the testing config's test runner command (or skill).
Verify it **fails because of the bug**.

- If the test **passes**: it does not capture the bug — revise the assertions.
- If the test fails for an **unrelated reason** (setup, infrastructure): fix
  the test setup. If the config references a debugging skill, use it.

Once the test fails as expected, **commit the test file** with a message like:
`Add failing test for <bug description>`.

## Phase 3: Implement the Fix

Now implement the code change to make the test pass.

### STRICT RULE: Do NOT modify the test

**It is NOT ALLOWED to change the test file created in Phase 2.** The test is
the specification — the code must be changed to make the test pass, not the
other way around.

### Implementation workflow

1. **Implement the fix**: make the minimal code change needed.
2. **Run the test**: use the testing config's test runner.
3. **If the test still fails**: investigate and iterate on the implementation.
   If the config has a test debugging skill, use it.
4. **Repeat** steps 1-3 until the test passes.

### After the test passes

Run the code config's pre-commit verification commands. Fix any issues
introduced. Commit the implementation.

## Phase 4: Verification

### Visual verification (if manual testing is available)

If the testing config has a **Manual Testing** section:

1. Follow the config's instructions to launch the app.
2. Re-run the original repro steps and take screenshots.
3. If the config has **Visual Verification** instructions (e.g. annotating
   screenshots), follow them.
4. Show the "after" screenshots to the user alongside the "before" screenshots
   from Phase 1.

### Verification mode (read the testing config)

The testing config (`.sculptor/testing.md`) may specify rules about *how*
to verify particular classes of bugs — for example, which test harness
mode to use, whether real external services are required, or which kind
of evidence is mandatory. Re-read the testing config's **Test Strategy**
and **Manual Testing** sections now and apply any verification rules
that match this bug's class. Verification policy lives in the repo's
config, not in this skill.

### Self-review pass (REQUIRED — implementation isn't done until reviewed)

Run the code-review skill named in `.sculptor/docs.md`'s `## Code Review`
section against the diff produced by this fix.

- **If the section is missing or empty:** skip the review pass entirely
  (same fallback as `/sculptor-workflow:review`). Continue to "Final
  checks" below.
- **If the section names a skill** (e.g. `Skill: /code-review-checklist`):
  invoke that skill with:
  - Working directory: the repo root.
  - Diff range: `<merge base>...HEAD`.
  - Stated goal: a short summary of the bug and the intended behaviour
    (the same content you've been building in Phase 1).

  Read every finding. Use your judgement to decide which findings to act
  on (there's no severity rule — trust yourself). For each finding you
  decide to act on, fix it in a follow-up commit. Single pass — do not
  re-run the review after fixing. Print the remaining findings (those you
  declined to act on) at the end of Phase 4 so the user can see them.

The implementation is not considered complete until this review pass has
run.

### Final checks

1. Ensure all pre-commit verification commands from the code config pass.
2. Ensure all unit tests pass (if the code config specifies a unit test command).
3. Confirm the implementation is committed.

## Summary Checklist

### All bug fixes

- [ ] All three config files (`.sculptor/code.md`, `.sculptor/testing.md`,
      `.sculptor/docs.md`) loaded (or created via setup)
- [ ] Bug understood: current behavior, expected behavior, and repro steps
- [ ] User confirmed understanding before any code was written
- [ ] Failing test written and committed (for behavioral bugs)
- [ ] Test confirmed to fail before the fix
- [ ] Fix implemented — test now passes
- [ ] Test file was NOT modified during the fix
- [ ] Pre-commit verification commands pass
- [ ] Fix committed
- [ ] Phase 4 self-review pass ran (or was skipped only because
      `.sculptor/docs.md` has no `## Code Review` section); findings the
      agent declined to act on were printed to the user

### Visual verification (if manual testing available)

- [ ] Bug reproduced with screenshots before the fix
- [ ] Screenshots taken after the fix showing correct behavior
- [ ] Before/after screenshots shown to the user
- [ ] Any verification rules in the testing config that apply to this
      bug's class were followed

## Autonomous Workflow

Enter this workflow only when the input began with `--autonomous` (or
`autonomous` as the first token). Steps 1–3 above have already run.

### Forbidden in autonomous mode

- **No `mcp__sculptor__ask_user_question` calls.** Not for clarification, not
  for confirmation, not for fallback approval, not ever.
- **No waiting on the user.** Don't ask "should I proceed?" — proceed.
- **No fabricated bugs.** If you cannot reproduce any plausible interpretation
  of the user's description with a real failing test, classify the outcome
  as STALE, ALREADY-FIXED, or UNREPRODUCIBLE per the "Ticket outcomes"
  section below and take the corresponding branch. **Do not invent a bug
  to fix.** Trying to fix every ticket at all costs is the failure mode
  that pattern was added to prevent.
- **No editing the test after the fix begins.** Same STRICT rule as Phase 3 in
  the interactive workflow.
- **No skipping the test-strategy criteria.** The `.sculptor/testing.md` rules
  for when a non-end-to-end test is allowed still apply. In autonomous mode
  you make that decision yourself (no user gate), but the criteria are
  unchanged. Document the test-kind choice for each bug in the final MR/PR
  body so a reviewer can sanity-check it.
- **No thin MR/PR bodies.** "Fixed the bug" with no detail is forbidden. The
  body is the reviewer's only context — see the "Required output" block below.
- **No skipping evidence capture on cost or convenience grounds.** Running
  the testing config's **Manual Testing** flow twice (once in A2 to
  reproduce, once in A4 to verify the fix) is a fixed cost of this
  workflow, not optional. "Too slow," "too expensive," "the failing test
  output already proves it," "the fix is obvious," and "I'll add screenshots
  later" are NOT valid reasons. For any bug you reproduce through the UI in
  A2, before and after screenshots are mandatory artifacts in the MR/PR body
  and cannot be replaced by test output.

### Required output: a comprehensive MR/PR body

The success bar for autonomous mode is **a reviewer can approve the MR/PR
without re-running the repro themselves.** That requires:

- A **detailed prose description** of the repro (exact steps, environment,
  expected vs actual), the hypothesis, and the fix (what changed and why).
- **Proof of work** matching the standard in `.sculptor/code.md`'s `## Proof of
  Work` section — typically before/after screenshots for UI-visible bugs,
  failing-then-passing test output for the rest. Capture this evidence **as
  you go** in Phases A2 and A4 (instructions inline below). Do not try to
  reconstruct screenshots at the end.

Treat A1–A4 as actively building the MR/PR body. Keep an "evidence log" in
your working notes — for each hypothesis: the repro attempt, screenshots
taken (with file paths), the test file path, what the test output looked like
before the fix and after.

### Ticket outcomes (read before A1 — this is the decision tree)

Autonomous mode MUST recognize that not every ticket is a "fix this code"
ticket. After Phase A1 + A2 (investigate, form hypotheses, attempt repro),
the agent classifies the ticket into exactly one of four outcomes:

1. **REPRODUCED** — at least one hypothesis was reproduced with a real
   failing test. Proceed to A3 → A4 → A4.5 → A5 (the existing flow).
2. **STALE** — the described symptom does not manifest on the current
   `main`. The bug appears to have resolved itself (perhaps via an
   unrelated commit). Skip the fix flow. Take the "STALE" branch under
   Phase A5.
3. **ALREADY-FIXED** — investigation surfaces an existing commit or MR
   on `main` that already addresses the bug. Skip the fix flow. Take the
   "ALREADY-FIXED" branch under Phase A5.
4. **UNREPRODUCIBLE** — the description is too ambiguous to form a
   grounded hypothesis, or every hypothesis the agent formed was
   discarded after attempting repro. Skip the fix flow. Take the
   "UNREPRODUCIBLE" branch under Phase A5.

**Crucial rule:** if the outcome is anything other than REPRODUCED, the
agent MUST NOT push a branch, open an MR, or commit a speculative fix.
**Do not invent a bug to fix.** Trying to fix the bug at all costs — when
the right answer is to say "this is stale" or "I can't reproduce this" —
is the failure mode this section exists to prevent.

Trust the outcome decision. A clean STALE / ALREADY-FIXED / UNREPRODUCIBLE
outcome is a successful run, not a failed one.

### Phase A1: Investigate and form hypotheses

1. **Re-read the bug input** (plus ticket context, if any was fetched in Step 3).
2. **Check whether the bug is already fixed.** Search `git log --oneline -200`
   and grep the codebase for recent changes that could plausibly address the
   bug (commits mentioning the same files, symptoms, or ticket ID). If you
   find one, plan to verify in A2 — if the symptom no longer reproduces on
   `main`, the outcome is **ALREADY-FIXED**.
3. **Explore the codebase** to find the code path(s) the description could
   plausibly refer to. Use Grep, Glob, and Read. If the testing config has a
   **Manual Testing** section, follow its instructions to poke at the live
   UI to narrow down where the bug surfaces.
4. **List concrete hypotheses.** Each hypothesis must name:
   - The specific user-visible behavior that would be wrong
   - The code path / file / function likely responsible
   - How a test could distinguish "bug present" from "bug fixed"
5. **Cap the list.** Carry at most 3 hypotheses forward. If you have more,
   keep the 3 best-supported by code evidence and drop the rest.

   If the description is so vague that you can't form even one grounded
   hypothesis: the outcome is **UNREPRODUCIBLE**. Stop here, skip A2–A4, and
   take the UNREPRODUCIBLE branch under Phase A5.

Save your hypothesis list (titles + one-line summaries) — you'll quote it in
the final MR/PR body, or in the ticket comment if the outcome is not
REPRODUCED.

### Phase A2: Reproduce each hypothesis with a real test

For each hypothesis, in order:

1. **Try to reproduce the bug through the UI** by following the testing
   config's **Manual Testing** section (if present). Drive the UI to the
   buggy state, then take a **before-screenshot** and save it under the
   workspace attachments directory (e.g.
   `attachments/screenshots/bug-<slug>-before.png`). This screenshot is a
   **required artifact** in the final MR/PR body — capturing it now is not
   optional, and the failing-test output you save in step 3 does not
   substitute for it. Record the exact repro steps you used — every click,
   input, and navigation — in your evidence log; they go into the MR/PR
   body verbatim. If the bug does not reproduce, **discard the hypothesis**
   and note in the evidence log what you tried and what you observed
   instead. Move on.
2. **Write a failing test** that asserts the desired behavior, following
   the testing config's **Test Strategy**:
   - Default to an end-to-end test. If the testing config's **Test
     Writing** section references a skill, invoke it; otherwise read an
     existing end-to-end test in the repo and follow its patterns.
   - Fall back to a unit test only if the test strategy's "impossible"
     criteria genuinely apply. In autonomous mode you do not have a user gate,
     but you MUST cite the specific criterion in the MR/PR body. "Difficult"
     or "inconvenient" is not a valid reason — discard the hypothesis instead.
3. **Run the test** following the testing config's **Test Framework**
   section (use whatever runner or skill it references for running e2e
   tests) and confirm it fails for the right reason. Save the failing test output
   (stdout + stderr, or at least the failing assertion and traceback) to
   your evidence log — it goes in the MR/PR body. If the test passes, it
   does not capture a real bug — discard the hypothesis.
4. **If the test fails for an unrelated reason** (setup / infrastructure):
   fix the setup. If the testing config has a **Test Debugging** section,
   follow it. Do not give up on a hypothesis just because the test harness
   misbehaved.

At the end of Phase A2 you have a set (possibly empty, possibly one, possibly
several) of **proven** bugs, each with a failing test, a before-screenshot
(if UI-visible), and saved failing-test output.

**Outcome decision after A2:**
- **Proven bug set non-empty** → outcome is **REPRODUCED**. Proceed to A3.
- **Proven bug set empty AND** you found evidence on `main` that an existing
  commit/MR addresses the bug → outcome is **ALREADY-FIXED**. Skip A3–A4.5;
  take the ALREADY-FIXED branch under Phase A5.
- **Proven bug set empty AND** the symptom does not manifest at all on
  `main` (no existing fix found either) → outcome is **STALE**. Skip
  A3–A4.5; take the STALE branch under Phase A5.
- **Proven bug set empty AND** the description was too vague to drive
  reproduction → outcome is **UNREPRODUCIBLE**. Skip A3–A4.5; take the
  UNREPRODUCIBLE branch under Phase A5.

Do not push, commit fixes, or open an MR in any non-REPRODUCED outcome.
Do not invent a bug to fix.

### Phase A3: Commit the failing tests

For each proven bug, commit its failing test on its own:

```bash
git add <test file>
git commit -m "Add failing test for <one-line bug description>"
```

One test per commit keeps the history easy to review and lets a human bisect
later.

### Phase A4: Fix each proven bug

For each proven bug, in order:

1. Implement the **minimal** code change to make the test pass.
2. Run the test. Iterate the implementation (not the test) until it passes.
   Save the passing test output to the evidence log alongside the failing
   output from Phase A2 — the before-and-after pair is what proves the fix.
3. Run any sibling tests in the same area to catch regressions.
4. **Re-run the manual repro** from Phase A2 against the fixed code via the
   testing config's **Manual Testing** section, and take an
   **after-screenshot** (e.g. `attachments/screenshots/bug-<slug>-after.png`).
   **If A2 captured a before-screenshot for this hypothesis, you MUST
   capture a matching after-screenshot.** There is no exception, including
   "the test already passes," "this would take too long," or "the fix is
   obvious." If the difference is subtle, annotate the after-screenshot
   using the testing config's **Visual Verification** section. Only skip
   this step if A2 did not use the UI to reproduce (i.e. the bug genuinely
   has no UI surface).

   **Exercise the full user flow, not just the narrow symptom.** If the
   ticket describes a multi-step flow, drive the entire flow end-to-end
   and confirm the whole thing works — don't just confirm the literal
   symptom is gone. Reviewers will reject "this one moment is fixed but
   the broader flow is still broken."

   **Verification mode:** re-read the testing config's **Test Strategy**
   and **Manual Testing** sections and apply any rules they specify
   about how to verify this class of bug (e.g. which harness mode,
   whether real external services are required, what evidence is
   mandatory). Verification policy lives in the repo's config — defer
   to it rather than guessing.
5. Commit the fix on its own:
   ```bash
   git add <fix files>
   git commit -m "Fix <one-line bug description>"
   ```

**The test files from Phase A3 are locked.** Do not modify them during A4.

### Phase A4.5: Self-review pass (REQUIRED — implementation isn't done until reviewed)

After all proven bugs have been fixed in A4, run the code-review skill
named in `.sculptor/docs.md`'s `## Code Review` section against the diff
this run has produced.

- **If the section is missing or empty:** skip the review pass entirely
  (same fallback as `/sculptor-workflow:review`). Proceed to A5.
- **If the section names a skill** (e.g. `Skill: /code-review-checklist`):
  invoke that skill with:
  - Working directory: the repo root.
  - Diff range: `<merge base>...HEAD`.
  - Stated goal: the assembled MR body draft (root cause, fix, repro,
    proof) you will publish in A5 — pass the actual draft, not just the
    bug description. The review skill needs the body to evaluate "Proof of
    work completeness" and "Consistency with stated goal."

  Read every finding. Use your judgement to decide which findings to act
  on — there's no severity-based rule, trust yourself. For each finding
  you decide to act on, fix it in a follow-up commit. **Single pass — do
  not re-run the review after fixing.**

  Any findings you declined to act on MUST be appended to the MR body in
  a `## Review notes` section so the human reviewer can see them and
  decide whether to push back.

### Phase A5: Verify and publish (REPRODUCED outcome only)

This phase only runs when the outcome from A2 is REPRODUCED. The STALE,
ALREADY-FIXED, and UNREPRODUCIBLE branches are below.

1. Run the code config's **Pre-commit Verification** commands. Fix anything
   they flag and amend or add a follow-up commit.
2. **Enumerate deferred-work follow-ups.** If during A1–A4.5 you
   consciously deferred any adjacent work (related bugs, refactors,
   follow-up improvements), enumerate them in a `## Deferred follow-ups`
   section of the MR body draft. If you deferred nothing, omit the
   section entirely.

   - **If the testing config has a "How to file new tickets" entry
     point:** file a tracker ticket for each item via that entry point
     and link the ticket URL next to the item. The repo's config
     opting into this entry point signals the team wants deferred work
     formally tracked; do not publish with un-tracked items in that case.
   - **If the testing config has no "How to file new tickets" entry
     point:** just list the items as bullets so a reviewer can act on
     them. Do not attempt to file tickets — the repo hasn't configured
     one.
3. Read the `## Publishing Changes` section of `.sculptor/code.md`.
   - **If the section is missing**, or **`Auto-publish allowed`** is `no` or
     ambiguous: stop here. Print a summary of the commits made and tell the
     user to publish manually (and to re-run `/setup-repo` if they want this
     automated next time). Do not push.
   - **If `Auto-publish allowed` is `yes`**: run the **Push command**
     verbatim, then run the **Create MR/PR (base command)** with the title
     (step 4) and body (step 5) appended as runtime flags.
4. **MR/PR title**: write one imperative line summarizing the primary fix,
   ≤ 70 characters (e.g. "Fix login crash when token contains a colon").
   If multiple bugs were fixed, summarize the most impactful one and rely
   on the body to enumerate the rest. Do NOT prefix with `Draft:` /
   `[WIP]` — draft state is controlled by the `--draft` flag in the base
   command, not the title.
5. **MR/PR body**: write a detailed, reviewer-ready description.

   First, **re-read `.sculptor/code.md`'s `## Proof of Work` section** to
   confirm the team's evidence standard, then assemble the body using the
   template below. The body is the reviewer's only context — vague,
   one-line, or "fixed the bug" bodies are not acceptable.

   Pass the title and body to the base command at runtime via flags. For
   `glab mr create`: append `--title "<title>" --description "<body>"`
   (for a large body, write it to a file first and pass it as
   `--description "$(cat <path>)"` — glab does not have a `--description-file`
   flag). For `gh pr create`: append `--title "<title>" --body "<body>"`
   (or `--body-file <path>`). Never use `--fill` — it would discard the body.

   **Required template** (use these exact section headings):

   ```
   ## Original bug
   <verbatim quote of the user's bug description, plus ticket link if any>

   ## Hypotheses considered
   <numbered list of every hypothesis from Phase A1, each annotated
   "REPRODUCED" or "DISCARDED — <one-line reason>">

   ## For each reproduced bug

   ### <one-line bug title>

   **Repro steps**
   <numbered, exact steps from the evidence log — every click, input,
   navigation, command, or fixture used to trigger the bug>

   **Expected vs actual**
   - Expected: <what should happen>
   - Actual: <what happens today>

   **Before**
   <If A2 captured a before-screenshot for this bug, embed it here. **Do
   not substitute test output** — the failing-test output is documented
   in the Test block above. If the bug has no UI surface and A2 did not
   take a screenshot, paste the saved failing-test output here in a
   fenced code block instead.>

   **Root cause**
   <several sentences explaining the code path responsible and why it
   produces the buggy behavior; reference specific files and functions>

   **Fix**
   <several sentences explaining what changed and why it addresses the
   cause; if there were obvious alternatives, briefly say why this one>

   **Test**
   - Path: `<test file>`
   - Kind: <e2e | unit> (if unit, cite the "impossible" criterion)
   - Failing-test commit: `<hash>`
   - Fix commit: `<hash>`

   **After**
   <If A4 captured an after-screenshot for this bug, embed it here. **Do
   not substitute test output.** If the bug has no UI surface and A4 did
   not take a screenshot, paste the saved passing-test output here in a
   fenced code block instead.>
   ```

   For multiple reproduced bugs, repeat the `### <bug title>` block.

   Reject your own draft if it contains any of:
   - "fixed the bug" without detail
   - A Before or After slot containing test output, prose, or anything
     other than the embedded screenshot when A2 / A4 captured one for
     that bug
   - A screenshot section with no actual screenshot
   - A Test block missing the commit hashes
   - A Root cause or Fix block under two sentences

   Rewrite before posting. If you catch yourself thinking "the screenshot
   isn't worth the time" or "the test output is enough proof," that is
   exactly the rationalization the autonomous mode is designed to reject —
   go back and capture the screenshot.

   **Review notes:** if Phase A4.5 left any findings you declined to act
   on, append them as a final `## Review notes` section. One bullet per
   finding, with the file/line reference. This is required even if the
   list is empty — write `_(no outstanding review notes)_` so a reviewer
   knows the review pass ran.
6. Print the resulting MR/PR URL.

#### STALE / ALREADY-FIXED / UNREPRODUCIBLE branches (non-REPRODUCED outcomes)

Take this branch when Phase A2 concluded the outcome is anything other
than REPRODUCED. **Do not push a branch, open an MR, or commit any
speculative fix.** The agent must NOT invent a bug.

For all three outcomes, follow these steps:

1. **Capture evidence.** Save the screenshots / logs / test output / git
   log entries showing what you tried and what you observed.
2. **Report the outcome.** How depends on the testing config:
   - **If the testing config has a "How to comment on tickets" entry
     point and a ticket ID is available:** post a comment on the
     ticket via that entry point using one of the templates below.
   - **Otherwise** (no entry point, or no ticket): print the same
     outcome summary to the caller as the run's final output. The
     summary still goes somewhere a human can see it; it just doesn't
     get auto-posted.
3. **For UNREPRODUCIBLE only**, if the testing config has BOTH a "How
   to change ticket state" entry point AND a configured "Needs-info
   state name", AND a ticket ID is available: change the ticket's
   state to that configured state via that entry point. If either is
   missing, skip the state change.
4. **Exit.** Do not push, do not open an MR. Print a one-line summary of
   the outcome so the caller (interactive user or scheduling system)
   knows the run is complete.

**Comment templates:**

For **STALE**:
```
**Outcome: stale** — autonomous fix-bug run on <commit-sha>

I attempted to reproduce this bug on `main` (<commit-sha>) and could not.
The symptom no longer appears to manifest. The bug may have been resolved
incidentally by an unrelated change.

What I tried:
- <bullet list of repro attempts and what was observed>

If you can still reproduce this, please add updated repro steps so I can
investigate further.
```

For **ALREADY-FIXED**:
```
**Outcome: already fixed** — autonomous fix-bug run on <commit-sha>

I found an existing fix on `main` that appears to address this:

- Commit: <hash-or-MR-link>
- Behaviour change: <one-line summary>

Walking the original repro against the current code shows the described
behaviour no longer occurs. Recommend closing this ticket.

What I tried:
- <bullet list of repro attempts and what was observed>
```

For **UNREPRODUCIBLE**:
```
**Outcome: unreproducible** — autonomous fix-bug run on <commit-sha>

I attempted to reproduce this bug but could not narrow it down from the
description. <Only include the next sentence if the state change in step 3
actually ran:> Moving the ticket to the configured "needs info" state so
the reporter can clarify.

What I tried:
- <bullet list of hypotheses considered, repro attempts, and observations>

To make this fixable, please add:
- Exact steps to reproduce (every click, input, navigation)
- Environment details (OS, app version, anything else relevant to the repro)
- Screenshots or logs showing the buggy state
- Whether it reproduces consistently or intermittently
```

These outcomes are successful runs, not failures. They preserve trust in
autonomous mode by guaranteeing the agent never fabricates a bug to fix.

## Autonomous Summary Checklist

### Always (regardless of outcome)

- [ ] Input began with `--autonomous` / `autonomous`; no user questions were asked
- [ ] All three config files (`.sculptor/code.md`, `.sculptor/testing.md`,
      `.sculptor/docs.md`) were loaded before any other action
- [ ] A ticket outcome was explicitly chosen (REPRODUCED / STALE /
      ALREADY-FIXED / UNREPRODUCIBLE) and the corresponding branch was
      followed — no speculative fix was committed

### REPRODUCED outcome

- [ ] At least one concrete, code-grounded hypothesis was formed
- [ ] Each carried-forward hypothesis was reproduced with a real failing test
      (not assumed, not a placeholder)
- [ ] Before-evidence captured during A2 (screenshot for UI bugs, saved
      failing-test output for non-UI)
- [ ] Failing tests were committed before any fix code was written
- [ ] Each fix is the minimal change needed to make its test pass
- [ ] After-evidence captured during A4 (screenshot for UI bugs, saved
      passing-test output for non-UI)
- [ ] Full user flow exercised in A4 — not just the narrow symptom
- [ ] Any verification rules in the testing config that apply to this
      bug's class were followed in A4
- [ ] Test files were not modified during the fix phase
- [ ] Phase A4.5 self-review pass ran (or was skipped only because
      `.sculptor/docs.md` has no `## Code Review` section)
- [ ] Findings from A4.5 either fixed in follow-up commits or recorded in
      the MR body's `## Review notes` section
- [ ] Deferred-work follow-ups (if any) enumerated in the MR body's
      `## Deferred follow-ups` section; if the testing config has a
      "How to file new tickets" entry point, each item also has a
      tracker URL
- [ ] Pre-commit verification commands pass
- [ ] Publishing followed `.sculptor/code.md`'s **Publishing Changes** section
      — pushed and opened MR/PR only if `Auto-publish allowed: yes`
- [ ] MR/PR title was composed by the agent (imperative, ≤ 70 chars), not
      auto-filled from a commit message
- [ ] MR/PR body was composed by the agent via `--description` / `--body`
      (or equivalent), not `--fill`
- [ ] MR/PR body follows the required template — every hypothesis annotated
      REPRODUCED/DISCARDED, every reproduced bug has repro steps, before
      and after evidence, root cause, fix, and test commit hashes
- [ ] MR/PR body would let a reviewer approve without re-running the repro

### STALE / ALREADY-FIXED / UNREPRODUCIBLE outcomes

- [ ] No branch was pushed; no MR/PR was opened; no speculative fix committed
- [ ] Evidence of the attempt (hypotheses, repro attempts, observations)
      was captured
- [ ] The outcome was reported per the testing config — comment posted
      via the configured "How to comment on tickets" entry point if
      one exists and a ticket ID is available; otherwise the summary
      was printed to the caller
- [ ] For UNREPRODUCIBLE: ticket moved to the configured "Needs-info
      state name" via the "How to change ticket state" entry point —
      but only if both are configured and a ticket ID is available
