# pi-capabilities — Implementation Plan

## Summary

Turn pi's capability flags `True` as genuine support lands (11 target
flags after the context-reset/compaction split), via independent parallel
tranches over a shared base. The plan was written in **two passes**:
pass 1 specified **phase 0** (feasibility investigation) and **phase 1**
(the shared base tranche); pass 2 — authored after both merged
(`feasibility.md` verdicts + PR #54's landed substrate) — adds the
capability task files (02–11), each embedding its verdict-chosen pi-side
mechanism and the base tranche's actual landed names.

## Phases

- **Phase 0: Feasibility investigation (task 0)** — *merged (PR #53)*:
  `feasibility.md` verdicts — (i) Sculptor-side ×8, (ii) extension ×2
  (backchannel, sub-agents), (iv) defer ×1 (background tasks); no
  version bump needed.
- **Phase 1: Base tranche** — *merged (PR #54)*: ratchet-based gate-read
  hardening (the generated twin's index signature rules out the
  compile-time check), the `supports_context_reset` split, five new
  narrow atoms/hooks, the `CapabilityGate`/`useCapabilityGate` primitive
  (+ 3 `CAPABILITY_DISABLED_*` ElementIDs; suppression fallback for
  picker rows / skills panel / fast-mode), the typed pi protocol module
  (`parse_rpc_message` + full union) with a behavior-preserving
  exhaustive-match dispatcher, error-level dead-letter logging, and
  two-sided gate-state integration tests.
- **Phases 2–11: Capability tranches** *(planned in pass 2 — parallel,
  unordered except as noted)* — 02 interruption, 03 tool-use rendering,
  04 context reset, 05 compaction, 06 session resume, 07 interactive
  backchannel (AUQ + plan mode; first extension — establishes the
  REQ-EXT home and fail-loud posture), 08 skills, 09 image input + file
  attachments (bundled), 10 sub-agents (**after 03 and 07; schedule
  late** — heaviest, lowest-confidence, pre-staged deferral
  contingency), 11 background tasks (**originally deferred; reversal
  2026-06-13 — now an implementation tranche**: backgrounded tool calls
  + subagents/tasks in flight while the main thread stays interactive;
  see `11_01_background_tasks.md` and `feasibility.md` §11 REVERSAL).

## Phase Rationale

- **Phase 0 ∥ Phase 1.** They share nothing: phase 0 probes pi's protocol
  and extension surface (read/spike, merging only a document); phase 1 is
  Sculptor-side substrate. Both MUST merge before any capability phase
  starts (REQ-PROC-1, REQ-INV-5).
- **Why base first:** every capability tranche wires behavior into the
  hardened gates (typo-safe reads, complete atom set, tooltip primitive)
  and consumes typed protocol events — landing that once avoids 10
  re-derivations and merge storms (REQ-BASE-1).
- **Why a second planning pass:** pi-side mechanisms are deliberately
  undesigned until task 0's verdicts (architecture's locked doctrine);
  capability task files written now would not be self-contained. Pass 2
  reads `feasibility.md` + architecture §4 and writes `02_*`–`11_*` task
  files, landing as its own docs MR to `main`.

## Execution topology

- This docs branch (`danver/pi-capabilities`) merges to `main` **first**,
  so tranche workspaces rooted on `main` can read these documents.
- Every phase — including 0 and 1 — runs in its **own workspace** on
  branch `danver/pi-capabilities-<topic>` with its own MR targeting
  `main` (REQ-PROC-2). Suggested topics: `-feasibility`, `-base`.
- Capability phases (2–11) are **parallel tranches, not a sequence** —
  the numbering is an index, not an order. Start whatever is unblocked
  (REQ-PROC-3); bundling stays as architecture set it (09 is a bundle;
  REQ-PROC-4).
- Evidence bundles (REQ-PROC-6): phase 1 carries the full bundle
  (deterministic gates single-run output, full `real_pi/` run,
  real-claude rerun result, ticked checklist) plus an explicit
  zero-Claude-visible-change assertion (REQ-BASE-7). Phase 0 is a
  docs-only MR: deterministic gates + the probe evidence embedded in
  `feasibility.md` (REQ-INV-3) — real_pi/real-claude reruns are not
  required for it.
- A mid-tranche feasibility reversal pauses for Danver's explicit
  go-ahead before converting to a deferral (REQ-INV-6); deferrals ship a
  "Proposed FOLLOWUPS entry" block in the MR description (REQ-PROC-7).

## Task Index

| File | Task | Phase | Requirements |
|------|------|-------|--------------|
| `00_01_feasibility_investigation.md` | Probe pi 0.78.0 per capability; write `feasibility.md` (verdicts + evidence + mechanisms) | 0 | REQ-INV-1..6, REQ-PROC-2/6/7 |
| `01_01_capability_split_and_twin_hardening.md` | Split `supports_compaction` → `+supports_context_reset`; regenerate twin; make capability-read typos compile errors (ratchet fallback) | 1 | REQ-BASE-2, REQ-BASE-3, REQ-BASE-7 |
| `01_02_gate_substrate_atoms_and_hooks.md` | Add the five missing narrow atoms + hooks | 1 | REQ-BASE-4 |
| `01_03_tooltip_primitive_and_surface_migration.md` | Shared disabled-with-tooltip primitive; migrate interactive affordances; ElementIDs | 1 | REQ-BASE-5, REQ-BASE-7 |
| `01_04_typed_pi_protocol_module.md` | Extend pi event models to the full documented union; typed dispatcher rewire (behavior-preserving) | 1 | REQ-BASE substrate, REQ-BASE-7 |
| `01_05_dead_letter_logging.md` | Warn-and-drop for unsupported control messages | 1 | REQ-BASE-6 |
| `01_06_gate_state_integration_tests.md` | fake_pi-parametrized gate-state tests across all gated surfaces | 1 | REQ-TEST-4, REQ-BASE-5 |
| `02_01_interruption.md` | Stop halts pi turns via `abort`; aborted-vs-crash disambiguation; fake_pi abort rework | 2 | REQ-CAP-INTERRUPTION |
| `03_01_tool_use_rendering.md` | Tool-execution lane → ToolUseBlocks; core-four arg adaptation (pi `edit` is multi-edit-shaped); generic fallback | 3 | REQ-CAP-TOOL-RENDERING |
| `04_01_context_reset.md` | `/clear` → `new_session`; endpoint capability guard; waiter-budget handling | 4 | REQ-CAP-CONTEXT-RESET |
| `05_01_compaction.md` | `compaction_start/end` → `AutoCompacting*` messages; stuck-pill prevention; threshold-row divergence note | 5 | REQ-CAP-COMPACTION |
| `06_01_session_resume.md` | `--no-session` → managed `--session-dir`; persisted session id; loud fresh-start fallback | 6 | REQ-CAP-SESSION-RESUME |
| `07_01_interactive_backchannel.md` | Sculptor-pinned extension (AUQ via `ctx.ui`, plan-mode lever); `extension_ui_request` ⇄ answer wiring; gated-method overrides; REQ-EXT home + fail-loud posture | 7 | REQ-CAP-BACKCHANNEL, REQ-EXT-1..5 |
| `08_01_skills.md` | Repeatable `--skill` flags from `discover_skills` sources; `/skill:<name>` invocation seam; loose-commands/plugin verification | 8 | REQ-CAP-SKILLS |
| `09_01_image_input_and_file_attachments.md` | Prompt assembly stops dropping `files`: images → `prompt.images[]` (base64), others → paths; loud-failure posture + hoist-later comment | 9 | REQ-CAP-IMAGE-INPUT, REQ-CAP-FILE-ATTACHMENTS |
| `10_01_sub_agents.md` | Bespoke structured-progress extension + nested `parent_tool_use_id` adapter; spike-first with REQ-INV-6 deferral contingency | 10 | REQ-CAP-SUB-AGENTS |
| `11_01_background_tasks.md` | **Reversal (2026-06-13)** — implement background tasks: backgrounded tool calls + subagents/tasks in flight while the main thread stays interactive (extension mechanism, per the merged sub-agents pattern) | 11 | REQ-CAP-BACKGROUND-TASKS |

## Pass-2 handoff contract — completed

Pass 2 ran after PR #53 (`feasibility.md`) and PR #54 (base tranche)
merged, reading both plus the landed base diff. Sequencing constraints it
encodes: **phase 10 requires phases 03 and 07 merged** (ToolUseBlock
pipeline + extension packaging) and is deliberately scheduled late;
phase 07 verifies its soft interplay with 03 in whichever order they
land; all other capability phases are mutually independent and root on
`main` at start time (≥ merge `99cbc0d`). Phase 11 needs no workspace —
it is verification + cycle-close bookkeeping. Every capability tranche
must run the FULL `real_pi/` suite at merge (REQ-TEST-2); note that the
base tranche's own real_pi/real-claude runs were deferred to the cycle
owner (PR #54 "Testing" note) — the first capability tranche to merge
effectively backfills that coverage.
