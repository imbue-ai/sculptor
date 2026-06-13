# pi-capabilities — Architecture

Phase 5 of the pi multi-harness initiative (cycle slug: `pi-capabilities`).
Derived from [goals.md](./goals.md) and [requirements.md](./requirements.md)
through the cycle's architecture Q&A session (2026-06-11).

**Design doctrine (locked).** This document designs the **Sculptor side
firmly** — adapters, message contracts, gates, substrate — for every target
capability. It deliberately does **not** design pi-side acquisition
mechanisms: those are chosen empirically by the task-0 feasibility
investigation and recorded permanently in `feasibility.md` (REQ-INV), which
this document points at. Where pi's pinned protocol is already characterized
by the committed reference
[`../pi-basic/pi-0.78.0-rpc.md`](../pi-basic/pi-0.78.0-rpc.md) (cited below
as **RPC §n**), that surface is treated as a *known constraint*, and each
capability section ends with the **probe checklist** task 0 must verify
empirically before the tranche commits.

---

## 1. Executive summary

The cycle inserts a shared **base tranche** (frontend gate substrate +
backend typed protocol layer), runs a **task-0 feasibility investigation**,
then fans out **independent capability tranches** that each wire one (or a
bundled few) of the 11 target flags end-to-end: pi-side mechanism (per
feasibility verdict) → typed events → Sculptor adapter → existing
harness-agnostic message contracts → hardened gates.

| Concern | Before (pi-basic shipped) | After (cycle complete) |
| --- | --- | --- |
| Gate-read typo safety | Mistyped field can resolve loosely; `?? true` makes gates fail **open** (FOLLOWUPS-9) | Mistyped capability read is a **compile error** (verified; ratchet fallback) — REQ-BASE-2 |
| Gate substrate | 8 of 12 flags have narrow atoms/hooks; 4 gates missing entirely | Every target flag has one hardened read path per side — REQ-BASE-4 |
| Degraded-affordance UX | Surfaces hidden outright | Disabled + explanatory tooltip via one shared primitive (stable ElementIDs, standard copy) — REQ-BASE-5 |
| Capability model | 12 bool flags; `/clear` conflated with compaction | 13 flags; `supports_context_reset` split out — REQ-BASE-3 |
| pi event handling | Raw-dict dispatch; tool/compaction/extension events discarded | Typed protocol module mirroring RPC §4–5 unions; per-capability adapters consume typed events — REQ-BASE (substrate) |
| Unsupported control messages | Silently dropped in `_push_message` | Warn-and-drop (dead-letter log), replaced by real handlers per tranche — REQ-BASE-6 |
| pi capability flags | 1 of 12 `True` (`supports_file_references`) | Each target flag `True` where its tranche lands; deferred flags stay `False` with correct fail-closed gates — REQ-CAP-* |
| pi-side mechanism record | None | `feasibility.md`: verdict + mechanism per capability, kept current — REQ-INV |
| Conformance | `real_pi/` = 2 smoke tests | Mirrors `real_claude/` per delivered capability; full suite green at every merge — REQ-TEST |

## 2. Current architecture

### 2.1 Backend — the pi agent today

```
            ChatInputUserMessage (text + files[] — files dropped today)
                       │
            ┌──────────▼─────────────────────────────────────────┐
            │ PiAgent (agent_wrapper.py)                         │
            │  _push_message: ChatInput → queue; everything else │
            │  silently dropped (interrupt/resume/clear/answer)  │
            │  _process_message_queue ─► RPC: {"type":"prompt"}  │
            └──────────┬─────────────────────────────────────────┘
                       │ stdin JSONL                 stdout JSONL
            ┌──────────▼─────────────────────────────────────────┐
            │ pi --mode rpc --no-session --append-system-prompt  │
            │ (pinned 0.78.0; runs its own read/edit/bash loop)  │
            └──────────┬─────────────────────────────────────────┘
                       │ three multiplexed lanes (RPC §5)
        ┌──────────────┼──────────────────┐
   "response"   AgentSessionEvent   "extension_ui_request"
   (ack by id)  (raw-dict dispatch)  (logged, discarded)
                       │
        message_update/_end → text accumulator → Partial/ResponseBlock
        tool_execution_end  → diff refresh only (rendering discarded)
        agent_end           → turn boundary
```

- Launch: `agent_wrapper.py:140`. Dispatcher: `_consume_until_turn_end`
  (`agent_wrapper.py:258`). Drops: `_push_message` (`agent_wrapper.py:150`).
- pi is **stateful across turns** within one process; `agent_end` is the
  turn boundary; preflight failures arrive as `response success:false`
  with **no** session events (RPC §6).

### 2.2 Frontend — capability gating today

```
 derived.py:381  harness_capabilities = resolve_harness(config).capabilities()
        │  (computed per task view; serialized to the generated TS twin)
        ▼
 taskAtomFamily ──► taskSupports<X>AtomFamily (8 narrow atoms, tasks.ts)
        │                      │  missing: context_reset*, compaction,
        │                      │  background_tasks, session_resume,
        ▼                      ▼  tool_use_rendering   (*post-split)
 useTaskSupports<X>() ──► consumer applies `?? true`  ◄── FOLLOWUPS-9:
        │                                                 typo or load-race
        ▼                                                 fails OPEN
 surfaces: ChatInput, StatusPill, QueuedMessageBar, SkillsPanel,
           AlphaToolGroup, MentionPickerList, Editor (paste path)
```

- One backend API gate exists: plan-mode entry rejects when
  `!supports_interactive_backchannel` (`app.py:2078`).
- `CAPABILITY-GAP:` markers annotate the unwired surfaces (inventory in
  requirements.md).

## 3. Key changes

### 3.1 The capability acquisition pattern (every tranche)

```
        feasibility.md verdict (task 0) ──── chooses ────┐
                                                         ▼
 ┌────────────┐   typed commands    ┌────────────────────────────┐
 │ pi 0.78.0  │ ◄─────────────────  │ PiAgent + protocol module  │
 │ (pinned;   │   typed events      │  per-capability adapter    │
 │ immutable) │ ─────────────────►  │  (Sculptor-side, firm)     │
 └────────────┘                     └─────────────┬──────────────┘
   ▲ extensions (only pi-side                     │ existing harness-agnostic
   │ lever; in-repo, pinned w/ binary)            ▼ agent messages
   │                                ┌────────────────────────────┐
   └── task 0 spikes ──────────────►│ message_conversion/derived │
                                    │ → ChatMessage/Task view    │
                                    └─────────────┬──────────────┘
                                                  ▼
                                    hardened gates + shared tooltip
                                    primitive (flag flips True here)
```

The Sculptor-side half (right of pi) is identical in shape for every
capability and is specified firmly in §4. The pi-side half (left) is the
verdict-dependent part: Sculptor-side-only / extension / version-bump
(permission-gated) / blocked→defer (REQ-INV-2).

### 3.2 Tranche graph

```
                    ┌────────────────────────────┐
                    │ BASE (one tranche, REQ-BASE)│
                    │ gates substrate + typed     │
                    │ protocol module             │
                    └──────────────┬─────────────┘
   TASK 0 (REQ-INV, parallel)      │ merges to main first
   feasibility.md verdicts ───────┐│
                                  ▼▼
   ┌───────────┬───────────┬───────────┬───────────┬──────────────┐
   │interrupt  │tool-render│ctx-reset  │compaction │session-resume│
   ├───────────┼───────────┼───────────┼───────────┼──────────────┤
   │backchannel│skills     │sub-agents │bg-tasks   │image+attach  │
   └───────────┴───────────┴───────────┴───────────┴──────────────┘
     11 REQ-CAPs; independent workspaces/MRs rooted on main;
     bundling allowed where plumbing is shared (REQ-PROC-4) —
     candidates: image-input + file-attachments (prompt assembly),
     context-reset ∥ session-resume (session lifecycle, but kept
     separable), backchannel covers AUQ + plan mode (one flag).
```

## 4. Component deep dives

### 4.1 Base tranche — frontend gate substrate (REQ-BASE-2..5)

**Twin tightening (REQ-BASE-2).** The generated `HarnessCapabilities` twin
appears to have no index signature (typos should already fail `tsc`); the
base tranche *verifies* this and locks it with a type-level negative test
(a deliberately bogus field read that must fail compilation), covering the
forward-compat question (older client ↔ new field) noted in requirements
Open Questions. If verification fails, fall back to a ratchet forbidding
`.harnessCapabilities.<field>` access outside `tasks.ts` atoms.
*Alternative considered:* runtime fail-closed default (`?? false` for pi) —
rejected in requirements Q&A; the `?? true` load-race default is retained
deliberately, since compile-time safety removes the typo path.

**The split (REQ-BASE-3).** `supports_context_reset` joins the model;
`supports_compaction` narrows to auto-compaction chrome. Both `True` for
Claude (pure refactor — no behavior change), `False` for pi. Because
`HarnessCapabilities` has no field defaults, pydantic forces every
constructor site (base, Claude, pi, fixtures) to take an explicit stance —
the grep-complete property is preserved.

**Substrate completion (REQ-BASE-4).** Five new atom/hook pairs in the
established `taskSupports<X>AtomFamily` + `useTaskSupports<X>` pattern:
context_reset, compaction, background_tasks, session_resume,
tool_use_rendering. Backend reads stay on typed `capabilities()`.

**Shared gating primitive (REQ-BASE-5).** One frontend primitive (hook +
thin wrapper) that consumes a narrow capability hook and yields one of:
*enabled* | *disabled + tooltip(standard copy) + stable ElementID*. All
~12 gated surfaces (including `supports_fast_mode`'s — presentation only)
migrate onto it; bespoke fallback (hiding) only where a surface can't host
a disabled state (e.g. a picker category that must not render). Copy
pattern is standardized once (e.g. "Not supported by the <harness>
harness"); ElementIDs are added per surface and regenerated into the
frontend types. *Alternative considered:* per-surface bespoke treatment —
rejected (Q&A): ~12 surfaces × 3 concerns (state, copy, test hook) would
drift.

**Dead-letter logging (REQ-BASE-6).** `PiAgent._push_message`'s reject
branch logs a warning naming the dropped message type. Replaced
incrementally by real handlers as tranches land.

### 4.2 Base tranche — typed pi protocol module (substrate)

A backend module under the pi agent package modeling the **documented**
wire unions (RPC §4 commands, §5 responses/session-events/extension-UI,
§7 streaming sub-events): parse-once at the dispatcher boundary, dispatch
on typed variants. Unknown `type`s remain tolerated (debug-log + ignore,
per RPC §5.3 forward-compat guidance). The dispatcher's three-lane split
(`response` / session event / `extension_ui_request`) becomes explicit in
types; `id`-correlation for responses (RPC §5.1 ordering caveat) is owned
here. Capability adapters consume typed events only.
*Alternative considered:* per-tranche ad-hoc typing — rejected: five-plus
tranches would each re-derive shapes from the protocol doc, eroding the
single ground truth and inviting drift.

### 4.3 Interruption — REQ-CAP-INTERRUPTION

Sculptor side (firm): `_push_message` accepts `InterruptProcessUserMessage`
→ send `abort` (id-correlated; known surface, RPC §4) → dispatcher treats
the following `agent_end` as the interrupted turn boundary → emit
`RequestSuccessAgentMessage(interrupted=True)` so the frontend's in-flight
message resolves (the contract Claude's interrupt path satisfies). The
turn-state machine gains an *aborting* state with an escalation ladder:
no `agent_end` within a grace window → SIGTERM (pi exits 143, RPC §3) →
process-exit fallback already handled by the dispatcher. Queued messages
remain **Sculptor-owned** (existing queue); pi's native `steer`/`follow_up`
queues are deliberately not adopted (YAGNI; no affordance reads them).
Flag flip + gate-state tests + `real_pi` mirror of `test_interrupts.py`.

**Probe checklist (task 0):** abort mid-stream leaves the session usable
for the next prompt? abort during tool execution — does the tool die?
`agent_end` content after abort (partial messages? `stopReason:
"aborted"`)? latency of abort→agent_end on a long generation?

### 4.4 Tool-use rendering — REQ-CAP-TOOL-RENDERING

Sculptor side (firm): an adapter in the pi output processor maps the
tool-execution lane (RPC §9) onto the existing harness-agnostic blocks:
`tool_execution_start{toolCallId,toolName,args}` → `ToolUseBlock` appended
to the in-progress assistant message (in-progress state visible);
`tool_execution_update` → replace accumulated `partialResult` (pi sends
accumulated output, not deltas — simpler than Claude's accumulator);
`tool_execution_end{result,isError}` → tool-result block. Mapping policy
(locked): pi's core file tools `read`/`edit`/`write`/`bash` map onto the
existing Read/Edit/Write/Bash renderers **with arg-shape adaptation in the
backend adapter**; all other pi tools render generically (name + args +
result). The `toolCall` content blocks that also appear inside assistant
messages (RPC §9) are reconciled so blocks are not rendered twice — the
tool-execution lane is authoritative for rendering. Diff refresh
(`tool_execution_end` → `on_diff_needed`) is unchanged. Divergence note
for the MR (REQ-CAP-ALL-3): Claude streams tool *input* deltas; pi shows
complete input at start — equivalent fidelity, different rhythm.

**Probe checklist:** exact arg schemas of the core four tools; size/
truncation behavior of `partialResult` on long outputs; event ordering
guarantees between `message_update`(toolcall_*) and `tool_execution_*`;
sub-agent-like tools present in default toolset?

### 4.5 Context reset — REQ-CAP-CONTEXT-RESET

Sculptor side (firm): handle `ClearContextUserMessage` → send
`new_session` (known surface, RPC §4 — no process restart needed) → emit
the same acknowledgment flow Claude's clear path produces, so the frontend
experience matches. Frontend: `/clear` pseudo-skill entry gates on the new
atom via the shared primitive. Backend: the clear endpoint gains a
capability guard following the `app.py:2078` precedent (4xx when
unsupported) — the API-level sibling of dead-letter logging, per
no-fail-open (REQ-CAP-ALL-4).

**Probe checklist:** does `new_session` genuinely clear context (verify
with an API key: prior-content question after reset)? does it reset model/
thinking selections or only history? interaction with in-flight streaming
(must reject or queue while streaming)?

### 4.6 Compaction — REQ-CAP-COMPACTION

Sculptor side (firm): adapter maps `compaction_start{reason}` /
`compaction_end{aborted,willRetry,errorMessage}` (known surface, RPC §5.2)
onto the existing `AutoCompactingAgentMessage` / `AutoCompactingDoneAgentMessage`
pair, lighting up the existing `is_auto_compacting` derivation
(`derived.py:278`) and StatusPill/TokenPopover chrome with no new frontend
machinery beyond the substrate atom. `compaction_end willRetry:true`
extends the turn rather than ending it (RPC §6 boundary-absence case —
encoded in the typed dispatcher's state machine). Scope stays
Claude-parity: **no** manual `/compact` surface is added (Sculptor has
none for Claude); pi's `compact` command and `set_auto_compaction` are
noted for feasibility but unconsumed this cycle.

**Probe checklist:** does threshold compaction actually fire in 0.78.0
defaults (and is `autoCompactionEnabled` on by default)? does any numeric
threshold exist to surface in TokenPopover's context row, or does that row
legitimately stay empty for pi (possible divergence note)? compaction
mid-turn vs between turns?

### 4.7 Session resume — REQ-CAP-SESSION-RESUME

Sculptor side (firm): this tranche owns flipping `--no-session` → a
managed `--session-dir` under the environment's state path (locked: run
behavior changes only in the owning tranche). Session identity
(`sessionFile`/`sessionId`, RPC §5.1 `get_state`) is persisted alongside
Sculptor's existing per-task state (the pattern Claude uses for its
session-id file). Resume flow: on agent restart, relaunch pi with the
managed session dir and re-attach to the prior session (`switch_session`
is the documented candidate, RPC §4 — exact mechanism is feasibility's
call), then handle `ResumeAgentResponseRunnerMessage` instead of dropping
it. The harness's polymorphic path helpers may expose the session dir for
diagnostics parity (optional, not load-bearing).

**Probe checklist:** does `switch_session` restore conversation context
such that the next prompt sees prior content? crash-mid-write resilience
of pi session files? session-file size growth over long conversations?
does `--session-dir` + `new_session` interact sanely with reset (4.5)?

### 4.8 Interactive backchannel — REQ-CAP-BACKCHANNEL

Sculptor side (firm): the contracts both interactions ride are already
harness-agnostic — `AskUserQuestionAgentMessage` out,
`UserQuestionAnswerMessage` back into the in-flight turn, the plan-mode
state machine messages, and the gated methods (`is_ask_user_question_tool`
etc.) overridden truthfully on `PiHarness` once the transport names exist.
The `app.py:2078` plan-mode guard flips automatically with the flag.
Transport is **deliberately unranked** (locked): pi's extension-UI dialog
lane (`extension_ui_request` ⇄ `extension_ui_response`, wire fully
documented at RPC §5.3/§4 — but extension *authoring* uncharacterized) vs
native MCP support (unknown) — task 0 decides; mechanism + the
extension-runtime-failure posture for this capability land in
feasibility.md (the posture decision is explicitly deferred past this
document — we don't yet know enough; leaning stays fail-loud-first).

**Probe checklist:** extension authoring API (how a bundled extension is
loaded for `--mode rpc`; what `ctx.ui.select/confirm/input/editor` offer);
dialog `timeout` semantics (RPC §5.3 auto-resolve) vs Sculptor's
unbounded-wait AUQ model; does pi support MCP servers natively; plan-mode
fit: can an extension or prompt-level convention express
plan-then-confirm?

### 4.9 Skills — REQ-CAP-SKILLS

Sculptor side (firm): the skills endpoint + `discover_skills` source
(repo/user/plugin dirs) stays the single list authority; picker source and
SkillsPanel gate via the substrate. The parity bar is the full
Claude-visible set (REQ-CAP-SKILLS). pi has a *native* skills concept
(`--no-skills` flag; `get_commands` returns command names with sources —
RPC §3/§4): whether pi's discovery can be pointed at the same sources, or
an extension/prompt-expansion is needed, is feasibility's call (recorded
leaning: pi-native hooks or extension; prompt-expansion is the fallback
candidate).

**Probe checklist:** pi's skill discovery rules (which directories? what
file format? does it read `.claude/skills`-style SKILL.md?); how a skill
is invoked over RPC (slash text in `prompt`? a command?); does
`get_commands` enumerate discovered skills; can discovery dirs be
injected per-launch?

### 4.10 Sub-agents & background tasks — REQ-CAP-SUB-AGENTS, REQ-CAP-BACKGROUND-TASKS

These two have **no visible surface in the documented protocol** (RPC §5
event union contains no sub-agent or background-task vocabulary) — the
highest-probability deferral candidates (REQ-CAP-ALL-6 path). Sculptor
side (firm, stated for completeness): sub-agent rendering rides
`parent_tool_use_id` attribution in the existing ChatMessage contract;
background tasks ride the `BackgroundTaskStartedAgentMessage` /
`BackgroundTaskNotificationAgentMessage` pair. If task 0 finds no
extension-expressible mechanism, both defer with fail-closed gates and
FOLLOWUPS blocks (REQ-PROC-7).

**Probe checklist:** can an extension spawn a nested pi (or task) and
surface its lifecycle as events? does pi's toolset include anything
backgroundable (long-running bash semantics)? any roadmap surface in the
pinned version worth noting for the FOLLOWUPS entry?

### 4.11 Image input & file attachments — REQ-CAP-IMAGE-INPUT, REQ-CAP-FILE-ATTACHMENTS

Natural bundle (shared prompt-assembly plumbing; REQ-PROC-4). Sculptor
side (firm): `ChatInputUserMessage.files` (upload-path file paths — the
existing harness-agnostic transport) stops being dropped by pi's prompt
assembly. Attachments: file paths are presented to pi with the prompt the
same way Claude's prompt assembly presents them (pi reads files with its
own tools — `supports_file_references` already proves the loop). Images:
the `prompt` command's documented `images: ImageContent[]` field (base64 +
mimeType, RPC §4) carries image files read from the upload path.
Harness-level `supports_image_input` flips when transport works
end-to-end on capable models (locked); when the selected model can't
accept images, the turn's failure surfaces as a **runtime error** through
the standard failed-turn path, with a code comment marking the gating for
later hoisting (no model-capability wiring this cycle).

**Probe checklist:** does a text-only model **error** on `images[]` (the
acceptable path) or silently ignore them (would violate no-silent-drop —
needs a pre-send guard; check what `get_available_models` exposes about
multimodality)? size limits on base64 payloads over stdin JSONL? do
attachments-by-path satisfy "usable that turn" for large files?

## 5. Data model changes

- **`HarnessCapabilities`** (backend + generated TS twin): +1 field
  (`supports_context_reset`); `supports_compaction` semantics narrowed.
  No-defaults policy forces explicit stances at every constructor
  (intended; grep-complete).
- **No database/schema migration.** Capabilities are computed per task
  view (`derived.py:381`), never persisted; the wire change is additive.
- **No new agent-message types.** Every capability reuses the existing
  harness-agnostic contracts (ToolUseBlock, AutoCompacting*,
  AskUserQuestion*, BackgroundTask*, RequestSuccess(interrupted), …) —
  by design: degraded→rich is adapter work, not contract work (north star
  §2).
- **ElementIDs:** new stable IDs for each tooltip-upgraded surface
  (regenerated types; REQ-BASE-5).
- **`UserConfig`:** untouched. No user-facing capability toggles.

## 6. Migration strategy

No data migration. Rollout is per-tranche flag flips, each a one-line
`PiHarness.capabilities()` change riding its tranche's machinery, plus the
wire-additive split in the base tranche. Old frontend + new backend (and
inverse) tolerate the additive field; the twin-tightening probe
(REQ-BASE-2 / Open Q4 in requirements) confirms the older-client story
before the tightening ships.

## 7. Code removal plan

- `CAPABILITY-GAP:` markers removed by the tranche that resolves each
  (REQ-CAP-ALL-5); the base tranche re-homes markers whose surfaces it
  migrates onto the shared primitive.
- Dead-letter warn-and-drop branches in `_push_message` are deleted
  per-tranche as real handlers land (interrupt → 4.3, clear → 4.5,
  resume → 4.7, answer → 4.8).
- The raw-dict event dispatch in the pi output processor is subsumed by
  the typed protocol module (4.2) — the old `.get()` paths are removed,
  not kept alongside.

## 8. Files appendix (Sculptor-side; per tranche)

| Tranche | Modify | Create |
| --- | --- | --- |
| BASE (gates) | `interfaces/agents/harness.py` (split), `agents/{default,pi_agent}/harness.py` + capability fixtures, `frontend/src/common/state/atoms/tasks.ts` (+5 atoms/hooks), gated surfaces (`ChatInput.tsx`, `StatusPill.tsx`, `QueuedMessageBar.tsx`, `SkillsPanel.tsx`, `AlphaToolGroup.tsx`, `MentionPickerList.tsx`, `Editor.tsx`, `TipTapConfig.ts`, `TokenPopoverContent.tsx`), ElementIDs + regenerated types, `agents/pi_agent/agent_wrapper.py` (dead-letter) | shared gating primitive (frontend component/hook), type-level twin test (or ratchet rule) |
| BASE (protocol) | `agents/pi_agent/agent_wrapper.py` (dispatcher rewires), `agents/pi_agent/output_processor.py` | typed protocol module under `agents/pi_agent/` |
| interruption | `agent_wrapper.py` (+abort flow, turn-state), `pi_agent/harness.py` (flag), `testing/fake_pi.py` (+directives) | `real_pi/test_interrupts.py` |
| tool rendering | `output_processor.py` (+adapter, mapping), `harness.py` (flag), `fake_pi.py` | `real_pi/test_tool_calls.py` |
| context reset | `agent_wrapper.py` (+new_session), `web/app.py` (clear guard), `harness.py`, `fake_pi.py`, frontend `/clear` gate | `real_pi/test_clear_context.py` |
| compaction | `output_processor.py` (+compaction adapter), `harness.py`, `fake_pi.py` | `real_pi/test_compaction.py` |
| session resume | `agent_wrapper.py` (session-dir, resume flow, state persistence), `harness.py`, `fake_pi.py` | `real_pi/test_session_resume.py` |
| backchannel | `agent_wrapper.py` (transport per verdict), `pi_agent/harness.py` (gated methods + flag), `fake_pi.py` (+ui-request directives) | extension source under `agents/pi_agent/extensions/` (if verdict (ii)), `real_pi/test_ask_user_question.py`, `real_pi/test_plan_mode.py` |
| skills | per verdict (launch args / extension / prompt assembly), `harness.py`, frontend picker gates | `real_pi/test_skills.py` |
| sub-agents / bg-tasks | per verdict or defer (fail-closed gates + FOLLOWUPS) | `real_pi/` mirrors if delivered |
| image+attach | `agent_wrapper.py` (prompt assembly: files + images), `harness.py` (flags) | `real_pi/test_image_input.py`, `real_pi/test_file_attachments.py` |

(Exact per-file line targets belong to the implementation plan; this table
is the traceable Sculptor-side footprint.)

## 9. Testing strategy

```
 unit            integration (deterministic)         real (stochastic)
 ─────           ───────────────────────────         ─────────────────
 protocol module  fake_pi-driven UI tests:            real_pi/ mirrors of
 parsing/adapters  - gate-state per surface           real_claude/ per
 dead-letter       (False→hidden/disabled+tooltip,    capability; full
 arg mapping        True→functional)  REQ-TEST-4      suite green at every
                   - per-capability behavior via       merge (REQ-TEST-2),
                     new fake_pi directives            rerun tolerance as
                                                       for real-claude
```

- **fake_pi grows one directive family per capability** (tool events,
  compaction events, ui-requests, session files, …) — append-only, so
  parallel tranches rarely conflict.
- **`real_pi` mirrors `real_claude`** test-for-test where the capability
  corresponds (REQ-TEST-1): interrupts, tool_calls, clear_context,
  ask_user_question, plan_mode, background_tasks; divergences justified in
  the MR.
- **Claude flows this cycle puts at risk** (META_PLAN obligation), and how
  they stay green: (1) shared chat-input surfaces and pickers touched by
  the tooltip migration — covered by the existing frontend integration
  suite plus new gate-state tests asserting Claude (all-True) renders
  enabled/unchanged; (2) `HarnessCapabilities` constructor sites — the
  no-defaults policy turns any miss into a type/test failure on a single
  deterministic run; (3) the `app.py` capability guards on shared
  endpoints — guarded paths are no-ops for Claude (capabilities all True)
  and unit-tested both ways; (4) `real_claude/` itself is untouched and
  must stay green on a rerun per tranche (REQ-TEST-3). No Claude-side
  process, prompt, or session machinery is modified anywhere in the
  cycle.

## 10. North-star check (PHASE_6_NORTH_STAR §2–§3)

- **Capability shapes preserved:** bool fields on `HarnessCapabilities` +
  gated methods on the harness — no new advertisement mechanism invented;
  the dynamic/backend-declared evolution stays phase 6.
- **The split is the anticipated evolution** ("fields become finer as
  concrete differences surface") — granularity grows, shape doesn't.
- **Minimum interface unchanged:** turn-boundary signalling and structured
  failure were already satisfied by pi; everything this cycle adds is
  capability, not minimum (file-change signalling stays per-harness
  wiring, as decided in pi-basic).
- **Tool rendering = pure adapter improvement** with no contract or data
  migration — exactly the degraded→rich path §2 promised.
- **Backchannel stays a capability** delivered (if feasible) via pi's
  internal plugin set (§5: plugins immutable, Sculptor-curated, not
  user-facing — REQ-EXT matches).
- **Tripwires respected:** no permission/safety UI is introduced; the
  `can_use_tool` door stays open. `enable_multi_harness` untouched
  (decoupled from graduation). Conformance grows per §3; graduation
  remains the human call (REQ-PROC-9).

## 11. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Parallel tranches conflict on `PiHarness.capabilities()`, fixtures, `fake_pi` | One-line stances + append-only directive families; trivial rebases; REQ-PROC-1 sequencing only where real |
| Twin tightening breaks older-client forward-compat | Verify-first posture + ratchet fallback (REQ-BASE-2); probe in base tranche before relying on it |
| `abort` semantics differ from docs empirically | Probe checklist 4.3 runs before the interruption tranche commits; escalation ladder bounds the damage either way |
| pi session files grow unbounded / break across version bumps | Resume tranche owns `--session-dir`; growth probed (4.7); any version bump is permission-gated (REQ-PROC-5) and re-validates sessions |
| Extension authoring proves hard/unstable (backchannel, skills, sub-agents) | Verdict taxonomy routes to defer-with-FOLLOWUPS rather than forcing; extension-failure posture deliberately deferred until mechanisms exist |
| `images[]` silently ignored by text-only models | Probe 4.11; if silent, a pre-send guard is required before the flag flips (no-silent-drop is the REQ bar) |
| `real_pi` suite runtime grows (serial) | Accepted; full-suite-at-merge keeps cross-tranche regressions visible (REQ-TEST-2) |

## 12. Open questions → owners

1. **Per-capability pi-side mechanisms** → task 0 / `feasibility.md`
   (REQ-INV-2), guided by the probe checklists in §4.
2. **Extension runtime-failure posture** → deferred past this document
   (insufficient knowledge until mechanisms exist); per-capability call in
   feasibility addenda; leaning fail-loud-first.
3. **Twin-tightening forward-compat** → base tranche verification
   (REQ-BASE-2).
4. **Image-input model-capability hoisting** → marked in code this cycle;
   future cycle wires real per-model gating.
