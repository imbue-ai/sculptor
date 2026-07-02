# Task 99.2: Launch the Review agent

## Goal

Spawn `/sculptor-workflow:review` in a new agent tab so the Review agent can verify
requirements coverage, re-run the test suite, and invoke the repo's code-review skill.
This is the final task in the plan.

## Background

This is the last task in the plan. Every feature task is complete and committed; the
verification task before this one (Task 99.1) confirmed all tests pass. The Review
agent reads the design docs, plan, and the diff to produce `review.md`.

This plan used the `agent_docs/ui_refresh/` document set in place of a single
spec/architecture, so seed the Review agent with the relevant docs as the spec +
architecture inputs.

## Files to modify/create

None. This task spawns an agent; it does not edit code.

## Implementation details

1. Compute the diff range. Default: `origin/main...HEAD` (the default branch is `main`
   per `.sculptor/code.md`).
2. Spawn a new agent in the same workspace via the `/sculptor:sculpt-cli` skill,
   invoking `/sculptor-workflow:review` there. Seed it with:
   - `Slug:` `ui_refresh`
   - `Spec path:` `agent_docs/ui_refresh/goals.md` (behavior source of truth; also
     point it at `agent_docs/ui_refresh/user_stories.md` for the story IDs to trace)
   - `Architecture path:` `agent_docs/ui_refresh/state_design.md` +
     `agent_docs/ui_refresh/component_hierarchy.md` (and `supplemental/`)
   - `Plan folder:` `agent_docs/ui_refresh/plan/`
   - `Diff range:` `origin/main...HEAD`
3. The Review agent self-renames on entry; you do not need to rename it.
4. End this turn with **text instructions** pointing the user to the new Review tab. Do
   NOT ask the user a question (the workspace's "waiting for input" state must belong to
   the Review agent now).

## Verification checklist

- [ ] The Review agent is running in a new tab.
- [ ] Text instructions point the user there.

## Commit policy

**Do NOT commit.** This task does not edit any files. After spawning the Review agent,
report success with no commit.
