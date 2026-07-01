# pi Provider Authentication & Authenticated-Only Model Picker — Review

## Summary

- The implementation **meets the spec**: every `REQ-*` is covered with code and
  tests, the architecture's chosen designs (1b ephemeral login PTY, broadcast
  refresh, `sources_backend_models` signal, wrapper-chokepoint filter) are all
  realized, and the diff stays within `pi-core is immutable` (no pi-core changes).
- **Verification is green**: `just check` (ratchets, lint, typecheck, file-hygiene),
  `just test-unit` (backend, frontend, foundation, sculpt), and the 7 new pi
  integration files (**8 passed in 38.76s**) all pass — re-run during this review.
- **Nothing blocks merge.** One MEDIUM judgement call remains open as an acceptance
  decision: the headline interactive `/login` keystroke round-trip has no automated
  real-binary coverage (documented, verified by hand). The empty-state loading flash
  was confirmed real but brief and accepted, with a follow-up filed (SCU-1583).
- **Fixes landed during the review (Address-in-tab loop):** removed the dead
  `iter_single_key_env_var_names` helper (`f0bd95e`), dropped the unused
  `is_subscription` full-stack plumbing (`b803f28`), reworded plan-phase/REQ
  references out of comments (`771444b`), routed the picker/error test-ids through
  the chat-panel POM (`5310f1d`), converted the providers read from a loadable atom
  to a TanStack hook (`1391558`), and deduped the login-teardown model-refresh
  broadcast (`c34425a`). `just check` + `just test-unit` + the affected integration
  tests are green after each.

## Requirements Coverage

| Requirement | Status | Evidence |
|-------------|--------|----------|
| REQ-AUTH-1 (interactive `/login` from Settings) | Covered | `services/pi_login_service.py:88-126` (spawn), `web/app.py` `start_pi_login`, `PiProvidersArea.tsx:173-179` |
| REQ-AUTH-2 (global config dir, no `PI_CODING_AGENT_DIR`) | Covered | `pi_login_service.py:107-118` — `extra_env={}`, `$HOME` cwd, no `PI_CODING_AGENT_DIR`, no api-key secrets |
| REQ-AUTH-3 (disconnect via `/logout` as-is) | Covered | `PiLoginMode.LOGOUT`; Disconnect gated on `inAuthJson` (`PiProvidersArea.tsx:180-189`); `/logout` typed into PTY |
| REQ-AUTH-4 (merge-safe paste-key) | Covered | `authenticated_providers.py:74-101` (`write_auth_json_entry`), `web/app.py` paste-key endpoint, `PiPasteKeyForm.tsx` |
| REQ-UI-1 (master/detail Providers area) | Covered | `PiProvidersArea.tsx` (rail + detail) |
| REQ-UI-2 (Connected from `auth.json`, no re-entry) | Covered | `piProvidersGrouping.ts`, `ConnectedSource` "Imported from ~/.pi/agent/auth.json" |
| REQ-UI-3 (inline `/login` terminal, not a modal) | Covered | `PiLoginTerminal.tsx` via `useTerminal`, WS route `GET /api/v1/pi/login/{id}/ws` |
| REQ-UI-4 (collapsible paste-key) | Covered | `PiPasteKeyForm.tsx` (`isOpen` toggle) |
| REQ-UI-5 (verbatim empty copy + CTA) | Covered | `ModelSelector.tsx:84-98` (`PI_NO_MODELS_COPY` + "Open pi login") |
| REQ-FILTER-1 (authenticated-only picker) | Covered | `agent_wrapper.py` `_curate_models(... authenticated_providers)` + `compute_authenticated_provider_ids` |
| REQ-FILTER-2 (Sculptor-side, wrapper chokepoint) | Covered | filter applied at both `_fetch_models_into_state:1115` and `fetch_available_models_probe:1217` |
| REQ-FILTER-3 (live refresh, no restart) | Covered | `RefreshModelsUserMessage`, `broadcast_pi_models_refresh`, `_handle_refresh_models`; e2e `test_pi_picker_live_refresh.py` |
| REQ-PERSIST-1 (persist in pi's `auth.json`) | Covered | interactive `/login` (pi writes) + `write_auth_json_entry` |
| REQ-PERSIST-2 (single-key providers v1) | Covered | `provider_catalog.py` SINGLE_KEY entries |
| REQ-PERSIST-3 (session-only multi-value, deferred) | Covered | SESSION_ONLY group + explainer; no paste form offered |
| REQ-ERR-1 (actionable empty message + route) | Covered | picker empty state + `AlphaErrorBlock.tsx:115-127` failed-turn CTA |
| REQ-COMPAT-1 (Claude unchanged) | Covered | `sources_backend_models()` False for Claude; `PRODUCTION_MODELS` fallback retained |
| REQ-COMPAT-2 (#53 seam keeps working) | Covered | filter layered on `_curate_models`; current model always retained |
| REQ-COMPAT-3 (no pi-core changes) | Covered | only existing RPCs + `auth.json` read/write + driving pi's own `/login` |

## User Scenarios

- **US-1 (existing pi user, zero re-auth):** Delivered. `compute_authenticated_provider_ids`
  unions `keys(auth.json)` with env-detected providers, so an existing user's
  Anthropic/OpenAI show as Connected and the picker lists only their models.
  Covered by `test_pi_providers_settings.py` (Connected grouping + import
  annotation) and `test_pi_model_picker_filter.py`.
- **US-2 (new user authenticates once, persists for standalone pi):** Delivered.
  Authenticate opens the inline PTY against the user's real `~/.pi/agent`
  (no `PI_CODING_AGENT_DIR`), so pi writes the shared file. Inline-terminal wiring
  covered by `test_pi_login_terminal.py`; the real pi honoring a Sculptor-written
  file covered by `real_pi/test_provider_auth.py::test_real_pi_honors_written_auth_json`.
- **US-3 (interactive login is the primary path):** Delivered. Both Authenticate and
  Disconnect route through one `PiLoginService` PTY (mode flag). See coverage gap
  note in Test Coverage — the interactive keystroke flow itself is verified by hand,
  not automated.
- **Power-user paste / Disconnect / Session-only / Empty state:** all delivered and
  covered by `test_pi_paste_key.py`, `test_pi_picker_empty_state` and
  `test_pi_turn_error.py`.

## Test Coverage

- **Tests added:** backend unit — `provider_catalog_test.py`,
  `authenticated_providers_test.py`, `pi_login_service_test.py`,
  `app_pi_providers_test.py`, `pi_login_ws_test.py`, plus `agent_wrapper_test.py`
  filter/refresh cases and harness-capability fixture updates. Frontend unit —
  `PiProvidersArea.test.tsx` (`groupProviders`), `tasks.test.ts`. Integration —
  `test_pi_providers_settings.py`, `test_pi_login_terminal.py`, `test_pi_paste_key.py`,
  `test_pi_model_picker_filter.py`, `test_pi_model_picker_empty_state.py`,
  `test_pi_picker_live_refresh.py`, `test_pi_turn_error.py` (extended). real_pi —
  `real_pi/test_provider_auth.py`.
- **Test suite status:** `just check` ✅ and `just test-unit` ✅ (backend / frontend /
  foundation / sculpt all OK) — re-run during this review.
- **Integration tests:** the 7 new pi integration files were run via the
  integration harness during this review — **8 passed in 38.76s** (filter, empty
  state, providers settings, login terminal, paste-key ×2, live refresh, turn-error
  CTA).
- **real_pi conformance:** gated by `@real_pi` (needs the real binary +
  `ANTHROPIC_API_KEY`); not executed in this review pass.
- **Nothing skipped / `xfail` / pending without justification.** One deliberate,
  documented automation gap: the interactive `/login` / `/logout` keystroke
  round-trip (provider selector → key entry → pi writes) is **not** automated —
  `real_pi/test_provider_auth.py` states the TUI selector is too fragile to
  keystroke-drive deterministically and substitutes the paste-key write path to
  prove "pi honors the Sculptor-written file." This is reasonable, but it means the
  headline REQ-AUTH-1 path is verified only by hand against the real binary — see
  Code Review Findings (MEDIUM).

## Code Review Findings

Output of the configured `/code-review-checklist` skill (diff `origin/main...HEAD`,
goal `agent_docs/pi-auth/spec.md`):

### Correctness

**LOW — ACCEPTED (confirmed real; follow-up SCU-1583)** — `ModelSelector.tsx:84`. The
empty-state branch fires whenever `sourcesBackendModels && models.length === 0`.
`backendModels` comes from `taskAvailableModelsAtomFamily`, which collapses to
`EMPTY_MODEL_OPTIONS`, so `[]` means *both* "still loading" and "genuinely empty",
and `selectedModelId` is null in both cases too — the frontend has no signal that
distinguishes them. `AlphaChatInterface.tsx:629` renders `ChatInput` (hence
`ModelSelector`) for any non-`ERROR` task status, with no "agent ready" / "models
loaded" gate. The start-time catalog probe (`_eager_fetch_pi_models_into_state`,
`run_agent/v1.py:220`) runs *after* the task is observable and persists models only
at `finalize_task_setup`, so a freshly-started **authenticated** pi agent shows
"No models available — please log in to authenticate" for ~1–3s until the probe
lands. Confirmed real via code analysis; brief and self-correcting.

**Decision (reviewed with the user):** accept for this PR. The only robust fix is a
backend `model_catalog_fetched` signal threaded to the frontend (`AgentTaskStateV2`
→ persist paths, including the empty no-auth case currently short-circuited at
`v1.py:854` → task view → a frontend atom/hook → gate the empty state on it) — ~7
files plus `generate-api` and tests, on the headline model-loading path. A
frontend-only gate on task status was considered but its correctness depends on the
exact status during the probe window (the task may be `RUNNING`, not `BUILDING`,
during the probe), so it is not reliable. Disproportionate for a transient LOW;
deferred to a follow-up (see *Deferred follow-ups* below).

**LOW — RESOLVED (commit `c34425a`)** — `pi_login_service.py` + `web/app.py`
`pi_login_websocket`. On the normal "Done" flow both `finishPiLogin` (the `/done`
endpoint) and the WebSocket close handler called `teardown()`, so
`broadcast_pi_models_refresh` fired twice per session. `teardown` now broadcasts
only from the call that actually unregisters the PTY; later no-op teardowns return
early. A test asserts the single broadcast.

### Consistency with stated goal

No functional scope creep — every change maps to a `REQ-*`. The `is_subscription`
catalog flag is the one artifact carried beyond what v1 consumes (see Dead code).
Disconnect is correctly offered only for `auth.json`-backed providers (env-only
"Connected" providers show "clear that variable to disconnect" instead), matching
the planning decision that pi's `/logout` only clears `auth.json` entries.

### Test coverage

**MEDIUM** — `real_pi/test_provider_auth.py`. The interactive `/login` / `/logout`
keystroke round-trip (REQ-AUTH-1/US-3, the feature's headline path) has no automated
real-binary coverage; it is documented as verified by hand. Automated real_pi
coverage exercises only the paste-key write path. Acceptable given the TUI
fragility, but worth conscious sign-off since it is the primary auth path.

### Proof of work completeness

Stated goal is a spec, not an autonomous-workflow MR body — section skipped.

### Dead code & leftover artifacts

**LOW — RESOLVED (commit `f0bd95e`)** — `provider_catalog.py:241`
`iter_single_key_env_var_names()` was defined and unit-tested but never called by
production code; env detection in
`authenticated_providers.py:detect_env_authenticated_provider_ids` iterates the
catalog directly. Removed the dead function and its unit test.

**LOW — RESOLVED (commit `b803f28`)** — `is_subscription` / `isSubscription` was
plumbed full-stack (`provider_catalog.py` → `ProviderAuthStatus` →
`AuthenticatedProviderEntry` API type → frontend type) but never read by any UI
logic — only set in the catalog and referenced in a test fixture. Removed the dead
field from the catalog, the auth-status model, and the API response (the generated
frontend type regenerates without it); integration tests still green.

### Comments

**LOW — RESOLVED (commit `771444b`)** — Several shipped comments/docstrings carried
plan-phase / requirement references that should stand on their own:
`PiProvidersArea.tsx` ("Task 4.2"), `agent_wrapper.py` `_handle_refresh_models`
docstring ("Task 5.1's …"), `agent_wrapper_test.py` ("REQ-COMPAT-2"), docstrings in
`pi_login_service_test.py`, `pi_login_ws_test.py`, `test_pi_login_terminal.py`
("Task 7.1"), and `test_pi_picker_live_refresh.py` ("REQ-FILTER-3"). Reworded each
to describe the behaviour directly.

### Error handling

No issues found. `read_auth_json_provider_ids` catches `OSError` /
`json.JSONDecodeError` narrowly and is intentionally best-effort; `write_auth_json_entry`
raises a typed `PiAuthJsonError` and leaves a garbled file untouched (tested);
`_write_auth_json_atomically` catches `BaseException` only to unlink the temp file
then re-raises. Frontend catches are scoped and set actionable messages.

### Security & secrets

No issues found. Paste-key values are written only to `auth.json` (`0600`, temp-file +
`os.replace`) and never logged; the login service logs `login_id` / mode only. The
PTY runs the server-resolved `pi` binary plus fixed `/login` / `/logout` strings (no
injection from `provider_id`, which `spawn` discards). Endpoints sit behind
`get_user_session`; the WS route mirrors the existing agent-terminal 4404 contract.

### Type safety

No issues found. New structures are Pydantic models; the empty-vs-Claude signal
reuses the harness's existing `sources_backend_models()` method (from the
graduated model-selection work) rather than adding a new capability field.
`just check` (typecheck + `generate-api`) passes.

### Backwards compatibility

No issues found. `HarnessCapabilities` is computed per request by `get_capabilities()`
(not persisted), so the new required field needs no migration.
`RefreshModelsUserMessage` is an additive member of the persisted
`PersistentUserMessageUnion` (old messages don't use it; new ones round-trip).
Frontend and backend ship together (types regenerated).

### Frontend issues

**MEDIUM — RESOLVED (commit `1391558`)** — `common/state/atoms/piAuthenticatedProviders.ts`
cached the `GET /api/v1/pi/providers/authenticated` response in a Jotai `loadable`
async atom with a manual `refreshPiProvidersAtom` counter — the
`no_bespoke_fetch_caching` / `use_tanstack_for_pulled_data` anti-pattern. Replaced
it with a `usePiAuthenticatedProviders` TanStack hook (modeled on the existing
global-read hook `useTerminalAgentRegistrations`): a `["sculptor","pi",…]` query
key, `staleTime: 0`, and caller-driven `refetch`. The credential-change flows now
call `refetch` instead of bumping a counter, gaining in-flight de-duplication and
request cancellation on unmount; the old atom file is deleted. Settings integration
tests (providers/paste-key/login-terminal) still green.

No effect anti-patterns (the new components use no `useEffect` — they derive during
render and act in event handlers), atom accessors are appropriately narrow
(`useSetAtom` for the refresh counter, `useAtomValue` for reads), and
`PiProvidersArea` is well-decomposed into sub-components rather than monolithic.

### Integration test issues

**LOW — RESOLVED (commit `5310f1d`)** — `use_pom_hierarchy`.
`test_pi_model_picker_empty_state.py` and `test_pi_turn_error.py` reached
`page.get_by_test_id(...)` directly for `PI_PICKER_EMPTY_STATE` /
`PI_PICKER_LOGIN_CTA` / `PI_ERROR_LOGIN_CTA` in the test body. Added
`get_picker_empty_state` / `get_picker_login_cta` / `get_error_block_login_cta`
accessors to the chat-panel page object and routed both tests through them.

**LOW (informational)** — several `to_be_visible(timeout=30_000)` calls equal the
harness default (30s), so they aren't "lowered" timeouts, just redundant explicit
args. Isolation is solid throughout (`PI_CODING_AGENT_DIR` → `tmp_path` in every
test), launch-mode markers are correct (browser-mode UI; `@real_pi` for the gated
suite), and no test is layout-only.

### Style guide & ratchets

No issues found. `just ratchets` passed inside `just check`. Imports are top-level,
no relative imports, booleans are prefixed, `_PI_TUI_READINESS_SECONDS` is a named
constant, and there are no mutable default args. (The plan-reference comments are
tracked under Comments.)

### Git hygiene

No issues found. Commits are atomic and per-task with descriptive subjects.

### Public-facing text

**LOW** — commit subjects use an internal `Task N.N:` prefix (e.g. "Task 5.1: Filter
the pi model picker…"). These are low-value internal plan references in a
world-readable repo, but contain no secrets, PII, customer data, or internal
hostnames. Consider dropping the prefix in a squash; not required. The committed
`agent_docs/pi-auth/*` docs describe the feature at a safe altitude with no
sensitive content.

### Code-review summary

- The change accomplishes the stated goal: provider auth is organic from Settings and
  the picker is authenticated-only, with all REQs covered and tests green.
- Top items to weigh before merge: (1) the loadable-atom vs TanStack data-hook
  question (MEDIUM); (2) conscious sign-off that the interactive `/login` round-trip
  is hand-verified only (MEDIUM); (3) trivial cleanup of dead `is_subscription` /
  `iter_single_key_env_var_names` plumbing and plan-reference comments (LOW).
- Nothing blocks the change.

## Deferred Follow-ups

- **[SCU-1583](https://linear.app/imbue/issue/SCU-1583) — pi model picker empty-state
  CTA flashes during authenticated agent startup.** Confirmed real but brief
  (~1–3s, self-correcting); the robust fix is a backend `model_catalog_fetched`
  signal threaded to the frontend (~7 files + `generate-api` + tests). Accepted as a
  known transient for this PR; deferred per review decision.

## Overall Assessment

**Ready to merge.** The data-hook MEDIUM was resolved during review (converted to a
TanStack hook, `1391558`). One MEDIUM judgement call remains:

- **Interactive-login coverage** — the primary auth path is verified by hand against
  the real binary, not automated. Acceptable given pi's TUI fragility, but it should
  be an explicit, recorded acceptance.

The two LOW correctness items raised in review are both closed: the double
refresh-broadcast was fixed (`c34425a`), and the empty-state loading flash was
confirmed real but brief/self-correcting and accepted with a follow-up (SCU-1583).
The biggest residual risk is the unautomated interactive login flow regressing
silently; a lightweight smoke check or a documented manual checklist would mitigate
it. All verification re-run during this review is green: `just check`,
`just test-unit`, and the new integration files; each in-review fix was re-verified
before commit.
