# pi-capabilities — Exploration notes (pass 1)

Compact reference distilled from direct codebase reading (2026-06-11),
backing the pass-1 task files. Re-read this instead of re-reading sources.

## Capability model & gating

- `sculptor/sculptor/interfaces/agents/harness.py:51-81` — `HarnessCapabilities`
  (SerializableModel, 12 bool fields, **no defaults** — every constructor
  lists every field). `Harness.capabilities()` base returns all-False
  (`harness.py:107-129`); gated methods `is_ask_user_question_tool` /
  `is_exit_plan_mode_tool` / `is_valid_ask_user_question_input` /
  `get_plan_file_path_from_tool_use` / `extract_recent_plan_file_path`
  default trivially (`harness.py:131-144`).
- Python constructor sites (grep `supports_file_references`):
  `interfaces/agents/harness.py`, `agents/default/claude_code_sdk/harness.py`
  (Claude override, all True), `agents/pi_agent/harness.py:54-72` (pi:
  only `supports_file_references=True`), `agents/default/claude_code_sdk/harness_test.py`,
  `agents/pi_agent/harness_test.py`, `web/derived_task_status_test.py`.
- TS fixture sites: `frontend/src/common/state/atoms/tasks.test.ts:29,130,154,179,211,235`,
  `frontend/src/stories/custom/WorkspacePeekPopover.stories.tsx:74`.
- Flow to frontend: `web/derived.py:378-381` computed field
  `harness_capabilities` → `_resolve_harness()` (`derived.py:469-471`) →
  `harness_registry.get_harness_for_config` (match on config type;
  `agents/harness_registry.py:33-48`). Re-evaluated per task-view build; no caching.
- Twin: generated (`frontend/src/api` is **gitignored**; `just generate-api`);
  type-level tests must import from `~/api`.
- Narrow atoms: `frontend/src/common/state/atoms/tasks.ts:107-137` — 8
  `taskSupports<X>AtomFamily` (pattern at 131-133). Missing: ContextReset
  (new flag), Compaction, BackgroundTasks, SessionResume, ToolUseRendering.
- Hooks: `frontend/src/common/state/hooks/useTaskHelpers.ts:33-62` — 8
  `useTaskSupports<X>` one-liners wrapping the atoms.
- Consumers apply `?? true` (load-race optimism — retained deliberately):
  `ChatInput.tsx:149-156` (`canEnterPlanMode`, `canInterrupt`,
  `canUseFastMode`, `canHarnessAttachFiles`, `canUseImageInput`),
  `ChatInput.tsx:169` (`canAttachFiles = modelCapabilities.supportsFileAttachments && canHarnessAttachFiles` — AND-of-model-and-harness precedent),
  `QueuedMessageBar.tsx:45`, `StatusPill.tsx:103`, `SkillsPanel.tsx:64`,
  `AlphaToolGroup.tsx:69-70`.
- CAPABILITY-GAP markers: `MentionPickerList.tsx:143` (image `+`-menu),
  `TipTapConfig.ts:339,341` (file-refs note; skills picker),
  `Editor.tsx:230` (paste path), `ChatInput.tsx:186` (`/clear` — references
  supportsCompaction, becomes supportsContextReset), `ChatInput.tsx:284`
  (plan mode), `TokenPopoverContent.tsx:30` + `StatusPill.tsx:34`
  (compaction chrome), `agents/pi_agent/agent_wrapper.py:154-158` (drops),
  `agent_wrapper.py:352` (tool events), `agent_wrapper_test.py:500`.

## pi agent backend

- `agents/pi_agent/agent_wrapper.py` — `PiAgent(DefaultAgentWrapper)`;
  launch argv `[binary, --mode rpc, --no-session, --append-system-prompt, <prompt>]`
  (line 140); `_push_message` (150-161) queues ChatInput, returns False for
  Interrupt/Resume/Clear/Answer (silent drop today — dead-letter site);
  `_process_message_queue` (247-256) wraps each turn in
  `self._handle_user_message(message)`; `_consume_until_turn_end` (258-302)
  three-lane dispatch; `_handle_session_event` (324-363) per-type dict
  dispatch; `_handle_message_update/_end`, `_handle_agent_end` (383-498)
  text accumulator → `PartialResponseBlockAgentMessage` /
  `ResponseBlockAgentMessage` with stable
  `assistant_message_id`/`first_message_id` from `_TurnState` (85-103);
  `FILE_CHANGE_TOOL_NAMES = {edit,write,bash}` (74) → `on_diff_needed`
  (365-381); `wait()` sends `{"type":"abort"}` + closes stdin (176-194);
  `_send_rpc` (237-245).
- `agents/pi_agent/output_processor.py` — pydantic models already exist for
  the consumed subset: `RpcResponse`, `ExtensionUiRequest` (type+id+method
  only), `ParsedTextDelta`, `ParsedAssistantMessageError`, `ParsedAgentStart/End`,
  `ParsedMessageUpdate/End`, `ParsedAutoRetryEnd`, `ParsedExtensionError`,
  `AgentMessage` (content: raw dicts) + `extract_assistant_text`. The typed
  protocol task EXTENDS this module to the full documented union.
- Base class `agents/default/agent_wrapper.py` — `DefaultAgentWrapper`:
  `push_message` (93-117) calls `_push_message` then generic handling
  (RemoveQueuedMessage, StopAgentUserMessage→terminate);
  `_handle_user_message` ctx-mgr (137-196) emits `RequestStartedAgentMessage`
  → on success `RequestSuccessAgentMessage(interrupted=self._was_interrupted.is_set())`;
  **`_was_interrupted: threading.Event` already exists on the base (line 62)** —
  the pi interruption tranche sets it.
- Errors: `PiCrashError`, `PiBinaryNotFoundError`, `PiVersionMismatchError`
  in `interfaces/agents/errors.py`; version pin `PI_VERSION_RANGE`
  (0.78.0 single-point) in `services/dependency_management_service.py:64-68`.
- Protocol ground truth: `agent_docs/pi-basic/pi-0.78.0-rpc.md` —
  commands incl. `prompt{message, images?, streamingBehavior?}`, `abort`,
  `new_session`, `compact`, `set_auto_compaction`, session cmds
  (`switch_session`, `fork`, `--session-dir`), `get_state` (sessionFile/
  sessionId/isCompacting...), `get_commands`; events incl. `turn_start/end`,
  `tool_execution_start/update/end`, `compaction_start/end{reason}`,
  `queue_update`, `auto_retry_*`, `extension_error`, `extension_ui_request`
  (dialog select/confirm/input/editor + fire-and-forget) ⇄
  `extension_ui_response`; turn boundary = `agent_end`; preflight failure =
  `response success:false` with NO session events; responses correlate by
  `id` not order; `--help` flags incl. `--no-skills`, `--no-extensions`.

## Endpoints (web/app.py)

- Send: `send_workspace_agent_messages` (~2050-2112) — plan-mode guard at
  ~2078: 400 if `enter_plan_mode and not capabilities().supports_interactive_backchannel`;
  builds `ChatInputUserMessage(text, files=message_request.files, enter/exit_plan_mode, fast_mode, effort)`.
- AUQ answer: `answer_workspace_agent_question` (~2114-2141) — persists
  `UserQuestionAnswerMessage`; **no capability guard**.
- Clear: `clear_workspace_agent_context` (~2145-2168) — persists
  `ClearContextUserMessage` under `await_message_response(message_id, ...)`
  (waiter resolves on the request's terminal Request* message); **no guard**
  — context-reset tranche adds one mirroring the 2078 pattern.
- Interrupt endpoint follows (~2170+). Upload: `POST /api/v1/upload-file`
  (~3639-3657) stores under `settings.upload_path` with uuid names; frontend
  sends fileIds via `SendMessageRequest.files`.
- Skills list: `GET /api/v1/skills` (~1489-1554) → `web/skills.py:153-201`
  `discover_skills(repo_path, plugin_dirs)` scanning plugin skills →
  `<repo>/.claude/skills` → `<repo>/.claude/commands` → `~/.claude/skills`
  → `~/.claude/commands` (first-name-wins).
- Pseudo-skills (`/clear`, `/copy`, `/btw`) parse frontend-side:
  `frontend/src/common/pseudoSkills.ts:47-100`; `/clear` executes in
  `ChatInput.executePseudoSkill` (`ChatInput.tsx:186-200`) calling
  `clearWorkspaceAgentContext` (generated client).

## Frontend patterns for the base tranche

- Tooltip: Radix `Tooltip` from `@radix-ui/themes` (`AgentStatusDot.tsx:42`);
  `TooltipIconButton` wrapper used in `BottomBar.tsx:64,86`, `ChatInput.tsx:581`.
  CLAUDE.md note: IconButtons in `Flex` need `gap="2"`.
- ElementIDs: `sculptor/sculptor/constants.py:11` `class ElementIDs(StrEnum)`,
  SCREAMING_SNAKE values; regenerate with `just generate-api`; frontend
  `page.get_by_test_id(ElementIDs.X)` in tests.
- Model-capability precedent: `getModelCapabilities(localModel)`
  (`ChatInput.tsx:166`, `modelCapabilities.ts`) — image-input's future
  hoist target; this cycle: runtime error + comment.

## Testing infrastructure

- fake_pi: `sculptor/sculptor/testing/fake_pi.py` — directive grammar
  `fake_pi:<name> \`<json>\`` (registry at 213-218: emit_text, stream_text,
  sleep, wait_for_file; `error` handled via `_find_error_directive`);
  emits response→agent_start→user-echo message_end→message_update(s)→
  message_end→agent_end (`_run_turn` 239-270); **abort handler acks then
  EXITS (287-289) — real pi stays alive; interruption tranche must fix**;
  `install_fake_pi_binary(fake_bin_dir)` (322-334) pins absolute path.
  Default pi stub auto-installed in integration tests;
  `disable_default_pi_stub_for_session()` (`testing/dependency_stubs.py:61-70`)
  is the real_pi escape hatch.
- Gate tests: `tests/integration/frontend/test_pi_capability_gating.py` —
  parametrized `harness` fixture ("claude"/"pi", indirect;
  `HarnessTestConfig` from `tests/integration/frontend/conftest.py`),
  `_create_workspace_for_harness` helper (installs fake_pi, model_name=None
  for pi vs FAKE_CLAUDE_MODEL_NAME), 5 existing tests assert pi-side
  `to_have_count(0)` — **assertions change to disabled+tooltip when the
  base tranche migrates surfaces**. Siblings: `test_pi_basic.py`,
  `test_minimum_interface_conformance.py`, `test_workspace_harness_picker.py`,
  `test_pi_managed_install.py`.
- real_pi: `tests/integration/real_pi/` — conftest swaps real keys +
  `disable_default_pi_stub_for_session`; `helpers.create_pi_workspace_and_send`
  uses `start_task_and_wait_for_ready(harness=HarnessName.PI, model_name=None)`
  + `prefixed()` test-prefix; 2 tests (basic flow, file edit). Run:
  `just test-real-pi` (justfile:1414; serial, excluded from CI). real_claude
  sibling: 17 files (interrupts, tool_calls, clear_context,
  ask_user_question, plan_mode, background_tasks, streaming, ...).
- `@user_story(...)` decorator used on integration tests.

## Process anchors

- This docs branch (`danver/pi-capabilities`) merges to main FIRST; every
  phase = own workspace on `danver/pi-capabilities-<topic>`, MR → main
  (REQ-PROC-2); base merges before capability phases (REQ-PROC-1 /
  REQ-BASE-1); task 0 ∥ base allowed (REQ-INV-5).
- Pass 2: after task 0 + base merge, a second planning session authors
  phase 02-11 task files from feasibility.md + architecture §4.
- Evidence bundles: base = full (gates output, full real_pi, real-claude
  rerun, checklist) + zero-Claude-change assertion; task 0 = deterministic
  gates + probe evidence embedded in feasibility.md (docs-only MR).
