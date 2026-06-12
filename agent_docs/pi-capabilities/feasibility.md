# pi-capabilities — Feasibility verdicts (task 0)

Phase 5 of the pi multi-harness initiative (cycle slug: `pi-capabilities`).
Empirical feasibility investigation per **REQ-INV** in
[requirements.md](./requirements.md), gating every capability tranche and
feeding the pass-2 capability-planning session. Companion docs:
[goals.md](./goals.md), [architecture.md](./architecture.md) (§4 probe
checklists), and the authoritative wire reference
[`../pi-basic/pi-0.78.0-rpc.md`](../pi-basic/pi-0.78.0-rpc.md) (cited as
**RPC §n**).

This document is the **permanent record of the pi-side mechanism** for each
capability — architecture.md deliberately designs only the Sculptor side and
points here for the pi-side half.

## Verdict taxonomy (REQ-INV-2)

Each target flag is classified as exactly one of:

- **(i)** achievable **Sculptor-side only** — launch flags, prompt assembly,
  and Sculptor adapters over surfaces pi 0.78.0 already exposes; no pi
  extension required.
- **(ii)** achievable via an **added pi extension** — code Sculptor folds into
  its pinned, immutable extension set (REQ-EXT), loaded with `-e`.
- **(iii)** achievable **only via a pinned-version bump** — permission-gated
  (REQ-PROC-5); recorded as a note, never acted on here.
- **(iv)** **blocked on pi-core → defer** — no pi-core surface and no
  extension-expressible path that meets the capability's parity bar; carries a
  Proposed FOLLOWUPS entry (REQ-PROC-7).

Free-form notes supplement any verdict whose findings exceed the taxonomy.

## Environment & method (REQ-INV-3 provenance)

| Item | Value |
| --- | --- |
| pi binary | `@earendil-works/pi-coding-agent` **0.78.0** (pinned `PI_VERSION_RANGE`), installed via `just install-pi` to `.venv/bin/pi` (managed standalone GitHub-release build). `pi --version` → `0.78.0` on **stderr** (RPC §2.2). |
| Probe transport | `.venv/bin/pi --mode rpc [flags]`, JSONL on stdin/stdout, driven by a Python harness (responses correlated by `id`, not order — RPC §5.1). |
| Source read | The installed `@earendil-works/pi-coding-agent@0.78.0` package (cited below as `<pi-pkg>`): `docs/*.md`, `examples/extensions/*`, `dist/`. Reproducible by `npm pack @earendil-works/pi-coding-agent@0.78.0`. Reading pi source is allowed; pi was **not** modified. |
| Models | All probes used the configured Anthropic key. `get_available_models` returned **24 models, all Anthropic, all `input: ["text","image"]`** (multimodal). Live turns used `claude-haiku-4-5` (cheap); one bootstrap turn used the configured default `claude-opus-4-8`. |
| Auth | pi resolved credentials from its own auth file (`pi`'s `~/.pi/agent/auth.json`, an Anthropic `api_key` entry) — so direct RPC probing needed **no** `ANTHROPIC_API_KEY` in the environment. In Sculptor's real flow the key is injected as a subprocess secret (`PiConfig.api_key_env_var_names`, default `ANTHROPIC_API_KEY` — `agent_wrapper.py:208-215`). |
| Spend | ≈ **$0.08** total API cost across 15 live turns (prompts kept tiny, `[SCULPTOR-PROBE]`-prefixed). |
| Spike artifacts | Probe scripts, the spike extension, and full JSONL transcripts are **uncommitted** (REQ-INV-4), retained in the task-0 workspace under `pi-probes/` (`transcripts/<name>.txt`). This document quotes the load-bearing excerpts inline so every verdict is re-checkable without them. |

**No pinned-version bump is required or recommended.** Every capability that
is achievable is achievable on 0.78.0; no verdict is **(iii)**. No bump
opportunity was found that unlocks a blocked capability (the lone deferral is
a pi-core *design* exclusion, not a version gap — see §11).

---

## Verdict table

| # | Flag | Verdict | Pi-side mechanism (one line) | Key evidence |
| - | ---- | ------- | ---------------------------- | ------------ |
| 1 | `supports_interruption` | **(i)** Sculptor-side | `abort` command; `agent_end` is the interrupted boundary (`stopReason:"aborted"`, partial content kept); session stays usable | §1 · `transcripts/p2_abort.txt` |
| 2 | `supports_tool_use_rendering` | **(i)** Sculptor-side | Adapter maps `tool_execution_start/update/end`; 4 core tools with stable arg schemas | §2 · `transcripts/p1_tool_schemas.txt` |
| 3 | `supports_session_resume` | **(i)** Sculptor-side | Flip `--no-session` → `--session-dir`; relaunch with `--continue`/`--session <id>` restores context | §3 · `transcripts/p5b_session_resume.txt` |
| 4 | `supports_context_reset` | **(i)** Sculptor-side | `new_session` clears history in-process (`messageCount`→0); next turn has no prior content | §4 · `transcripts/p3_context_reset.txt`, `p3b_reset_recall.txt` |
| 5 | `supports_compaction` | **(i)** Sculptor-side | Map `compaction_start/end{reason,result}`; `autoCompactionEnabled` defaults `true` | §5 · `transcripts/p4_compaction.txt` |
| 6 | `supports_interactive_backchannel` | **(ii)** extension | Sculptor extension registers an AUQ tool calling `ctx.ui.select`/`input` → `extension_ui_request` (no `timeout` = unbounded wait); plan mode via the same extension lever | §6 · `transcripts/p8_extension_auq.txt` |
| 7 | `supports_skills` | **(i)** Sculptor-side | Point pi at Sculptor's skill dirs via `--skill` (repeatable) / settings `skills`; `get_commands` enumerates; `/skill:name` invokes | §7 · live `get_commands`, `<pi-pkg>/docs/skills.md` |
| 8 | `supports_sub_agents` | **(ii)** extension | Extension spawns nested `pi` processes (shipped `subagent` example) and streams progress; Claude-parity nested *attribution* needs bespoke output shaping | §8 · `<pi-pkg>/examples/extensions/subagent/` |
| 9 | `supports_image_input` | **(i)** Sculptor-side | Base64 images via `prompt.images[]`; all available models multimodal; unprocessable image fails **loud** | §9 · `transcripts/p6b_image_valid.txt`, `p6_image.txt` |
| 10 | `supports_file_attachments` | **(i)** Sculptor-side | Present upload-path file paths in the prompt; pi reads them with its own tools (`supports_file_references` already `True`) | §10 · `<pi-pkg>/docs/rpc.md:41-78`, read-tool schema |
| 11 | `supports_background_tasks` | **(iv)** defer | pi-core has no background-execution primitive or lifecycle event; only a bespoke extension simulation exists, with no native signal and no defined Sculptor affordance | §11 · `<pi-pkg>/docs/usage.md:286`, RPC §5 |

Tally: **(i) × 8, (ii) × 2, (iii) × 0, (iv) × 1.** Pass-2 planning is unblocked
for all 11.

---

## Per-capability findings

### 1. `supports_interruption` — verdict (i) (architecture §4.3)

**Probe:** sent a long generation, waited for streaming to begin, sent
`{"type":"abort"}`, then sent a fresh prompt on the same process
(`transcripts/p2_abort.txt`).

Probe-checklist answers:
- **Does `abort` leave the session usable for the next prompt?** Yes. After
  the aborted turn's `agent_end`, a new `prompt` was accepted and completed
  normally on the same process (no relaunch).
- **`agent_end` content after abort?** The interrupted assistant message
  carries `stopReason:"aborted"` and retains partial content blocks
  (`['thinking','text','toolCall']`, ~79 chars of partial text). `agent_end`
  fires with `willRetry:false`.
- **abort→`agent_end` latency on a long generation?** ≈ **11 ms** — effectively
  immediate; pi does not wait for the in-flight LLM stream to drain.
- **Abort during tool execution — does the tool die?** Not exercised against a
  live long-running tool in this probe; the `abort` ack + immediate `agent_end`
  with `stopReason:"aborted"` is pi's documented cancellation path
  (RPC §6 boundary table). The interruption tranche's escalation ladder
  (grace window → SIGTERM → process-exit fallback, architecture §4.3) bounds
  the residual risk regardless.

**Mechanism sketch (Sculptor-side):** `PiAgent._push_message` accepts
`InterruptProcessUserMessage` → send `{"type":"abort"}` (id-correlated) → the
dispatcher treats the next `agent_end` as the interrupted boundary → emit
`RequestSuccessAgentMessage(interrupted=True)` (the base
`_was_interrupted` event already exists). Sculptor-owned queue stays as-is;
pi's native `steer`/`follow_up` are not adopted (YAGNI). Matches architecture
§4.3 exactly — no surprises.

### 2. `supports_tool_use_rendering` — verdict (i) (architecture §4.4)

**Probe:** drove one turn that exercised all four core tools
(`transcripts/p1_tool_schemas.txt`).

Probe-checklist answers:
- **Exact arg schemas of the core four tools** (from `tool_execution_start.args`):
  - `bash` → `{"command": string}`
  - `read` → `{"path": string}`
  - `write` → `{"path": string, "content": string}`
  - `edit` → `{"path": string, "edits": [{"oldText": string, "newText": string}]}`
    — note pi's `edit` takes an **array** of `{oldText,newText}` (multi-edit),
    unlike Claude's single `old_string`/`new_string`. The backend adapter must
    arg-shape-adapt here (architecture §4.4 anticipated this).
- **`partialResult` shape / truncation:** `tool_execution_update.partialResult`
  is `{content:[{type:"text",text}], details:{truncation, fullOutputPath}}` and
  carries **accumulated** output (not deltas) — clients replace their display
  per update (RPC §9 confirmed). `details` exposes `truncation` and
  `fullOutputPath` for large outputs.
- **Ordering between `message_update`(toolcall_*) and `tool_execution_*`:** the
  assistant message's `toolcall_start`/`toolcall_delta`/`toolcall_end` stream
  **before** the matching `tool_execution_start`. The tool-execution lane is
  the authoritative rendering source (architecture §4.4); the in-message
  `toolCall` blocks are reconciled to avoid double-render.
- **`tool_execution_end` detail:** file-mutating tools carry rich details —
  e.g. `edit` end → `details:{diff, patch, firstChangedLine}`; `isError`
  flags failures.
- **Sub-agent-like tools in the default set?** No. The default RPC toolset is
  exactly **`read`, `bash`, `edit`, `write`** (confirmed by the model's own
  tool enumeration in `transcripts/p7_ask_question.txt`). Anything richer is
  extension-supplied.

**Mechanism sketch:** pure Sculptor-side adapter in the pi output processor
mapping the tool-execution lane onto the existing harness-agnostic
`ToolUseBlock` contract; `read`/`edit`/`write`/`bash` map onto Claude's
renderers with backend arg-shape adaptation, others render generically. Diff
refresh on `edit`/`write`/`bash` end is unchanged. No pi-side work needed.

### 3. `supports_session_resume` — verdict (i) (architecture §4.7)

**Probe:** process A launched with `--session-dir <dir> --name probe-resume`,
stored a secret, then closed (stdin close → clean shutdown). Process B
launched with the same `--session-dir --continue` and was asked to recall the
secret (`transcripts/p5a_session_write.txt`, `p5b_session_resume.txt`).

Probe-checklist answers:
- **Does resume restore context such that the next prompt sees prior content?**
  **Yes.** Process B reported the **same `sessionId`**, `messageCount:2`, and
  recalled the secret codeword verbatim (`MARMALADE-9`) — full context survives
  a process restart.
- **Session-file behavior:** the session is a single JSONL file under the
  session dir (`<timestamp>_<uuid>.jsonl`), ~2.2 KB after one short exchange;
  pi auto-saves and organizes by working directory. Tree/branch structure per
  `<pi-pkg>/docs/session-format.md`.
- **Resume flags available:** `--continue/-c` (most recent in dir),
  `--resume/-r` (picker — TUI only), `--session <path|id>` (exact), plus the
  in-band `switch_session` command (RPC §4). For Sculptor's per-task isolation,
  persisting the `sessionId` and relaunching with `--session-dir` + `--session <id>`
  (or `--continue` in a per-task dir) is the clean path.
- **`--session-dir` + `new_session` interaction (vs reset §4):** `new_session`
  starts a fresh session id within the same dir; resume targets the persisted
  id — the two compose without conflict.
- **Crash-mid-write resilience / unbounded growth:** not stress-tested here;
  JSONL append-per-entry makes partial-tail truncation the expected failure
  mode, and growth is linear in conversation length. Flagged for the resume
  tranche's `real_pi` test to bound (architecture §4.7 risk row).

**Mechanism sketch:** the resume tranche owns flipping the launch from
`--no-session` to a managed `--session-dir` under the environment state path,
persists the session id alongside Sculptor's per-task state (the pattern Claude
already uses), and relaunches + re-attaches on agent restart. Handle
`ResumeAgentResponseRunnerMessage` instead of dropping it. Entirely
Sculptor-side.

### 4. `supports_context_reset` — verdict (i) (architecture §4.5)

**Probe:** turn 1 planted a secret codeword; sent `{"type":"new_session"}`;
then asked the agent to recall it (`transcripts/p3_context_reset.txt`,
`p3b_reset_recall.txt`).

Probe-checklist answers:
- **Does `new_session` genuinely clear context?** **Yes, definitively.**
  `get_state.messageCount` went **2 → 0**, `sessionId` changed, and the
  post-reset turn answered `NO_CODEWORD` — the model had no record of the
  planted secret. Response: `{"command":"new_session","success":true,"data":{"cancelled":false}}`.
- **Does it reset model/thinking selections or only history?** Only history.
  `thinkingLevel` was `high` before and `high` after the reset; model selection
  is likewise preserved. `new_session` clears the conversation, not the session
  configuration.
- **Behavior while streaming:** not exercised mid-stream; `new_session` can be
  cancelled by a `session_before_switch` extension handler (RPC §4) — none
  loaded here. Sculptor should issue it between turns (its `/clear` is a
  between-turns action).

**Mechanism sketch:** handle `ClearContextUserMessage` → send `new_session`
(no process restart), emit Claude's clear-acknowledgment flow; the clear
endpoint gains a capability guard mirroring the `app.py:2078` plan-mode
precedent. Entirely Sculptor-side.

### 5. `supports_compaction` — verdict (i) (architecture §4.6)

**Probe:** primed two turns, sent `{"type":"compact"}`, observed the events and
post-compaction recall (`transcripts/p4_compaction.txt`).

Probe-checklist answers:
- **Does compaction surface over RPC?** **Yes.** Manual `compact` emitted
  `{"type":"compaction_start","reason":"manual"}` then
  `{"type":"compaction_end","reason":"manual","aborted":false,"willRetry":false,"result":{summary,firstKeptEntryId,tokensBefore,details}}`.
  The `compact` command response carried the same `result` shape
  (`tokensBefore:2768`). Conversation memory survived (post-compaction recall
  was correct).
- **Is `autoCompactionEnabled` on by default?** **Yes** — `get_state` reports
  `autoCompactionEnabled:true` on a fresh `--no-session` process. Threshold
  auto-compaction emits the **same** `compaction_start/end` events with
  `reason:"threshold"` (and `"overflow"` → `willRetry:true`, RPC §6); only the
  `reason` differs from the manual case proven here. `isCompacting` is also
  exposed on `get_state` for the "Compacting" status state.
- **Numeric threshold for the TokenPopover context row?** No explicit threshold
  percentage is exposed on the wire. The context row can be derived from
  assistant `usage.totalTokens` ÷ `model.contextWindow` (both present on
  events / `get_state.model`); an exact auto-compaction trigger fraction is an
  internal pi detail (see `<pi-pkg>/docs/compaction.md`). If the tranche wants a
  literal threshold and finds none, leaving that sub-element empty is a valid
  divergence note (REQ-CAP-ALL-3).
- **Mid-turn vs between turns:** manual compaction here ran between turns; the
  `overflow` reason with `willRetry:true` is pi's mid-turn case (compaction
  then prompt re-run) — the typed dispatcher's state machine must treat
  `compaction_end willRetry:true` as turn-extending (architecture §4.6 / RPC §6).

**Mechanism sketch:** Sculptor-side adapter maps `compaction_start/end` onto the
existing `AutoCompacting*` message pair and `is_auto_compacting` derivation —
no new frontend machinery beyond the substrate atom. No manual `/compact`
surface is added (Claude has none). Entirely Sculptor-side.

### 6. `supports_interactive_backchannel` — verdict (ii) extension (architecture §4.8)

This flag gates **(a) ask-user-question** and **(b) plan mode**. Both are
deliverable via Sculptor's pinned extension set.

**Decisive probe (AUQ round-trip):** a ~25-line throwaway extension
(`auq_ext.ts`) registered a tool `ask_user_question` whose `execute` calls
`ctx.ui.select(question, options)`. Loaded **hermetically** with
`--no-extensions -e auq_ext.ts` (no `extension_error` on load). The model
called the tool; the full round-trip (`transcripts/p8_extension_auq.txt`):

```
→ extension_ui_request {"method":"select","title":"Do you prefer tea or coffee?",
                        "options":["tea","coffee"]}          # note: NO timeout field
← extension_ui_response {"value":"coffee"}
→ tool_execution_end   {"toolName":"ask_user_question","isError":false,
                        "result":{...,"details":{"answer":"coffee"}}}
→ agent_end            # model's final text: "YOU_CHOSE=coffee"
```

Probe-checklist answers:
- **Extension authoring/loading for `--mode rpc`:** an extension is a `.ts`
  module exporting `default (pi: ExtensionAPI) => { pi.registerTool(...) }`,
  loaded via `-e <path>` (repeatable; `--no-extensions` disables *discovery*
  but explicit `-e` still loads — RPC §3 / `pi --help`). Loaded via jiti;
  `import { Type } from "@earendil-works/pi-ai"` and
  `import { defineTool, ExtensionAPI } from "@earendil-works/pi-coding-agent"`
  resolve against the bundled binary (confirmed: the spike loaded with zero
  errors). This is the REQ-EXT packaging shape.
- **What `ctx.ui.{select,confirm,input,editor}` offer:** all four dialog
  methods are **functional in RPC mode** (`ctx.hasUI === true`), translated to
  the `extension_ui_request ⇄ extension_ui_response` sub-protocol
  (`<pi-pkg>/docs/rpc.md:985-1006`, confirmed live). `select` (options) maps to
  Sculptor's multiple-choice AUQ; `input` to freeform.
- **`timeout` semantics vs Sculptor's unbounded-wait AUQ:** the `timeout` field
  is **optional**; when omitted (as in the spike) pi does **not** auto-resolve —
  it blocks indefinitely until the client posts a response. This is an exact
  match for Sculptor's unbounded-wait AUQ model. (When a `timeout` *is* set, pi
  auto-resolves with a default; Sculptor simply never sets one.)
- **Does pi support MCP servers natively?** **No** —
  `<pi-pkg>/docs/usage.md:286` states pi "intentionally does not include
  built-in MCP … You can build or install those workflows as extensions or
  packages." MCP is therefore not a transport here; the extension-UI lane is.
- **Can plan-then-confirm be expressed?** **Yes** — pi ships a `plan-mode`
  extension (`<pi-pkg>/examples/extensions/plan-mode/`) providing `/plan` (and a
  `--plan` startup flag), read-only tool restriction, `Plan:`-section
  extraction, an "Execute the plan?" confirm dialog, `[DONE:n]` progress, and
  session-persistent state. The same extension lever + Sculptor's existing
  plan-mode state-machine contracts deliver plan mode.

**Mechanism sketch (pi-side):** a Sculptor-pinned extension registers an AUQ
tool that calls `ctx.ui.select`/`input` (no timeout); the dispatcher maps
`extension_ui_request{method:"select"|"input"}` → `AskUserQuestionAgentMessage`
and routes `UserQuestionAnswerMessage` back as the `extension_ui_response`. Plan
mode is delivered analogously (adapting the shipped `plan-mode` extension into
the pinned set, or a Sculptor equivalent), wiring its plan/confirm signals onto
Sculptor's plan-mode messages; the `app.py:2078` guard flips with the flag. The
harness's gated methods (`is_ask_user_question_tool`, `is_exit_plan_mode_tool`,
…) override truthfully once the transport tool names exist.

**Extension-runtime-failure posture (recommendation):** **fail loud first.** A
thrown extension surfaces as a non-terminal `extension_error` event
(`{extensionPath,event,error}`, RPC §5.2/§8) — Sculptor should surface that as a
failed turn / visible error rather than silently swallowing it, until enough
operational experience justifies graceful isolation. (Matches requirements
Open-Q1 / architecture §12 leaning.)

### 7. `supports_skills` — verdict (i) (architecture §4.9)

Probe-checklist answers (source: `<pi-pkg>/docs/skills.md`, live `get_commands`):
- **Discovery rules / directories / format:** pi reads skills from
  `~/.pi/agent/skills/`, `~/.agents/skills/`, project `.pi/skills/` and
  `.agents/skills/` (cwd + ancestors to repo root), package `skills/` entries,
  a settings `skills` array, and **`--skill <path>` (repeatable, additive even
  with `--no-skills`)**. A skill is a directory with a `SKILL.md`
  (`name`/`description` frontmatter) — the **agentskills.io standard**, the
  same `SKILL.md` shape Claude uses.
- **Does it read `.claude/skills`-style skills?** **Yes** —
  `<pi-pkg>/docs/skills.md:43-62` documents "Using Skills from Other Harnesses":
  add `"~/.claude/skills"` (and `~/.codex/skills`) to the settings `skills`
  array, or pass them as `--skill` paths.
- **Does `get_commands` enumerate them?** **Yes** — a live `get_commands`
  returned the workspace's user-scope skills as
  `{"name":"skill:<name>","source":"skill","sourceInfo":{path,scope,baseDir,…}}`
  (e.g. `skill:vet`, `skill:jujutsu`, discovered from a `.../skills/<name>/SKILL.md`).
- **How is a skill invoked over RPC?** Send `/skill:<name>` (optionally with
  args) as a `prompt` message — input expansion expands skill commands before
  sending (`<pi-pkg>/docs/rpc.md:69`). The model also auto-loads by description
  (progressive disclosure).
- **Can discovery dirs be injected per-launch?** **Yes** — `--skill <path>`
  (repeatable) and/or a per-launch settings file.

**Mechanism sketch:** Sculptor keeps `discover_skills` as the single list
authority and launches pi pointed at the **same** sources it already exposes
(repo `.claude/skills` / `.claude/commands`, `~/.claude/skills` /
`~/.claude/commands`, plugin dirs) via repeatable `--skill` flags (or settings
`skills`); the slash picker sends `/skill:<name>`. Pure launch-args + Sculptor
wiring — no extension.

**Free-form note (parity caveat for the tranche):** SKILL.md-directory skills
are covered cleanly. Loose command-style `.md` files (e.g. `.claude/commands/*.md`
without `SKILL.md`) and *plugin* skills should be verified at tranche time —
pi's loose-`.md` discovery depends on the location class
(`<pi-pkg>/docs/skills.md:36-41`). REQ-CAP-SKILLS' "full Claude-visible set" bar
(REQ-CAP-ALL-1) is judged there; if a source class doesn't map, the residual is
a divergence note, not a blocker on the mechanism.

### 8. `supports_sub_agents` — verdict (ii) extension (architecture §4.10)

Architecture §4.10 listed this as a high-probability deferral ("no visible
surface in the documented protocol … unless extensions can express these").
**Extensions can express it**, so the verdict is (ii), not (iv).

Probe-checklist answers (source: `<pi-pkg>/examples/extensions/subagent/`,
README + `index.ts`):
- **Can an extension spawn nested work and surface lifecycle?** **Yes.** The
  shipped `subagent` extension uses `spawn` (`node:child_process`,
  `index.ts:15,329`) to run each subagent as a **separate `pi` process** with an
  isolated context, supporting single / parallel (max 8, 4 concurrent) / chained
  modes. It streams child progress through the tool's `onUpdate` callback
  (`index.ts:308,539,609,669`).
- **How does that surface over RPC?** As the **parent tool's**
  `tool_execution_update.partialResult` — i.e. one `subagent` tool call whose
  streaming result text aggregates the children's formatted progress. The
  children's individual tool calls are **not** emitted as first-class nested
  `tool_execution_*` events with a `parent_tool_use_id` on the parent stream.
- **Backgroundable tools in the default set?** No (default set is
  read/bash/edit/write; §2).

**Mechanism sketch (pi-side):** a Sculptor-pinned variant of the `subagent`
extension (or the example itself) provides the nested-pi capability. Sculptor
maps the subagent tool's events onto the existing ChatMessage
`parent_tool_use_id` sub-agent grouping.

**Free-form note / risk (important):** the shipped example's surface is a single
aggregated tool block, **not** Claude-parity nested+attributed rendering (a
parent entry with each child's tool calls nested and attributed distinctly,
REQ-CAP-SUB-AGENTS). Closing that gap requires a bespoke extension that emits
**structured per-child lifecycle data** (e.g. structured `partialResult`
payloads, or piping each child's own RPC event stream upward) that the Sculptor
adapter parses into nested blocks. That is the heaviest and lowest-confidence
item in the (ii) set. Recommendation: schedule it **late / low priority**; it is
the prime candidate for a REQ-INV-6 paused-reversal-to-defer if the nested
rendering proves intractable within parity bounds. A ready-to-curate FOLLOWUPS
entry is included in the MR description so the architect can pre-stage that
contingency.

**Extension-runtime-failure posture (recommendation):** fail loud first
(`extension_error` surfaced as a failed turn) — plus, because subagents spawn
child processes, the tranche must ensure child cleanup on parent abort (the
example propagates Ctrl+C/abort to kill children — `index.ts` abort handling).

### 9. `supports_image_input` — verdict (i) (architecture §4.11)

**Probe:** sent `prompt` with a base64 PNG in `images[]`, twice
(`transcripts/p6_image.txt` invalid 4×4; `p6b_image_valid.txt` valid 48×48 blue).

Probe-checklist answers:
- **Does pi accept `images[]` and is the image actually seen?** **Yes.** With a
  valid PNG the turn completed `stopReason:"stop"` and the model answered
  **"Blue"** — the image reached and was processed by the model. The image
  block appears in the user message pi builds (`message_start.content` includes
  `{type:"image",data,mimeType}`).
- **Does a non-capable / bad image error or silently drop?** It **errors loud**.
  The malformed 4×4 image produced an API `400 invalid_request_error
  ("Could not process image")` surfaced as assistant `stopReason:"error"` with
  `errorMessage`, then a clean `agent_end` (the standard failed-turn path) — no
  silent drop. This satisfies REQ-CAP-IMAGE-INPUT's no-silent-drop bar.
- **Text-only-model concern:** moot in Sculptor's deployment — all 24 models
  returned by `get_available_models` (Anthropic, the configured provider) are
  `input:["text","image"]`. A hypothetical text-only model would, by the above,
  fail loud rather than drop; the architecture's "runtime error + code comment"
  posture (no per-model wiring this cycle) holds.
- **Size limits over stdin JSONL:** JSONL framing is LF-only with no documented
  payload cap (RPC §3); base64 images ride inline in the `prompt` command.
  Practical limits are the model API's image-size limits, surfaced as the same
  loud error. (Large images: prefer the attachments-by-path route, §10.)

**Mechanism sketch:** Sculptor stops dropping `ChatInputUserMessage` images;
prompt assembly base64-encodes upload-path image files into
`prompt.images[]:[{type:"image",data,mimeType}]`. Entirely Sculptor-side.

### 10. `supports_file_attachments` — verdict (i) (architecture §4.11)

Probe-checklist answers:
- **Do attachments-by-path satisfy "usable that turn"?** Yes. pi's `read` tool
  (`{path}`, §2) reads file contents synchronously within the turn, and
  `supports_file_references` is **already `True`** for pi (it resolves
  @-mentioned paths via its own file-reading loop — `harness.py:69-71`). So
  presenting attachment file paths in the prompt makes their content available
  the same turn, the same way Claude's prompt assembly does.
- **Large files:** the read tool streams via `partialResult` with
  `details.truncation`/`fullOutputPath` for oversized output (§2) — pi handles
  large files through its own tool loop rather than inlining.

**Mechanism sketch:** `ChatInputUserMessage.files` (upload-path file paths)
stops being dropped by pi's prompt assembly; the paths are presented with the
prompt exactly as Claude's assembly presents them. Non-image attachments take
this read-with-tools path; image attachments take the `images[]` path (§9).
Entirely Sculptor-side. Natural bundle with image-input (shared prompt-assembly
plumbing, REQ-PROC-4).

### 11. `supports_background_tasks` — verdict (iv) defer (architecture §4.10)

Probe-checklist answers:
- **Backgroundable tools / async execution in pi-core?** **None.**
  `<pi-pkg>/docs/usage.md:286`: pi "intentionally does not include … background
  bash." The `bash` tool and the out-of-band `bash` RPC command are synchronous;
  there is **no** background-task lifecycle vocabulary anywhere in the event
  union (RPC §5 — no `background_*` events).
- **Any extension-expressible path?** Only a **bespoke simulation**: an
  extension could `spawn` a detached process (as `subagent` spawns children),
  return "started" immediately, and later inject a completion via
  `pi.sendUserMessage(..., {deliverAs:"followUp"})` or `ctx.ui.notify`
  (`<pi-pkg>/docs/extensions.md:1294-1310`). But there is no native
  background-task signal to map, and the Sculptor-side affordance for this flag
  is itself undefined/thin today (architecture §4.10: "no dedicated frontend
  gate exists"; the base tranche only *adds* the gate).
- **Roadmap surface worth noting?** None in the pinned 0.78.0 protocol.

**Verdict rationale:** at the pi-core level the capability is blocked — there is
no background-execution primitive and no lifecycle event to render parity with
Claude's `BackgroundTaskStarted/Notification` contracts. The only path is a
bespoke extension that *imitates* backgrounding with no native signal, against
an undefined Sculptor affordance — not worth a tranche this cycle. **Defer**
(REQ-CAP-ALL-6 satisfied by verdict (iv)). The keep-gate-closed treatment
(fail-closed gate, REQ-CAP-ALL-4) applies; a Proposed FOLLOWUPS entry is in the
MR description. *(Free-form: this is a design exclusion, not a version gap — a
pinned-version bump is **not** expected to unlock it; revisit only if pi-core
adds a background-execution primitive.)*

---

## Cross-cutting findings (exceed the per-flag taxonomy)

These resolve the "pending live probe" unknowns in RPC §10 and inform the base
tranche's typed protocol module (architecture §4.2):

- **No startup banner.** `pi --mode rpc` (even without `--no-session`) emits
  **zero** stdout/stderr before the first command — it starts and waits
  silently (RPC §10 #1 resolved). stderr only carried a benign Bun
  AVX-support warning, never protocol output.
- **`thinking_level_changed` IS emitted.** `set_thinking_level` returns its
  `response` **and** streams `{"type":"thinking_level_changed","level":...}`
  (RPC §10 #2 resolved).
- **`stopReason` on clean completion is `"stop"`** (RPC §10 #3 resolved);
  `"aborted"` on abort (§1), `"error"` on in-turn API failure (§9).
- **Default RPC toolset = `read`, `bash`, `edit`, `write`** only. There is **no**
  native `ask_question`/`question` tool in `--mode rpc` (the
  `--exclude-tools ask_question` example refers to a tool not present in the
  default RPC set); interactive questions require the extension lane (§6).
- **`get_state` fields confirmed live:** `model{…,input:[...],contextWindow}`,
  `thinkingLevel`, `isStreaming`, `isCompacting`, `steeringMode`/`followUpMode`
  (default `one-at-a-time`), `sessionId`, `sessionFile?`, `autoCompactionEnabled`
  (default `true`), `messageCount`, `pendingMessageCount`.
- **All available models multimodal.** With the configured Anthropic key,
  `get_available_models` returned 24 Anthropic models, every one
  `input:["text","image"]` (§9).

These confirm the RPC wire surface is as `pi-0.78.0-rpc.md` characterizes it;
the base tranche can model the documented unions with confidence.

---

## Graduation

*Placeholder — filled at cycle close per REQ-PROC-9.* When every REQ-CAP is
resolved (flag flipped, or deferred with its FOLLOWUPS block) and this document
reflects final reality, the cycle agent asks Danver for the graduation judgment
(daily-usable: yes / not-yet) and records it here.
