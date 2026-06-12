---
name: write-release-notes
description: |
  Summarize commits merged to origin/main as two outputs: internal release
  notes (categorized into Features, UI Polish, Testing, CI, Cleanup) and
  user-facing release notes (What's new, Improvements, Reliability).
  Two input modes: a Sculptor release version (e.g., "0.27") for
  single-release notes, or a date range (e.g., "Feb 14-23") for ad-hoc weekly
  notes. Defaults to the last 7 days.
argument-hint: [release-version | date-range]
---

# Write Release Notes

Produce a concise summary of work merged to `origin/main`. Two modes:

- **Release mode** — summarize one Sculptor release (commits between the prior release tag and this release's tag or branch). Use when cutting or promoting a release.
- **Date-range mode** — summarize work landed in a date window. Use for weekly status updates.

In both modes, produce **two outputs in the same message**:

1. **Internal release notes** — the full categorized breakdown (Features, UI Polish, Testing, CI, Cleanup). For engineers and the team.
2. **User-facing release notes** — a shorter, curated view (What's new, Improvements, Reliability) scoped to changes a typical user will notice.

The user-facing view is derived from the internal one by filtering and regrouping; it is not a separate analysis pass.

## Input

Argument: $ARGUMENTS

Mode detection:
- If the argument matches `\d+\.\d+(\.\d+)?` (optionally prefixed with `v`), treat it as a **release version**. Examples: `0.27`, `0.27.0`, `v0.27`.
- Otherwise, treat it as a **date range**.
- If no argument is provided, default to **date-range mode** with the **last 7 days** (relative to today's date).

## Step 1: Resolve the commit range

### Release mode

Normalize the version to `X.Y.0` (e.g., `0.27` → `0.27.0`).

Fetch tags first:

```bash
git fetch origin --tags --quiet
```

**Endpoint** (tip of this release):
- If `sculptor-v{X.Y.0}` tag exists, use it (release was promoted).
- Else if `origin/release/sculptor-v{X.Y.0}` branch exists, use that (release is still in flight on RCs).
- Else, abort and tell the user the release hasn't been cut yet.

```bash
git rev-parse --verify sculptor-v{X.Y.0} 2>/dev/null \
  || git rev-parse --verify origin/release/sculptor-v{X.Y.0} 2>/dev/null
```

**Start point** (prior release tag, exclusive):

```bash
git tag -l 'sculptor-v*' | grep -v rc | sort -V
```

Pick the highest tag whose version is **strictly less** than `X.Y.0`. That's the prior release. Don't assume `X.Y-1` — version numbers can skip (e.g., 0.18 → 0.20, 0.22 → 0.24).

The range is `<prev_tag>..<endpoint>`. Example for 0.27 in flight: `sculptor-v0.26.0..origin/release/sculptor-v0.27.0`.

### Date-range mode

Parse the argument into a start date and end date (both inclusive). Examples:

- `Feb 14-23` means Feb 14 through Feb 23
- `Feb 14 - Feb 23` means Feb 14 through Feb 23
- `last 7 days` means 7 days ago through today
- `last week` means 7 days ago through today
- `2026-02-14 2026-02-23` means Feb 14 through Feb 23

If the input is ambiguous, ask the user to clarify.

## Step 2: Fetch merge commits

What matters for release notes is when work **landed on main** (became available to users), not when the developer authored the commits. Use merge commits to determine this, since this repo uses a no-fast-forward merge strategy — every MR creates a merge commit.

### Release mode

```bash
git fetch origin --quiet
git log <prev_tag>..<endpoint> --merges --first-parent --format="%h %s"
```

`--first-parent` follows only the main / release-branch spine, so you get exactly the MR-level merge commits that landed (no internal merges from inside any single MR's history).

Then, to get individual commits for context (needed for categorization):

```bash
git log <prev_tag>..<endpoint> --no-merges --format="%h %s"
```

### Date-range mode

```bash
git fetch origin main --quiet
git log origin/main --merges --after="<start-date>T00:00:00" --before="<end-date>T23:59:59" --format="%h %s"
```

Use the actual start and end dates with explicit times — `T00:00:00` for the start and `T23:59:59` for the end — so the range is inclusive on both sides. Do NOT use the "offset by one day" trick with date-only strings; git's approxidate parser handles bare dates inconsistently and will include commits outside the intended range.

For merge commits, the author date equals the merge time, so `--after`/`--before` filtering is accurate.

Then, to get the detailed individual commits for each MR (needed for categorization), run:

```bash
git log origin/main --no-merges --after="<start-date>T00:00:00" --before="<end-date>T23:59:59" --format="%h %s"
```

### Source-of-truth rule (both modes)

Use the **merge commit list** as the source of truth for what's included — if individual commits appear in the `--no-merges` output but their MR's merge commit is outside the chosen range, exclude them. Conversely, if a merge commit is in range but some of its individual commits have author dates outside the range, still include that work.

If the output is very large, save it to a temporary file and read it with the Read tool.

## Step 3: Categorize commits

Read every commit message and sort each commit into exactly one of these categories:

### Features
New user-facing capabilities, new API endpoints, new UI components, new backend services, new integrations. A feature is something that **adds functionality that didn't exist before**.

### UI Polish
Bug fixes, visual tweaks, UX improvements, performance optimizations, and behavioral fixes to **existing** features. If a commit fixes, polishes, or improves something that already existed, it goes here — not in Features.

### Testing
New test suites, test infrastructure, test migration, flaky test fixes, regression tests, test utilities, test skills. Anything whose primary purpose is **improving test coverage or test reliability**.

### CI
CI pipeline changes, build system changes, CI job additions/removals, CI worker configuration, CI-specific fixes.

### Cleanup
Dead code removal, refactoring with no behavior change, dependency removal, code quality sweeps, migration cleanup, removing deprecated features.

### Categorization guidelines

- A commit that adds a **new feature AND its tests** goes in Features (the tests are part of the feature).
- A commit that adds tests for an **existing** feature goes in Testing.
- New test infrastructure, test tooling, or test frameworks go in Testing — even if built from scratch — because their purpose is testing, not user-facing functionality.
- A commit that fixes a bug goes in UI Polish, not Features.
- A commit that removes a feature entirely goes in Cleanup.
- Design docs and implementation plans go in Features (they're part of a feature's delivery).
- If a commit truly doesn't fit any category, include it in the closest match.

## Step 4: Consolidate and summarize

Within each category, **group related commits into single line items**. For example, 15 commits for "Cmd+F Chat Search" become one bullet point, not 15.

**Sort items within each category by significance** — most impactful first. Rank by a mix of: (a) how many users it affects daily, (b) whether it's a new capability vs. an incremental improvement, and (c) architectural significance. User-facing workflow changes rank above infrastructure; foundational-but-invisible work ranks last.

Each bullet point must be:
- **10 words or fewer**
- Formatted as: `• *Label:* concise description`
- The label is a short feature/area name (2-4 words)
- The description completes the thought

Good example:
```
• *Cmd+F Chat Search:* In-chat find with highlighting, navigation, and scroll
```

Bad example (too long):
```
• *Cmd+F Chat Search:* Implemented in-chat find functionality with CSS Custom Highlight API for match rendering, next/prev navigation with scroll-to-match, auto-expand of collapsed tool calls, and extensive polish
```

## Step 5: Build the user-facing view

The user-facing view is a **curated subset** of the internal list, regrouped into three sections. Start from the internal categories you already produced — don't re-analyze the commits.

### Sections

**What's new**
Genuinely new capabilities or new default behaviors — things users couldn't do before, or that they now do differently by default. Usually 0–2 bullets per release. Omit the section if nothing qualifies.

**Improvements**
Polish to features that already worked: visible UX wins, performance, clearer interactions, richer rendering. The thing existed; it's now better.

**Reliability**
Bug fixes, stability work, and error-path improvements. Anything that fixes broken behavior. Include both stability work users will perceive (retries, clearer errors on transient failures) and visible defects (incorrect counts, sort order, dark-mode flashes) that now render correctly.

### Filter rules

Include an item only if a typical user — not a developer or maintainer — would plausibly notice. **Exclude**:

- Developer-only tools (devtools panels, in-app debug helpers)
- Internal observability / telemetry (PostHog events, Sentry instrumentation)
- Environment-variable knobs and other unsurfaced configuration (env vars are almost never user-facing — they exist for internal dev or escape-hatch use, not as documented product features)
- Tests, CI, build infrastructure
- Refactors and cleanup with no visible behavior change
- Accessibility tweaks (unless a major a11y initiative for the release)
- Backend internal stability with no user-perceptible effect (subprocess leaks, race fixes deep in the harness)

When uncertain, **exclude** — the user-facing list should feel curated, not exhaustive.

Keep the user-facing view **public-safe**: no real people's names, internal hostnames/service/tool names, or customer data — it is world-readable. (The internal notes may keep team-facing detail.) Same scrubbing as CLAUDE.md's "Public Visibility" section.

### Mapping from internal categories

- Internal **Features** → user-facing **What's new** (only if genuinely new to users; dev-only features are excluded entirely).
- Internal **UI Polish** → split between **Improvements** (things that already worked and are now better) and **Reliability** (visible defects, incorrect behavior, error-path bugs that are now fixed).
- Internal **Testing / CI / Cleanup** → excluded from the user-facing view unless something there has a direct user impact worth flagging.

Visible bug fixes that look like polish (e.g., a flash on load, wrong sort order, doubled counters) go in **Reliability**, not Improvements — the defect existed and now it doesn't.

Same formatting rules apply: ≤10 words per bullet, `• *Label:* description`, sorted by user impact within each section.

## Step 6: Output format

Output **both** reports in the same message, each in its own code fence, **internal first, then user-facing**. Use Slack-compatible formatting throughout: `*text*` for bold (single asterisks), `•` for bullet points, no heading syntax — just bold the section names.

### Internal release notes

```
*Internal release notes for <title>*

*Features*
• *Label:* concise description

*UI Polish*
• *Label:* concise description

*Testing*
• *Label:* concise description

*CI*
• *Label:* concise description

*Cleanup*
• *Label:* concise description
```

### User-facing release notes

```
*<title heading>*

*What's new*
• *Label:* concise description

*Improvements*
• *Label:* concise description

*Reliability*
• *Label:* concise description
```

### Titles

Internal title:
- **Release mode** — `*Internal release notes for v0.27*` (use major.minor only, no patch suffix).
- **Date-range mode** — `*Internal release notes for <human-readable date range>*` (e.g., `Feb 14–23`).

User-facing title:
- **Release mode** — `*Sculptor v0.27*`.
- **Date-range mode** — `*Sculptor <human-readable date range>*`.

Omit any section that has zero items in either output.

## Do not

- Include commit hashes in the output
- Exceed 10 words per bullet point
- Create a bullet point for every individual commit — always consolidate related work
- Include a section header if it has no items
- Pad the user-facing view with internal-only items just to fill a section
- Repeat the user-facing view verbatim — it's a curated subset, not a copy
