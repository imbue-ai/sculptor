# pi-capabilities — Requirements

Phase 5 of the pi multi-harness initiative (cycle slug: `pi-capabilities`).
Derived from [goals.md](./goals.md) through the cycle's requirements Q&A
session (2026-06-11). Consumed by the architecture and implementation-plan
sessions and by the per-tranche implementation agents.

**Language.** MUST / SHOULD / MAY per RFC-2119 intent. Requirements state
WHAT, not HOW; mechanism choices belong to `architecture.md` and the
feasibility investigation.

**Targets.** The cycle targets every pi capability flag that is `False` and
in scope — after the split below, **11 target flags**:

| # | Flag | REQ |
| - | ---- | --- |
| 1 | `supports_interruption` | REQ-CAP-INTERRUPTION |
| 2 | `supports_tool_use_rendering` | REQ-CAP-TOOL-RENDERING |
| 3 | `supports_session_resume` | REQ-CAP-SESSION-RESUME |
| 4 | `supports_context_reset` *(new — split)* | REQ-CAP-CONTEXT-RESET |
| 5 | `supports_compaction` *(post-split)* | REQ-CAP-COMPACTION |
| 6 | `supports_interactive_backchannel` | REQ-CAP-BACKCHANNEL |
| 7 | `supports_skills` | REQ-CAP-SKILLS |
| 8 | `supports_sub_agents` | REQ-CAP-SUB-AGENTS |
| 9 | `supports_image_input` | REQ-CAP-IMAGE-INPUT |
| 10 | `supports_file_attachments` | REQ-CAP-FILE-ATTACHMENTS |
| 11 | `supports_background_tasks` | REQ-CAP-BACKGROUND-TASKS |

**The compaction split (requirements-level refinement of goals.md).**
`supports_compaction` as shipped conflates two mechanisms with different
semantics and different feasibility: `/clear` is a context **reset** (the
session is discarded and the next turn starts fresh —
`process_clear_context_message`, `process_manager.py`), while
**compaction** summarizes context in place at a threshold so the same
conversation continues (`AutoCompactingAgentMessage` plugin hook,
`derived.py`). This cycle splits the flag into `supports_context_reset`
(the `/clear` path) and `supports_compaction` (auto-compaction chrome).
Claude advertises both `True` — no Claude behavior change. goals.md's
Targets bullet is amended in the same commit as this document.

**Definitions.**

- **Tranche** — an independent unit of work in its own workspace and MR,
  rooted on `main`. The **base tranche** is the shared-groundwork tranche
  (REQ-BASE). **Task 0** is the feasibility investigation (REQ-INV).
- **Affordance** — a user-visible surface or behavior a capability flag
  gates (button, panel, picker entry, message handling path).
- **Verdict** — the investigation's per-capability feasibility
  classification (REQ-INV-2).
- **Deferral** — leaving a flag `False` with its gate correctly wired
  (affordance hidden/disabled, never dead or fail-open) and the gap
  surfaced to the architect.
- **Extension** — code added to pi's pinned, immutable plugin/extension
  set, shipped by Sculptor. pi-core itself is immutable and NOT ours to
  change.
- **Evidence bundle** — the MR-recorded proof a tranche met its bars
  (REQ-PROC-7).

---

## REQ-INV — Feasibility investigation (task 0)

- **REQ-INV-1.** The investigation MUST run as implementation task 0: its
  own tranche, workspace, and branch. It MAY write spike code against real
  pi. Its sole merged deliverable MUST be
  `agent_docs/pi-capabilities/feasibility.md`.
- **REQ-INV-2.** `feasibility.md` MUST record one verdict per target flag
  using this fixed taxonomy: **(i)** achievable Sculptor-side only;
  **(ii)** achievable via added pi extension; **(iii)** achievable only via
  a pinned-version bump (permission-gated per REQ-PROC-6); **(iv)** blocked
  on pi-core → defer. Free-form notes MAY supplement any verdict whose
  findings exceed the taxonomy.
- **REQ-INV-3.** Every verdict MUST cite evidence: a protocol trace, spike
  result, or upstream source/docs reference sufficient for a reviewer to
  check the classification.
- **REQ-INV-4.** Spike code MUST NOT merge. The spike branch and workspace
  MUST remain on the filesystem for reference until cycle close; Danver is
  responsible for deleting them.
- **REQ-INV-5.** No capability tranche may start before its flag's verdict
  is recorded (the **verdict gate**). The investigation MAY run
  concurrently with the base tranche — neither depends on the other.
- **REQ-INV-6.** If a tranche discovers mid-implementation that its
  verdict was wrong (a pi-core wall the investigation missed), it MUST
  pause and obtain Danver's explicit go-ahead before converting to a
  deferral, and `feasibility.md` MUST be amended to match reality.

## REQ-BASE — Shared base tranche (gate hardening + substrate)

- **REQ-BASE-1.** The base tranche MUST merge to `main` first,
  independently of and before every capability tranche; capability
  tranches root on `main` after it lands.
- **REQ-BASE-2.** *(FOLLOWUPS-9.)* A mistyped capability field name in
  frontend gate code MUST be a compile-time error. Primary approach:
  verify/tighten the generated `HarnessCapabilities` TypeScript twin so an
  unknown key cannot type-check (no index signature swallowing typos), and
  lock that guarantee with a type-level test. If this proves infeasible
  (e.g. it breaks the older-client/new-field forward-compat story), the
  tranche MUST fall back to a ratchet forbidding direct
  `.harnessCapabilities.<field>` reads outside the narrow-atom layer.
- **REQ-BASE-3.** The base tranche MUST perform the compaction split:
  `supports_context_reset` and `supports_compaction` as separate flags on
  `HarnessCapabilities` and its generated twin. Claude MUST advertise both
  `True` with no behavior change; pi starts both `False`.
- **REQ-BASE-4.** The base tranche MUST complete the gate substrate: every
  target flag is readable through one hardened, narrowly-typed read path
  per consuming side (frontend: a dedicated per-flag atom + hook in the
  existing `taskSupports*` pattern; backend: typed `capabilities()` reads).
  Flags missing that path today: `supports_context_reset`,
  `supports_compaction`, `supports_background_tasks`,
  `supports_session_resume`, `supports_tool_use_rendering`.
- **REQ-BASE-5.** Surfaces gated off for pi MUST upgrade from
  hidden-outright to **disabled with an explanatory tooltip** wherever
  feasible; where infeasible, graceful fallback (hiding) is acceptable.
  This includes `supports_fast_mode`'s surfaces (presentation only — the
  capability itself stays out of scope). The treatment MUST be testable:
  one standardized copy pattern and a stable ElementID per upgraded
  surface.
- **REQ-BASE-6.** *(Dead-letter visibility.)* Any control message the pi
  agent drops because its capability is unsupported (today:
  interrupt, resume, clear-context, question-answer in
  `PiAgent._push_message`) MUST log a warning identifying the dropped
  message type. No user-facing change. Capability tranches replace
  warn-and-drop with real handling as they land.
- **REQ-BASE-7.** The base tranche MUST NOT change Claude-visible
  behavior.

## REQ-CAP — Capability requirements

### Cross-cutting (apply to every REQ-CAP below)

- **REQ-CAP-ALL-1.** *(Strict flip rule.)* A flag flips `True` only when
  ALL affordances it gates work end-to-end on pi. Partial delivery means
  the flag stays `False` and the remainder defers. The per-flag affordance
  lists below are **descriptive** starting points — "ALL" is judged per
  tranche at implementation time.
- **REQ-CAP-ALL-2.** *(Override valve.)* A flag MAY flip despite a known
  residual gap only for overwhelming reason, by maintainer judgment; the
  residual surface MUST carry a `CAPABILITY-GAP:` code marker recording
  the gap.
- **REQ-CAP-ALL-3.** *(Parity bar.)* The capability MUST behave the
  "same" as on a Claude workspace from the user's perspective; divergence
  is allowed only where pi is sufficiently different, and MUST be recorded
  in the tranche's MR.
- **REQ-CAP-ALL-4.** *(No fail-open, no dead affordance.)* While `False`,
  every gated surface is hidden or disabled-with-tooltip; when `True`,
  every gated surface works.
- **REQ-CAP-ALL-5.** A tranche MUST remove the `CAPABILITY-GAP:` markers
  it resolves and MUST NOT leave stale ones.
- **REQ-CAP-ALL-6.** *(Striving bar.)* Deferral is a last resort: it
  requires either verdict (iv) from REQ-INV-2 or a paused-and-approved
  mid-tranche reversal per REQ-INV-6.
- **REQ-CAP-ALL-7.** Each tranche MUST satisfy REQ-TEST and REQ-PROC for
  the flag(s) it carries; a bundled tranche (REQ-PROC-5) satisfies every
  bundled REQ-CAP individually.

### REQ-CAP-INTERRUPTION — `supports_interruption`

The Stop affordance MUST halt the in-flight pi turn with latency
comparable to Claude's observable stop behavior, leave the agent
responsive to the next message, and leave no zombie pi work running.
Queued-message behavior matches Claude's where applicable. Bar is
qualitative — tests assert completion of the stop, not a tight numeric
deadline. Known gated surfaces: stop affordances in the status pill and
chat input, queued-message bar; backend handling of the interrupt control
message (today dropped).

### REQ-CAP-TOOL-RENDERING — `supports_tool_use_rendering`

pi tool calls MUST render as rich tool blocks (tool name, input, and
output/result, with in-progress state while running) equivalent to
Claude's tool rendering, instead of being discarded. Diff refresh on
file-mutating tools (already wired) MUST keep working. Known gated
surfaces: chat tool-call rendering (tool groups); pi-side tool events
(today ignored at `tool_execution_start`/`_update`).

### REQ-CAP-SESSION-RESUME — `supports_session_resume`

A pi workspace's conversation MUST survive the flows that session resume
serves for Claude (agent process restart — e.g. Sculptor restart or
workspace reopen) with context preserved: the resumed agent can answer
follow-ups that depend on pre-restart conversation content. Known gated
surface: resume control-message handling (today dropped).

### REQ-CAP-CONTEXT-RESET — `supports_context_reset` *(new)*

`/clear` MUST work for pi: the context is genuinely reset (the next turn
demonstrably does not see prior-conversation content), the slash entry is
available, and the reset is acknowledged in the conversation the same way
as on Claude. Known gated surfaces: the `/clear` pseudo-skill entry in the
chat input; clear-context control-message handling (today dropped).

### REQ-CAP-COMPACTION — `supports_compaction` *(post-split)*

Auto-compaction chrome MUST be truthful for pi: the "Compacting" status
state and the context/threshold display reflect real pi compaction
behavior as it happens. If pi-core never surfaces compaction signals,
this flag defers (verdict-dependent). Known gated surfaces: status-pill
compacting state, token-popover context row.

### REQ-CAP-BACKCHANNEL — `supports_interactive_backchannel`

Both interactions the flag gates MUST work end-to-end: (a)
ask-user-question — the agent can pose a structured question, the user
answers in Sculptor's UI, and the answer reaches the agent mid-turn; (b)
plan mode — entry, plan presentation, and exit behave as on Claude. The
harness's gated methods (`is_ask_user_question_tool`,
`is_exit_plan_mode_tool`, `is_valid_ask_user_question_input`, plan-file
extraction) MUST answer truthfully for pi. Known gated surfaces: plan-mode
entry in chat input, AUQ/plan tool rendering, backend waiting-state
derivation and the plan-mode API gate, question-answer control-message
handling (today dropped).

### REQ-CAP-SKILLS — `supports_skills`

The skill set a workspace shows under Claude — all sources (repo-level
`.claude/skills`, user-global skills, built-in/plugin skills) — MUST be
discoverable and executable from a pi workspace: the slash picker lists
them and invoking one causes pi to follow that skill. Anything less than
the full set is partial (REQ-CAP-ALL-1 applies). Known gated surfaces:
skills panel, slash-command picker source.

### REQ-CAP-SUB-AGENTS — `supports_sub_agents`

pi sub-agent activity MUST render grouped and labeled as Claude's
sub-agents do (a parent entry with the sub-agent's activity nested), and
sub-agent work MUST be attributed distinctly from main-loop work. Known
gated surface: sub-agent grouping in chat tool rendering.

### REQ-CAP-IMAGE-INPUT — `supports_image_input`

Images supplied through every input surface (paste, `+`-menu, toolbar)
MUST reach the pi model on image-capable models. Because pi fronts a mixed
model set, the flag MAY flip while honest degradation handles non-capable
models: when the selected model cannot accept images, the affordance MUST
NOT silently drop them (mechanism — including instance-state-dependent
`capabilities()` — decided at architecture). Known gated surfaces:
`+`-menu Images entry, editor paste path, chat-input image gating.

### REQ-CAP-FILE-ATTACHMENTS — `supports_file_attachments`

File attachments MUST work for pi as they do for Claude: attaching a file
through the chat-input surfaces delivers its content to the agent for that
turn. Known gated surface: chat-input attachment gating.

### REQ-CAP-BACKGROUND-TASKS — `supports_background_tasks`

Background-task affordances MUST behave as on Claude: long-running work
the agent backgrounds is visible as such, and its completion is reflected
in the conversation. The concrete affordance inventory for this flag is
thin today (no dedicated frontend gate exists); the base tranche adds the
gate (REQ-BASE-4) and the investigation pins what pi can express.

## REQ-EXT — Extension packaging & security

- **REQ-EXT-1.** Extensions Sculptor adds to pi's set MUST live in the
  Sculptor repository and be code-reviewed like any other code.
- **REQ-EXT-2.** The extension set MUST be pinned together with the pi
  binary version as one immutable unit.
- **REQ-EXT-3.** Extensions MUST NOT be user-visible or user-configurable
  (no plugin management surface).
- **REQ-EXT-4.** Extensions MUST NOT embed secrets.
- **REQ-EXT-5.** Extensions MUST NOT emit telemetry of their own.

## REQ-TEST — Conformance & regression

- **REQ-TEST-1.** Each capability tranche MUST add `real_pi/` tests
  mirroring the corresponding `real_claude/` test(s) for that capability;
  divergence from the Claude shape is allowed only where pi is
  sufficiently different and MUST be justified in the MR.
- **REQ-TEST-2.** At merge time a tranche MUST have the FULL `real_pi/`
  suite green (same rerun tolerance the goals grant the real-Claude gate)
  — no regressions across parallel tranches.
- **REQ-TEST-3.** Every tranche MUST keep the deterministic gates green on
  a single run (`just test-unit`, `just test-offload`, `just ratchets`,
  `just check`) and the stochastic real-Claude gate green on a rerun.
- **REQ-TEST-4.** Each capability tranche MUST include gate-state tests
  for its flag: the affordance is hidden/disabled when the harness reports
  `False`, and functional when `True` (the FOLLOWUPS-9 lesson — a gate is
  only trusted when a test asserts the gated-off state).
- **REQ-TEST-5.** Existing granted capabilities MUST NOT regress:
  `supports_file_references` stays `True` and functional for pi.

## REQ-PROC — Process

- **REQ-PROC-1.** Base first: REQ-BASE merges before any capability
  tranche starts (REQ-BASE-1); the verdict gate (REQ-INV-5) also applies.
- **REQ-PROC-2.** Each tranche runs in its own workspace on branch
  `danver/pi-capabilities-<topic>`, with its own MR targeting `main`.
- **REQ-PROC-3.** No priority ordering and no cap on tranches in flight:
  pure parallelism — start whatever is unblocked; investigation findings
  shape sequencing naturally.
- **REQ-PROC-4.** Tranches MAY bundle multiple flags where plumbing is
  genuinely shared (decided at architecture/plan time); a bundled tranche
  satisfies every bundled REQ-CAP individually.
- **REQ-PROC-5.** A pinned-pi-version bump is opportunistic only and MUST
  receive Danver's explicit permission BEFORE the bump is made.
- **REQ-PROC-6.** *(Evidence bundle.)* Each tranche's MR MUST record:
  deterministic-gates output (single-run green), full `real_pi/` run
  output (rerun tolerance noted if used), the real-Claude rerun result,
  and a ticked acceptance checklist for its REQ-CAP(s).
- **REQ-PROC-7.** *(Deferral handoff.)* Every deferral or structural
  learning MUST appear in the tranche's MR description as a ready-to-curate
  **"Proposed FOLLOWUPS entry"** block: problem statement + evidence +
  suggested resolution direction. The architect curates from there.
- **REQ-PROC-8.** *(Docs conform.)* Each tranche MUST update user-facing
  docs where its change makes them wrong — kept deliberately small, since
  pi capabilities are discoverable through the UI; docs must not become a
  brittle capability matrix.
- **REQ-PROC-9.** *(Cycle close.)* The cycle closes when every REQ-CAP is
  resolved (flag flipped, or deferred with its FOLLOWUPS block) and
  `feasibility.md` reflects final reality. The cycle agent MUST then ask
  Danver for the graduation judgment (daily-usable: yes/not-yet) and
  record it as a final "Graduation" section appended to `feasibility.md`.

## Out of Scope

- **`supports_fast_mode`** — no natural mapping to pi's models for now.
  (Its gated-off surfaces DO receive REQ-BASE-5 presentation treatment.)
- **Retiring `enable_multi_harness`** — deliberately retained,
  indefinitely; decoupled from graduation (FOLLOWUPS-8). Do not touch it.
- **The `harness-per-invocation` migration** — its own later cycle
  (FOLLOWUPS-5).
- **A generic schema-driven settings-form engine** — deferred until a
  third harness exists.
- **Fixing `just test-real-claude` flakiness** — the rerun cost is
  accepted; owning that fix is outside this initiative.
- **Modifying pi-core** — immutable, not ours to change; extension points
  only.
- **A fixed automated graduation gate** — graduation stays a human
  judgment (REQ-PROC-9).

## Open questions (deferred to architecture / investigation)

1. **Extension runtime-failure handling** — decided per capability at
   architecture time (leaning: fail loud first, evolve toward isolation).
   Deliberately not pinned here.
2. **Image-input model-dependence mechanism** — how honest degradation on
   non-capable models is expressed (instance-state-dependent
   `capabilities()` is an allowed shape). REQ-CAP-IMAGE-INPUT states the
   behavior; architecture picks the mechanism.
3. **Compaction signal availability** — whether pi-core surfaces
   compaction at all (REQ-CAP-COMPACTION is verdict-dependent).
4. **Twin tightening vs forward-compat** — REQ-BASE-2's primary approach
   needs verification against the older-client/new-field story; the
   fallback is specified.

## Acceptance criteria summary

| REQ | Acceptance criterion | Verified by |
| --- | -------------------- | ----------- |
| REQ-INV-1..3 | `feasibility.md` merged with a taxonomy verdict + evidence for all 11 targets | MR review of task 0 |
| REQ-INV-4 | No spike code in the merged diff; spike branch/workspace retained on disk | MR diff + Danver at cycle close |
| REQ-INV-5 | No capability MR opens before its verdict exists | Orchestrator + MR review |
| REQ-INV-6 | Any verdict reversal shows a recorded pause + Danver go-ahead | MR review |
| REQ-BASE-2 | A deliberately mistyped capability read fails `just check`; or the ratchet rejects direct reads | Type-level test / ratchet run |
| REQ-BASE-3 | Both split flags exist end-to-end (model, twin, gates); Claude advertises both `True`; Claude UX unchanged | Unit tests + deterministic gates |
| REQ-BASE-4 | Every target flag has its narrow read path; no consumer reads `harnessCapabilities` directly | Code review + ratchet/test |
| REQ-BASE-5 | Each upgraded surface shows standardized tooltip copy under its stable ElementID when gated off | Integration tests |
| REQ-BASE-6 | Each dropped control message produces a warning log naming the message type | Unit tests |
| REQ-BASE-7 / REQ-TEST-3 | Deterministic gates green single-run; real-Claude green on rerun | Evidence bundle |
| REQ-CAP-ALL-1/2 | Flag flips only with all affordances working, or carries a maintainer-approved `CAPABILITY-GAP` marker | MR review + REQ-TEST-4 tests |
| REQ-CAP-ALL-5 | No stale `CAPABILITY-GAP` markers for resolved gaps | grep in MR review |
| REQ-CAP-INTERRUPTION | Stop ends the in-flight pi turn; agent answers a follow-up; no orphaned pi work | `real_pi` interrupt tests |
| REQ-CAP-TOOL-RENDERING | A pi tool call renders name/input/result with in-progress state | `real_pi` tool-call tests |
| REQ-CAP-SESSION-RESUME | Post-restart pi agent answers a question depending on pre-restart context | `real_pi` resume test |
| REQ-CAP-CONTEXT-RESET | After `/clear`, pi demonstrably lacks prior context; UX matches Claude's `/clear` | `real_pi` clear test |
| REQ-CAP-COMPACTION | Compacting state + context display reflect real pi compaction events | `real_pi` test (verdict-dependent) |
| REQ-CAP-BACKCHANNEL | AUQ round-trip and plan-mode enter/exit both work end-to-end | `real_pi` AUQ + plan tests |
| REQ-CAP-SKILLS | The workspace's full Claude-visible skill set lists and executes under pi | `real_pi` skills test |
| REQ-CAP-SUB-AGENTS | pi sub-agent activity renders nested/attributed like Claude's | `real_pi` sub-agent test |
| REQ-CAP-IMAGE-INPUT | Image via paste/menu/toolbar reaches a capable model; non-capable model path degrades honestly | `real_pi` image test |
| REQ-CAP-FILE-ATTACHMENTS | An attached file's content is usable by pi that turn | `real_pi` attachment test |
| REQ-CAP-BACKGROUND-TASKS | Backgrounded work is visible and completion reflected, as on Claude | `real_pi` background test |
| REQ-EXT-1..5 | Extensions in-repo, reviewed, pinned with pi version, user-invisible, secret-free, telemetry-free | Code review |
| REQ-TEST-1 | Each tranche's `real_pi` tests name their `real_claude` counterparts (or justify divergence) | MR review |
| REQ-TEST-2 | Full `real_pi/` suite green at merge | Evidence bundle |
| REQ-TEST-4 | Gated-off state has an explicit asserting test per flag | MR review |
| REQ-TEST-5 | `supports_file_references` unchanged and covered | Existing tests stay green |
| REQ-PROC-2 | Branch `danver/pi-capabilities-<topic>`, own workspace, MR → `main` | MR review |
| REQ-PROC-5 | No pi-version change without recorded prior permission | MR review |
| REQ-PROC-6 | Evidence bundle present in MR description | MR review |
| REQ-PROC-7 | Deferrals carry a "Proposed FOLLOWUPS entry" block | MR review |
| REQ-PROC-9 | Graduation section recorded in `feasibility.md` after Danver's call | Cycle close |
