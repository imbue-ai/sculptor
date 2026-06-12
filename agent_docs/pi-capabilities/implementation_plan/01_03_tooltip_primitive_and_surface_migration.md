# Task 1.3: Shared capability-gate primitive + surface migration (disabled-with-tooltip)

## Goal

Replace hidden-outright gating on pi's missing capabilities with one
shared frontend primitive that renders an affordance **disabled with an
explanatory tooltip** (standardized copy, stable ElementID per surface),
and migrate every interactive gated affordance onto it. Status-only
chrome keeps its graceful fallback (hidden/collapsed).

## Requirements addressed

REQ-BASE-5, REQ-BASE-7 (Claude rendering unchanged).

## Background

Sculptor gates per-harness affordances on `task.harnessCapabilities`
(generated twin of `HarnessCapabilities`,
`sculptor/sculptor/interfaces/agents/harness.py:51-81`). Reads go through
narrow hooks (`sculptor/frontend/src/common/state/hooks/useTaskHelpers.ts:33-62`;
five more added by Task 1.2: ContextReset, Compaction, BackgroundTasks,
SessionResume, ToolUseRendering). Consumers currently HIDE affordances
when a capability is false (e.g. the plan-mode toggle, the Stop button) —
the north-star ideal is "greyed/disabled with an explanatory tooltip
where feasible; graceful fallback otherwise; visible, never silent."

The decision record (requirements/architecture Q&A): one shared
primitive, reused everywhere feasible; **interactive affordances only** —
status-only chrome (the StatusPill "Compacting" state at
`StatusPill.tsx:34`, the TokenPopover context row at
`TokenPopoverContent.tsx:30`) and pure rendering degradations (tool calls
as plain text) have nothing to disable and stay hidden/collapsed as the
documented graceful fallback. The treatment must be testable: a
standardized copy pattern + a stable ElementID per upgraded surface
(REQ-BASE-5). The `?? true` load-race default in consumers is retained.

Existing UI patterns to follow: Radix `Tooltip` from `@radix-ui/themes`
(example: `sculptor/frontend/src/pages/workspace/components/AgentStatusDot.tsx:42`);
the `TooltipIconButton` wrapper (used at
`sculptor/frontend/src/pages/workspace/components/BottomBar.tsx:64,86` and
`ChatInput.tsx:581`); ElementIDs are a backend `StrEnum`
(`sculptor/sculptor/constants.py:11`, SCREAMING_SNAKE values) regenerated
into frontend types via `just generate-api` and asserted in tests via
`page.get_by_test_id(ElementIDs.X)`.

The gated interactive surfaces (current state):

- Plan-mode toggle — `ChatInput.tsx:149` (`canEnterPlanMode`, hidden via
  `useTaskSupportsInteractiveBackchannel`); marker at `ChatInput.tsx:284`.
- Interrupt/Stop — `StatusPill.tsx:103` (`canBeInterrupted`), Ctrl+C
  keybinding gate `ChatInput.tsx:153`, `QueuedMessageBar.tsx:45`.
- Fast-mode toggle — `ChatInput.tsx:154` (`canUseFastMode`) —
  presentation-only inclusion: the capability itself is out of scope, but
  its surface gets the honest disabled treatment.
- File attachments — `ChatInput.tsx:155` + the AND-of-model-and-harness
  at `ChatInput.tsx:169`.
- Image input — `+`-menu Images entry (`MentionPickerList.tsx:143`
  marker), toolbar upload + paste path (`Editor.tsx:230` marker,
  `handleTriggerImageUpload` in `ChatInput.tsx:160-165`).
- Skills — `SkillsPanel.tsx:64` (`canRenderSkills`) and the slash-picker
  skill source (`TipTapConfig.ts:341` marker).
- `/clear` entry — `ChatInput.tsx:186` region (pseudo-skill execution;
  picker entry) — gates on Task 1.2's `useTaskSupportsContextReset`.

## Files to modify/create

- **Create** the shared primitive: a hook + thin component pair under
  `sculptor/frontend/src/components/` (suggested name
  `CapabilityGate` / `useCapabilityGate`), consuming a narrow
  `useTaskSupports<X>` hook result and yielding
  `{enabled}` | `{disabled, tooltip copy, elementId}`; tooltip rendering
  via Radix `Tooltip` consistent with `TooltipIconButton`.
- **Copy constant:** one standardized string beside the primitive — use
  the pattern "Not supported by this agent harness" (if the task view
  exposes the harness display name, prefer "Not supported by the
  <name> harness" — verify what `derived.py`'s task view exposes; do not
  add a new backend field for this).
- `sculptor/sculptor/constants.py` — new ElementIDs (StrEnum members) for
  each upgraded surface, e.g. `CAPABILITY_DISABLED_PLAN_MODE`,
  `CAPABILITY_DISABLED_STOP`, `CAPABILITY_DISABLED_FAST_MODE`,
  `CAPABILITY_DISABLED_ATTACHMENTS`, `CAPABILITY_DISABLED_IMAGE_INPUT`,
  `CAPABILITY_DISABLED_SKILLS`, `CAPABILITY_DISABLED_CLEAR` (follow the
  enum's existing grouping/comment style); run `just generate-api`.
- Migrate consumers:
  `sculptor/frontend/src/pages/workspace/components/ChatInput.tsx`
  (plan-mode toggle, fast-mode toggle, attachments, image upload trigger,
  `/clear` picker entry + `executePseudoSkill` refusal),
  `sculptor/frontend/src/pages/workspace/components/chat-alpha/StatusPill.tsx`
  (Stop button), `sculptor/frontend/src/pages/workspace/components/QueuedMessageBar.tsx`,
  `sculptor/frontend/src/pages/workspace/panels/SkillsPanel.tsx`,
  `sculptor/frontend/src/components/MentionPickerList.tsx` (Images
  category row), `sculptor/frontend/src/components/Editor.tsx` /
  `TipTapConfig.ts` (paste path notice + slash-picker skill rows — see
  Gotchas for picker feasibility).

## Implementation details

1. Build the primitive first; it must compose with both icon-button-like
   surfaces (`TooltipIconButton` style) and row/entry surfaces (picker
   rows, panel sections).
2. Migrate each surface: where the affordance is a button/toggle, render
   it disabled with the tooltip + `data-testid` from the new ElementID;
   where it's a picker row (Images category, skill entries, `/clear`),
   render the row disabled-with-tooltip if the picker framework supports
   disabled items — otherwise suppress the row (graceful fallback) and
   note it in the MR.
3. `/clear` needs BOTH: picker-entry treatment AND an execution-time
   refusal in `executePseudoSkill` (`ChatInput.tsx:186-200`) — typing
   `/clear` manually must not fire the endpoint when
   `useTaskSupportsContextReset(taskID) ?? true` is false (show the
   standard copy as a toast, mirroring the existing failure toast there).
4. Keep `?? true` semantics at every consumer (visible-until-loaded).
5. Update the existing pi-side assertions in
   `tests/integration/frontend/test_pi_capability_gating.py` — the five
   tests currently assert `to_have_count(0)` for pi (hidden); after
   migration the upgraded surfaces assert disabled + tooltip-bearing +
   ElementID-visible instead. (Task 1.6 adds the new flags' coverage.)
6. Remove/retarget the CAPABILITY-GAP markers this task resolves
   (presentation markers at `MentionPickerList.tsx:143`,
   `Editor.tsx:230`, `ChatInput.tsx:186/284` presentation halves) —
   behavior markers (backend drops, tool events) stay until their
   capability tranches land.

## Testing suggestions

- Integration (the real bar): the migrated-surface assertions in
  `tests/integration/frontend/test_pi_capability_gating.py` — pi side:
  disabled + tooltip + ElementID; Claude side: enabled and visually
  unchanged. Also `tests/integration/frontend/test_pi_basic.py` (chat
  remains usable) and `test_workspace_harness_picker.py` (workspace
  creation unaffected).
- Component-level: a focused unit/story test of the primitive itself
  (enabled/disabled/tooltip-copy states).

## Gotchas

- **IconButtons inside `Flex` need `gap="2"`** (Radix hover-margin
  quirk — repo CLAUDE.md frontend guideline).
- Radix `Tooltip` does not fire on `disabled` buttons in some setups —
  follow `TooltipIconButton`'s existing handling (wrapper span) rather
  than inventing one.
- Editor/TipTap surfaces (`TipTapConfig.ts` slash picker,
  `createTipTapExtensions`) have **no `taskID` in scope** — the
  `TipTapConfig.ts:339-341` markers say exactly this; thread the
  capability (or the gate result) through the Editor props rather than
  reading state inside the TipTap config. If threading is disproportionate
  for picker rows, suppression is the sanctioned fallback — record it.
- Do not change any Claude-visible rendering: every migrated surface must
  render byte-identically for a harness whose capability is true.
- Keyboard paths: the Ctrl+C interrupt keybinding (`ChatInput.tsx:153`)
  and image-paste path (`Editor.tsx:230`) have no visible affordance to
  disable — they stay inert for pi (existing behavior); paste of images
  for a non-supporting harness should keep routing only non-image
  attachments exactly as today.

## Verification checklist

- [ ] Every upgraded surface: pi-workspace shows disabled control +
      standardized tooltip copy + stable ElementID; Claude-workspace
      renders unchanged (pixel-equivalent enabled state).
- [ ] `/clear` typed manually in a pi workspace does NOT call
      `clearWorkspaceAgentContext`; shows the standard copy.
- [ ] New ElementIDs regenerate cleanly (`just generate-api`) and are the
      only test hooks the assertions use.
- [ ] Presentation CAPABILITY-GAP markers resolved by this task are gone;
      `grep -rn "CAPABILITY-GAP" sculptor/frontend` lists only
      still-unresolved behavior markers.
- [ ] Integration tests:
      `tests/integration/frontend/test_pi_capability_gating.py` (updated
      assertions), `test_pi_basic.py`, `test_workspace_harness_picker.py`.
