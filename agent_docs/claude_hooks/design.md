# Reliable busy/idle status for the Claude CLI terminal agent — design

> **Status: proposed.** Makes the registered Claude Code terminal agent report
> busy/waiting/idle reliably across the turn lifecycle. All decision logic
> lives **inside the Claude registration**; Sculptor and the `sculpt` CLI stay
> generic and extension-agnostic.
>
> **Scope split (important):** the net hook change is small — `SessionStart`
> stops idling on a mid-turn `compact` (the **auto-compaction** fix), and an
> `idle_prompt`→idle **backstop** is added. The third gap, the background-work
> "flicker," is **reclassified as correct behavior** (a finished turn is idle
> even with work pending — §5), so `Stop` is left unconditional. The fourth, the
> **Esc interrupt** (original SCU-1600), has **no reliable fix today** without
> coupling Sculptor to Claude's internals (see §7) and is deferred to an
> upstream Claude cancel signal. SCU-1600 is re-scoped to "ship the
> compaction fix + backstop; interrupt blocked on upstream."

## 1. Problem

The registered Claude Code terminal agent reports its status to Sculptor via
Claude Code **hooks** that shell out to `sculpt signal <state>`. The current
wiring is a coarse two-event model — *busy on `UserPromptSubmit`, idle on
`Stop`* — and it is wrong in three observed situations, plus a fourth that
hooks cannot see at all:

1. **Esc interrupt → stuck busy.** Pressing Esc to interrupt a turn fires
   **no hook**, so the last `busy` never clears and the tab spins forever.
   (This is SCU-1600 — **deferred**, see §7: no reliable fix exists today.)
2. **Auto-compaction → stuck idle.** When the context auto-compacts mid-turn,
   the agent keeps working but the tab goes idle and stays there.
3. **Completes-with-background-work → idle/busy "flicker".** A turn that leaves
   a background task (or scheduled wake-up) running reports idle, then flips
   back to busy when the background op wakes the agent, then idle again.
   (Investigated and **reclassified as correct** — §5: a finished turn *is*
   idle; the re-wake to busy is accurate, and idle is what produces the tab's
   completion/unread signal. No change here; `Stop` stays unconditional.)
4. **(Goal)** Across all of the above: always reliably indicate whether the
   agent is *actively working* or *truly idle/waiting*.

## 2. Evidence — verified Claude Code hook lifecycle

Everything below was measured against the **real Claude CLI 2.1.190** by
driving the TUI over a PTY with a settings file that logs every hook event's
full payload. The probe harness is kept at the Sculptor **workspace root**
(`run_hook_probe.py`, one level above this repo checkout) as a dev reference —
it is intentionally *not* committed (it spawns a real Claude and burns tokens);
the raw timelines below are reproduced here because the design rests on them.

### 2.1 Observed sequences

```
A. Trivial turn ("PONG")
   UserPromptSubmit → Stop(bg=0) → [+~3s] SubagentStop → [+60s] Notification idle_prompt

B. Tool turn
   UserPromptSubmit → PreToolUse(Bash) → PostToolUse(Bash) → Stop(bg=0)

C. Background task (sleep 30 in background, reply STARTED)
   UserPromptSubmit → PreToolUse → PostToolUse → Stop(bg=1) → SubagentStop(bg=1)
   …[~30s later, the task completes and RE-WAKES the agent]…
   UserPromptSubmit(re-wake) → Stop(bg=0)

D. Esc interrupt mid-tool (a ~30s CPU command running)
   UserPromptSubmit → PreToolUse(Bash) → [ESC] → **NOTHING**
   (no Stop, no Notification, no idle_prompt within 90s)

E. Compaction (/compact, same hooks as auto-compaction)
   PreCompact → SubagentStop → SessionStart(source=compact) → PostCompact
```

### 2.2 Load-bearing facts

- **`Stop` is not "done".** It fires at the end of *every* response, even
  when background work is still running. Its payload (2.1.190) carries
  `stop_hook_active`, `last_assistant_message`, and crucially
  **`background_tasks`** and **`session_crons`** arrays. In scenario C, `Stop`
  fired with `background_tasks=[{…,status:"running",command:"sleep 30"}]`.
- **A finishing background task re-wakes the agent as a fresh
  `UserPromptSubmit`** (scenario C, the second `UserPromptSubmit` that we
  never typed). That is the source of the flicker.
- **Auto-compaction re-fires `SessionStart` with `source:"compact"`**
  (sources are `startup | resume | clear | compact`), plus `PreCompact` and
  `PostCompact`. The turn then *continues* with no new `UserPromptSubmit`.
- **Esc fires zero hooks.** Confirmed: no `Stop`, no `Notification`. And the
  `idle_prompt` notification does **not** fire after an interrupt within 90s —
  it is armed by a normal turn end, of which there was none. So hooks cannot
  detect an interrupt at all.
- **`Notification:idle_prompt` is a fixed ~60s-after-turn-end reminder**
  (measured 60.1s in A), not an immediate idle signal — usable only as a slow
  corroborating backstop, never as the primary idle signal, and useless for
  the interrupt case.
- **`SubagentStop` fires ~3s after almost every `Stop`** even with no
  subagent involved — it is noise for status purposes; do not use it.
- Sandbox note for tests: the foreground `sleep` command is blocked by the
  harness; background `sleep` works. Use a CPU one-liner
  (`python3 -c "print(sum(range(900000000)))"`) to force a long foreground
  tool call.

## 3. Current architecture (what we are changing)

- **Hooks → CLI:** `samples/terminal_agents/claude-code/claude-code-hooks.json`
  maps hook events to `sculpt signal <state>` commands. `sculpt signal`
  (`tools/sculpt/sculpt/commands/signal.py`) POSTs to
  `/api/v1/agents/{agent_id}/signal` with `event ∈ {busy, idle,
  waiting-on-input, files-changed, session-id}`.
- **Endpoint → message:** `post_agent_signal` in `sculptor/sculptor/web/app.py`
  (~L3504–3566) maps the event to `TerminalStatusSignal` and creates an
  ephemeral `TerminalAgentSignalRunnerMessage`
  (`sculptor/sculptor/interfaces/agents/agent.py`). `TerminalStatusSignal`
  is `{BUSY, IDLE, WAITING}`.
- **Message → status:** `scan_terminal_signal_state`
  (`sculptor/sculptor/web/derived.py` L99–122) reverse-scans the live
  messages for the latest signal since the run-start anchor
  (`EnvironmentAcquiredRunnerMessage`). `CodingAgentTaskView.status`
  (L490–503) maps `BUSY→RUNNING`, `WAITING→WAITING`, else `READY`; no run
  yet → `BUILDING`.
- **PTY I/O:** the terminal WebSocket relay (`_connect_terminal_websocket`
  in `app.py`, ~L3669–3763) writes raw frontend bytes into the PTY via
  `LocalTerminalManager.write()`
  (`…/environment_manager/environments/local_terminal_manager.py`). **Sculptor
  sees every byte the user types**, including ESC (`0x1b`) and Ctrl-C
  (`0x03`) — this is what makes the interrupt fix possible.
- The task handler (`run_terminal_agent/v1.py`) runs a 1s idle poll loop with
  no per-turn request/response cycle, and injects `SCULPT_*` env (incl.
  `SCULPT_AGENT_ID`). The agent's Claude transcript path is **not** known to
  Sculptor (session-id is only used to `--resume`), so transcript
  introspection is not an available idle source.

## 4. Design principles

1. **`busy` must be cheaply re-assertable.** Any agent activity should be able
   to flip the tab back to busy, so a premature/incorrect idle self-corrects
   on the very next action.
2. **`idle` must be earned, not assumed.** We only go idle when the agent is
   genuinely waiting — i.e. a turn ended *and* no background work is pending.
3. **All decision logic lives in the extension — never in Sculptor or
   `sculpt`.** The backend and the `sculpt` CLI are a generic,
   extension-agnostic transport: a fixed signal vocabulary (`busy`, `idle`,
   `waiting`, `files-changed`, `session-id`), the POST endpoint, and the PTY
   proxy. They know nothing about Claude's hook events or payload schema. The
   Claude registration decides *when* to emit each signal entirely within its
   own files — the hooks JSON does any payload inspection in self-contained
   POSIX shell (the same dependency-free way it already extracts `session_id`
   with `sed`), and emits only the generic verbs. A second registration could
   implement completely different logic with zero changes to Sculptor.
4. **The interrupt has no reliable, principled fix today** — see §7. It is
   deferred to an upstream Claude cancel signal rather than fixed with a
   Sculptor-side heuristic that would couple to Claude and still be wrong.

## 5. The hook state machine (target)

Canonical event → signal mapping after this change:

| Source | Condition | Signal |
|---|---|---|
| `UserPromptSubmit` | always (incl. background-task re-wake) | **BUSY** |
| `PreToolUse` | tool ∈ AskUserQuestion, ExitPlanMode | **WAITING** |
| `Notification` | type = `permission_prompt` / `worker_permission_prompt` | **WAITING** |
| `PostToolUse` | tool ∈ AskUserQuestion, ExitPlanMode (answered) | **BUSY** |
| `PostToolUse` | tool ∈ Edit/Write/MultiEdit/NotebookEdit/Bash | `files-changed` (unchanged; not a status) |
| `Stop` | always (a finished turn is idle, regardless of pending background/scheduled work) | **IDLE** |
| `SessionStart` | `source ∈ {startup, resume, clear}` | **IDLE** |
| `SessionStart` | `source = compact` | *no-op* (preserve prior state) |
| `Notification` | type = `idle_prompt` | **IDLE** (slow corroborating backstop) |
| Esc / interrupt | — | **deferred** — no reliable signal exists today (see §7) |

New vs. today: `PreToolUse(any)→BUSY` (re-assert), `Stop` becomes
conditional, `SessionStart` becomes source-gated, `idle_prompt→IDLE` added as
a backstop, and the Esc handler is new.

### Why this fixes each gap

- **Gap 2 (compact):** the `SessionStart` hook is scoped (by matcher) to
  `startup|resume|clear`, so a mid-turn `source=compact` start fires nothing
  and the prior BUSY state simply persists — nothing signals idle until the
  turn's eventual real `Stop`. The agent stays busy through compaction.
- **Gap 3 (background "flicker") — reclassified as correct behavior.** `Stop`
  always signals idle. The status answers "is Claude *actively generating* right
  now?", so a finished turn is idle even if a background task or a scheduled
  wake-up is still pending — the agent is genuinely idle at its prompt. The
  perceived flicker (idle → busy → idle when a background op or timer re-wakes
  the agent) is accurate: each state reflects what Claude is really doing, and
  going idle is what produces the tab's completion signal (e.g. the unread/green
  dot when the tab isn't focused). We therefore do **not** suppress idle for
  pending work — `Stop` is left unconditional (identical to the prior shipped
  hooks). A long-lived background process (a `dev` server) correctly reads as
  idle; a transient one re-wakes to busy and settles back to idle.
- **Gap 1 (Esc):** deferred — §7 shows no reliable signal exists today.
- **Backstop:** if a `Stop` is somehow missed, `idle_prompt` corrects the tab to
  idle within ~60s of a genuine idle (it will not falsely fire during work, and
  — verified — it does not fire after an interrupt).

> **Product decision (background/scheduled-work status).** A finished turn is
> IDLE regardless of pending `background_tasks` or `session_crons`. We
> considered holding the tab BUSY while a scheduled wake-up (cron) is pending,
> but rejected it: "busy" should mean *actively generating*, and holding blue
> while merely waiting on a timer both misrepresents the state and swallows the
> completion (unread/green) signal an unfocused tab should show. So `Stop`
> stays unconditional `sculpt signal idle`; the agent re-wakes to BUSY on its
> own (a fresh `UserPromptSubmit`) when the timer/background op actually fires.
> (This diverges from Claude's own `idle_prompt` suppression during background
> tasks, which is a notification nicety, not a status contract.)

## 6. Hook-side changes — entirely within the Claude registration

**No change to the `sculpt` CLI or the backend signal endpoint.** They keep
the generic vocabulary. The decisions are made inside
`samples/terminal_agents/claude-code/claude-code-hooks.json` and call only the
generic `sculpt signal` verbs. There is no payload-inspecting shell at all:
filtering is done by Claude's matchers (`SessionStart` source, `Notification`
type, tool name), and `Stop` is unconditional.

**Stop** — a finished turn is always idle (see §5):

```jsonc
"Stop": [{ "hooks": [{ "type": "command", "command": "sculpt signal idle || true" }] }]
```

**SessionStart** — go idle on a real (re)start, but not on a mid-turn
compaction. Unlike `Stop`, `SessionStart` supports a `source` matcher, so the
filtering is done declaratively by Claude (no shell needed): the hook is scoped
to `startup|resume|clear`, so a `source=compact` start matches no group and
fires nothing, leaving the prior BUSY state intact.

```jsonc
"SessionStart": [
  { "matcher": "startup|resume|clear",
    "hooks": [{ "type": "command", "command": "sculpt signal idle || true" }] }
]
```

The full `claude-code-hooks.json` (the one conditional — `Stop` — inlined as a
one-liner, since `Stop` has no matcher and must read its payload):

```jsonc
{
  "skipDangerousModePermissionPrompt": true,
  "hooks": {
    "SessionStart": [{ "matcher": "startup|resume|clear",
      "hooks": [{ "type": "command", "command": "sculpt signal idle || true" }] }],
    "UserPromptSubmit": [{ "hooks": [
      { "type": "command", "command": "sculpt signal busy || true" },
      { "type": "command", "command": "sid=$(sed -n 's/.*\"session_id\"[[:space:]]*:[[:space:]]*\"\\([^\"]*\\)\".*/\\1/p' | head -n1); [ -n \"$sid\" ] && sculpt signal session-id \"$sid\" || true" }
    ] }],
    "Stop": [{ "hooks": [{ "type": "command", "command": "sculpt signal idle || true" }] }],
    "Notification": [
      { "matcher": "permission_prompt|worker_permission_prompt", "hooks": [{ "type": "command", "command": "sculpt signal waiting || true" }] },
      { "matcher": "idle_prompt", "hooks": [{ "type": "command", "command": "sculpt signal idle || true" }] }
    ],
    "PreToolUse": [
      { "matcher": "AskUserQuestion|ExitPlanMode", "hooks": [{ "type": "command", "command": "sculpt signal waiting || true" }] }
    ],
    "PostToolUse": [
      { "matcher": "Edit|Write|MultiEdit|NotebookEdit|Bash", "hooks": [{ "type": "command", "command": "sculpt signal files-changed || true" }] },
      { "matcher": "AskUserQuestion|ExitPlanMode", "hooks": [{ "type": "command", "command": "sculpt signal busy || true" }] }
    ]
  }
}
```

Notes:
- The `UserPromptSubmit` busy hook also catches the **background-task re-wake**
  (whose prompt is a `<task-notification>` injected by Claude) → busy, which is
  correct.
- `PreToolUse` only carries the question/plan→WAITING matcher. We deliberately
  do **not** add a generic `PreToolUse(any tool)→busy` re-assert: with the
  interrupt deferred there is no spurious mid-turn idle for it to correct, and
  it would need a stale-prone tool list plus extra signal volume. BUSY is
  asserted by `UserPromptSubmit` (incl. the re-wake) and by the answered-question
  `PostToolUse`.
- The `idle_prompt` matcher is **added** to `Notification`. The earlier
  deliberate omission (so the 60s reminder couldn't fake the dot) is now safe
  because `idle_prompt` only ever drives the tab *to idle* and agrees with the
  real idle we derive.
- All filtering is done by Claude's matchers (`SessionStart` source,
  `Notification` type, tool name); no hook inspects the payload in shell, so
  there is no `jq`/`python` dependency and nothing to break across Claude
  versions. The only remaining shell is the `UserPromptSubmit` `sed` that
  extracts the session id (unchanged from the prior shipped hooks).

## 7. Interrupt handling (SCU-1600) — no reliable fix today; defer upstream

The interrupt cannot be fixed both *reliably* and *without coupling Sculptor to
Claude's behavior* with the mechanisms Claude exposes today. This is the result
of exhaustive probing (CLI 2.1.190), not an assumption:

| Candidate signal | Verdict |
|---|---|
| **Any hook** (full documented set enabled) | A real cancel fires **nothing** — verified for both a running-tool interrupt and a text-generation interrupt (0 events in 30s). |
| **A dedicated cancel/interrupt hook** | Does not exist; `Stop` doesn't fire on interrupt; `SessionEnd` reasons don't include it. |
| **`idle_prompt` Notification** | Does **not** fire after an interrupt (it's armed by a normal turn end) — so even the Section 5 backstop can't catch this. |
| **Statusline command** | No turn-state/"is-working" field, and it doesn't run on interrupt (only after a new assistant message, `/compact`, permission-mode/vim change, or `refreshInterval`). |
| **Keystroke heuristic (ESC/Ctrl-C in the PTY)** | Unreliable *and* coupling: ESC is overloaded **inside Claude** (it also dismisses TUI menus, leaving the turn running), and "which key cancels" is itself Claude-specific. Sculptor can't tell a cancel from a menu-dismiss from the byte alone. |
| **Watch the Claude transcript** | The only internal record, and it *could* live in an extension-owned watcher (keeping Sculptor generic) — but it couples to Claude's **undocumented** transcript format, the interrupt-marker shape is unverified, and in our sandbox transcripts were not even persisted. Fragile; not recommended. |

**Why a keystroke fix is wrong (the decisive point).** The same ESC byte means
"cancel the turn" or "close a menu" depending on Claude's internal UI state,
which only Claude knows. No declaration (an `interrupt_bytes` field) or
Sculptor-side rule can disambiguate it, so any such fix would sometimes mark a
working agent idle. The earlier "self-corrects on the next PreToolUse"
mitigation does not hold: during a long model-generation or a quiet
long-running tool there may be no hook for many seconds, so the tab would show
a wrong idle for that whole window.

**Decision: defer the interrupt to upstream and scope it out of this change.**

1. **File a Claude Code feature request** for a turn-cancel signal — ideally a
   hook that fires on interrupt, or a turn-state field on the statusline input,
   or a `Stop` that fires (with a reason) on interrupt. Once any of these
   exists, the fix is **pure-extension, zero Sculptor change**: the hooks JSON
   maps it to `sculpt signal idle`.
2. **Until then, accept the residual.** After an Esc-cancel the tab stays on
   the spinner, but it **self-heals on the user's next interaction**: their
   next prompt fires UserPromptSubmit -> busy and ends at a real Stop -> idle.
   The bad window is "interrupted, then left untouched."
3. **No interrupt test is carried.** We don't commit a permanently-skipped
   Playwright test for behavior we can't implement; the desired behavior and
   its upstream block are documented here and on SCU-1600. Add the test when an
   upstream cancel signal exists.

If product decides the stuck-spinner-until-next-prompt residual is
unacceptable before upstream lands, the only option that keeps Sculptor generic
is the **extension-owned transcript watcher** (a helper the Claude registration
launches, that tails Claude's transcript and calls generic `sculpt signal`);
it must first be validated that interrupts are recorded distinguishably and
stably across versions. Flagged, not recommended.

## 8. Rollout / migration

The registration files are **installed once and then user-owned** —
edits/deletes stick and staleness is accepted (see
`agent_docs/terminal-agents/builtin-claude-code-design.md`). So shipping a new
`claude-code-hooks.json` in `samples/` does **not** update existing installs,
and the §5/§6 behavior depends on the new wiring. Required:

- **Hash-stamp refresh of the managed files.** The installer
  (`services/terminal_agent_registry/bundled.py`) keeps, per file, the sha256 of
  every version Sculptor has shipped (`_KNOWN_MANAGED_FILE_SHA256`). On every
  start, for each managed file (the TOML *and* the hooks JSON), if the installed
  copy's hash is in that file's set (i.e. it is an unmodified Sculptor copy) and
  differs from the bundle, it is overwritten with the bundle. A user-edited file
  (unknown hash) or a deleted file (absent) is left alone. The two files refresh
  **independently**, so editing one (e.g. customizing the TOML's launch command)
  never blocks upgrading the other (e.g. a hooks fix). When a bundled file
  changes, its new hash is appended to its set.
- **No `sculpt` CLI / endpoint / client changes**, so no
  `just generate-sculpt-client` and no version floor on `sculpt`. The new
  behavior is entirely in the registration's hooks JSON, and (since no hook
  inspects the payload) it is insensitive to Claude payload changes.
- **Interrupt migration** depends on the §7 decision: a backend-only generic
  rule needs no migration; a registration-schema field needs the same
  installer refresh as the hooks JSON (and a `RegisteredTerminalAgentConfig`
  field, regenerated types).

## 9. Test plan

1. **Real-Claude regression (`@real_claude`).** Adapt the workspace-root probe
   (`run_hook_probe.py`) into a permanent test
   under `sculptor/tests/integration/real_claude/` that asserts the verified
   sequences in §2.1: compact→`SessionStart(source=compact)`, background
   task→`Stop(bg≥1)` then re-wake, and (already covered)
   busy/idle/waiting. Burns tokens; keep it minimal and skippable like the
   existing `test_claude_code_terminal_agent`.
2. **Bundled-hooks structure tests** (`registry_test.py`, no tokens) — assert
   the shipped JSON's matcher semantics directly: `SessionStart` idles on
   `startup|resume|clear` but not `compact`; `Notification` signals `waiting`
   for permission prompts but never for `idle_prompt` (which signals idle);
   questions drive `waiting`→`busy` via PreToolUse/PostToolUse; the session id
   is reported from `UserPromptSubmit`, not `SessionStart`.
3. **Installer refresh tests** (`bundled_test.py`) — for each managed file
   (TOML and hooks JSON): an unmodified copy is refreshed to the bundle on
   upgrade; a user-edited or deleted file is left untouched; and editing one
   file does not block refreshing the other.
4. **No interrupt test** is committed — the behavior is blocked upstream (§7),
   and a permanently-skipped Playwright test earns nothing. Add it when an
   upstream cancel signal lands.
5. **Existing tests** must stay green:
   `test_claude_code_terminal_agent`, the terminal-input guard tests, and the
   CI-babysitter readiness gate (which reads `scan_terminal_signal_state`).

## 10. Out of scope / explicitly not doing

- Using `SubagentStop` for status (noise).
- Making `idle_prompt` the primary idle signal (60s-lagging; absent after
  interrupts).
- Reading the Claude transcript to infer idle (Sculptor doesn't have the
  path, and it's program-internal).
- Any change to how chat (SDK) agents report status — this is terminal-agent
  only.

## 11. File-touch summary

| Area | File | Change |
|---|---|---|
| **Extension only** | `samples/terminal_agents/claude-code/claude-code-hooks.json` | `SessionStart` source matcher + `idle_prompt`→idle (§6); `Stop` unchanged |
| Installer | `services/terminal_agent_registry/bundled.py` | per-file hash-stamp + independent refresh of the managed TOML and hooks JSON (user-owned copies) |
| Interrupt | **deferred (blocked upstream, §7)** | no code, no test; file the Claude FR |
| Tests | `services/terminal_agent_registry/{registry,bundled}_test.py`, `tests/integration/frontend/test_registered_terminal_agent.py` | §9 |
| Probe | `run_hook_probe.py` (workspace root, **not** committed) | dev reference harness |

Note: `sculpt` CLI, the signal endpoint, and `derived.py` are **unchanged** —
they stay generic.
