# pi Provider Authentication & Authenticated-Only Model Picker — Architecture

## Executive Summary

This feature makes pi provider authentication organic from Sculptor's
Settings page and makes the pi model picker authenticated-only, treating pi's
own `~/.pi/agent/auth.json` as the shared, bidirectional source of truth. It
builds on PR #53's `supports_model_selection` seam: a new **Settings → Pi →
Providers** area (Connected cards over an Add-a-provider grid) drives pi's
interactive `/login` / `/logout` in a centered modal (via the terminal-agent stack)
and offers a power-user merge-safe paste-key write, while Sculptor-side filtering
narrows pi's
presence-gated catalog to the *authenticated set*
(`keys(auth.json) ∪ env-detected providers`).

**Before:** pi inherits the user's ambient env + global `~/.pi/agent`, but
there is no Settings affordance to authenticate a provider, and the #53 picker
shows pi's full presence-gated catalog (stray ambient keys leak in; an empty
catalog silently falls back to the Claude model list).

**After:** a Providers area lets a user connect/disconnect/paste a provider;
the picker lists only authenticated providers' models and refreshes live when
credentials change; an empty catalog shows a verbatim actionable
"log in to authenticate" message + CTA instead of the wrong Claude list.

## Current Architecture

```
                       SETTINGS (global route /settings)
  ┌───────────────────────────────────────────────────────────────┐
  │ PiSettingsSection.tsx  (SettingsSectionLayout / SettingRow)     │
  │   Binary Source · Status · Install · Pinned/Detected version    │
  │   · "API key env vars" list (PiConfig.api_key_env_var_names)    │
  │   → useUserConfig / onSettingChange(UserConfigField.PI, …)      │
  └───────────────────────────────────────────────────────────────┘
            no provider-auth affordance exists today ─┘

  PER-AGENT MODEL PICKER  (#53 supports_model_selection seam)
  ┌───────────────────────────────────────────────────────────────┐
  │ run_agent/v1.py                                                 │
  │   start: PiAgent.fetch_available_models_probe(secrets)          │
  │          (throwaway `pi --mode rpc --no-extensions` probe)      │
  │   running: PiAgent._fetch_models_into_state()                   │
  │          get_available_models + get_state(.model)               │
  │          → _model_option_from_pi → _curate_models  (blacklist,  │
  │            dated-pin dedup, newest-first sort)                   │
  │          → ModelsAvailableAgentMessage                          │
  │   → AgentTaskStateV2.available_models / current_model           │
  └───────────────────────────────────────────────────────────────┘
            │  harness.get_available_models / get_selected_model_id
            ▼
   taskAvailableModelsAtomFamily / taskSelectedModelIdAtomFamily
            │
            ▼  ChatInput → ModelSelector(backendModels, selectedModelId,
                                         onBackendModelChange)
   backendModels non-empty → grouped pi list (ModelSelectOptions,
                             getProviderDisplayName)
   backendModels EMPTY      → built-in Claude PRODUCTION_MODELS list  ← wrong for pi
            │
            ▼  onBackendModelChange → POST …/agents/{id}/set_model
               → SetModelUserMessage → _handle_set_model (between-turns RPC)

  TERMINAL-AGENT STACK  (local execution only)
  ┌───────────────────────────────────────────────────────────────┐
  │ create_workspace_agent (agent_type TERMINAL / REGISTERED)       │
  │   → run_terminal_agent_task_v1 (LocalAgentExecutionEnvironment) │
  │   → register_agent_terminal_config / create_agent_terminal      │
  │     (LocalTerminalManager, key "agent:<task_id>")               │
  │   → write_launch_command(manager, launch_command)               │
  │ WS  /api/v1/agents/{agent_id}/terminal/ws  ← keyed by task id   │
  │ FE  AgentTerminalPanel → useTerminal(terminalPath) (xterm.js)   │
  │ Registry: ~/.sculptor/terminal_agents/*.toml (load_registrations)│
  └───────────────────────────────────────────────────────────────┘
```

Established facts that shape the design (from the phase-0 spike, pi 0.78.0):

- pi has **no headless auth** — `/login` / `/logout` are interactive TUI only;
  the only model RPCs are `get_available_models` / `get_state` / `set_model`.
- `get_available_models` gates on credential **presence, not validity** — any
  present (even bogus) provider key yields that provider's whole model set, so
  a stray ambient key leaks into the picker. ⇒ Sculptor-side filtering is
  mandatory (REQ-FILTER-2).
- A Sculptor-written `auth.json` is honored (literal / `$ENV` / `!cmd`, mode
  `0600`); a read-modify-write **merge** preserves unknown/OAuth entries;
  `auth.json` takes priority over env vars.
- `auth.json` top-level keys equal the catalog provider ids; the provider →
  env-var → auth-key table lives in `.venv/pi/docs/providers.md`
  (authoritative source `packages/ai/src/env-api-keys.ts`).
- **All Sculptor agents run in a local execution environment today** (only
  `local_*` environments exist; the terminal handler asserts
  `LocalAgentExecutionEnvironment`). So a login shell's `$HOME` is the user's
  real home and `pi /login` writes the user's real `~/.pi/agent/auth.json`
  (REQ-AUTH-2 holds without an isolated `PI_CODING_AGENT_DIR`).

## Proposed Architecture

```
  SETTINGS → Pi → Providers   (Variant B: Connected cards + Add grid; global)
  ┌────────────────────────────────────────────────────────────────────┐
  │ Connected · N                                                        │
  │   ● anthropic · imported from auth.json   [Connected] [Disconnect]   │
  │   ● openai    · $OPENAI_API_KEY           [Connected] [Disconnect]   │
  │ Add a provider                                                       │
  │   [ google + ]  [ openrouter + ]  [ groq + ]  [ mistral + ]  …       │
  │ ⚠ Session-only: bedrock / azure / cloudflare — this session only     │
  │                                                                      │
  │ click an Add cell or Disconnect → centered modal (Radix Dialog):     │
  │   [Open pi login] → embedded xterm (useTerminal)  ·  [Paste API key] │
  └────────────────────────────────────────────────────────────────────┘
         ▲ reads                    │ writes              │ login/out (CHOSEN: 1b)
         │                          ▼                     ▼
  GET …/pi/providers/authenticated  POST …/pi/providers/  PiLoginService (no Task):
   = provider catalog table          paste-key (merge-safe  POST …/pi/login → id
     × { in auth.json? env set? }     auth.json 0600 write)  WS …/pi/login/{id}/ws
         │                                  │                LocalTerminalManager
         │                                  │                runs interactive pi
         │                                  │                + typed /login|/logout
         │                                  └──────────┬───────────┘
         │                          credential change → PTY teardown / paste write
         │                                              ▼
         │                       REFRESH all running pi agents (broadcast):
         │                       re-read auth.json + re-probe catalog,
         │                       re-emit ModelsAvailableAgentMessage (no restart)
         ▼
  Sculptor PROVIDER CATALOG TABLE (static; mirrors providers.md)
   provider-id ↔ env-var(s) ↔ display name ↔ group(single|session-only)
                ↔ subscription/OAuth flag
         │
         └──────────────► authenticated-set filter, applied in the pi wrapper
                           curation chokepoint (BOTH probe + running fetch):
                           keep option only if option.provider ∈
                           (keys(auth.json) ∪ env-detected providers)

  PER-AGENT PICKER, authenticated-only
   available_models now = curated ∩ authenticated set
   empty + sources_backend_models → ModelSelector EMPTY STATE (H):
     "No models available — please log in to authenticate" + "Open pi login" CTA
   failed turn (auth reason) → existing test_pi_turn_error block, CTA → login
```

The design adds **no pi-core changes** (REQ-COMPAT-3): all pi reach is the
existing RPCs, driving pi's own `/login` / `/logout`, and reading/merge-writing
`auth.json`. Claude's per-turn model path is untouched (REQ-COMPAT-1); the #53
seam keeps working for already-authenticated pi (REQ-COMPAT-2).

## Component Deep Dives

### A. Sculptor provider catalog table (new, static)

A single source-of-truth table, Sculptor-side, mirroring
`.venv/pi/docs/providers.md` (authoritative `env-api-keys.ts`). Each entry:
provider id (= `auth.json` key = catalog `provider`), conventional env-var
name(s), human display name, group (`single-key` vs `session-only`
multi-value), and whether it is subscription/OAuth. Backend owns the
authoritative copy (used for env detection + the Settings list); the frontend
already has a partial display-name map (`getProviderDisplayName`) that this
extends/derives.

- Single-key, v1 fully supported (REQ-PERSIST-2): anthropic, openai, google,
  openrouter, groq, mistral, xai, deepseek, cerebras, … (literal table from
  providers.md).
- Session-only multi-value (REQ-PERSIST-3): azure-openai-responses,
  amazon-bedrock, cloudflare-ai-gateway, cloudflare-workers-ai — env-only this
  session, full standalone persistence deferred.

YAGNI: a flat literal table, not a plugin/registry. It changes only when pi
ships a new provider; a stale entry degrades gracefully (unknown providers
still display via the capitalized-fallback path).

### B. Authenticated-set computation + picker filter (REQ-FILTER-1/2)

`authenticated = keys(auth.json) ∪ { p : env-var(p) present in os.environ }`.
Read-only. Two consumers:

1. **Per-agent filter** — the pi wrapper computes the set locally (it can read
   the user's global `auth.json` directly and inspect `os.environ`) and filters
   curated `ModelOption`s by `provider ∈ authenticated`. This is applied in the
   curation chokepoint so it covers **both** entry points:
   `fetch_available_models_probe` (pre-first-message) and
   `_fetch_models_into_state` (running agent). Filtering is layered with the
   existing `_curate_models` (blacklist / dated-pin / sort) — the current model
   is still always retained so the switcher never goes empty mid-session.

   > **Being revised — see `agent_docs/no-usable-model-guard/design.md`.** This
   > "current model always retained" plank makes the empty state unreachable once a
   > model has been selected: with no authenticated provider and no authenticated
   > fallback, the catalog resolves to `[<the one unusable model>]`, not `[]`. The
   > revision drops the selection in exactly that case (keeping the cosmetic
   > blacklist/dated-pin exemptions), so `available_models` reaches `[]` and the
   > REQ-UI-5 empty state actually renders.
2. **Settings list** — the same computation behind a global read endpoint (C).

### C. Settings → Pi → Providers UI (REQ-UI-1/2)

A two-section area inside the existing Pi settings section (Variant B). The catalog
table (B) splits into a **Connected** list of first-class cards (provider ∈
authenticated; each card names its source — `auth.json` import per US-1 / REQ-UI-2,
or env var — and carries a **Disconnect** action, E) over an **Add a provider** grid
of the remaining single-key providers; **Session-only** multi-value providers (with
the deferred-persistence explainer) sit in their own callout. Clicking an Add cell
opens the login modal (D), which also hosts **Authenticate** and the **Paste API
key** path (F, REQ-UI-4). Per the shipped scope the cards omit per-model chips.

Data: a new global read endpoint `GET /api/v1/pi/providers/authenticated`
returns the catalog × authentication status. Agent-independent (Settings is a
global route, not workspace-scoped).

### D. Interactive `/login` terminal in a modal — Settings-scoped ephemeral PTY (REQ-AUTH-1, REQ-UI-3) — **CHOSEN: 1b**

"Open pi login" opens an interactive `pi` at `/login` **embedded in a centered
modal** (Radix Dialog, not a tab); pi writes its own `auth.json` (REQ-AUTH-1/2).
Because Settings is a **global** route while terminal-agent Tasks are
workspace-scoped, the login PTY is decoupled from the Task machinery — a global
action does not fabricate a workspace.

A small backend **PiLoginService** owns the ephemeral PTY lifecycle, mirroring
the agent-terminal config registry pattern but with no Task / environment /
diff-refresher / tab:

- **Spawn.** `POST /api/v1/pi/login` (mode = `login` | `logout`, target
  provider) resolves the managed-or-custom `pi` binary via the
  dependency-management service (the same source backing Settings → Binary
  Source), constructs a standalone `LocalTerminalManager` with a synthetic
  `environment_id` (e.g. `pi-login:<nonce>`) and the user's home as the working
  directory, and starts the PTY. Launch env = the user's `os.environ` + PATH,
  so `pi` can do OAuth/browser/keychain and write the user's global
  `~/.pi/agent`. It explicitly does **not** set `PI_CODING_AGENT_DIR`
  (REQ-AUTH-2) and does **not** inject api-key secrets (the user is
  authenticating, not running a model). Returns a login-session id.
- **Drive.** The shell runs interactive `pi`; `/login` (or `/logout`) is typed
  into the PTY via the existing `write_launch_command` "type into the shell"
  mechanism (with on-screen guidance + a user-types fallback if pi's TUI
  readiness can't be detected reliably — a build-time detail).
- **Attach.** A new WS route `GET /api/v1/pi/login/{id}/ws` reuses
  `_connect_terminal_websocket`; the frontend reuses the same `useTerminal`
  (xterm) hook `AgentTerminalPanel` uses, pointed at this path. (The existing
  `/api/v1/agents/{id}/terminal/ws` route is left untouched — it requires a
  terminal-agent Task, which this path deliberately has none of.)
- **Teardown.** On the user finishing (clicks Done) / the shell self-exiting /
  the WS closing, `PiLoginService` stops the PTY and fires the refresh (G). The
  service holds the manager off a server-lifetime concurrency group so a
  navigated-away PTY is still reaped.

Disconnect (E) and login share this one mechanism (mode flag).

### E. Disconnect via `/logout` (REQ-AUTH-3)

Disconnect drives pi's native `/logout` **as-is** through the same modal terminal
path (no Sculptor-side credential deletion). Whatever `/logout` clears moves from
Connected back to the Add-a-provider grid; the picker refreshes live. The mock
assumes per-provider granularity; pi's actual `/logout` granularity is a
**build-time check** against the real binary — if it is all-or-nothing, the
disconnect UI is adjusted to match (the docs say "`/logout` to clear
credentials" without stating granularity).

### F. Power-user paste-key (REQ-AUTH-4, REQ-UI-4)

A form reached via "Paste API key instead" in the login modal: literal key or a
`$ENV` / `!command` reference. `POST /api/v1/pi/providers/paste-key` performs a **merge-safe**
read-modify-write of `auth.json`: read current JSON, set
`{provider}: {"type":"api_key","key": <value>}`, write back with mode `0600`,
preserving all unknown/OAuth entries. After the write, fire the same refresh as
the terminal-close path. Single-key providers only in v1 (REQ-PERSIST-2);
multi-value providers are not offered a paste form (REQ-PERSIST-3).

### G. Live refresh without restart (REQ-FILTER-3)

After login / logout / paste, running pi agents must re-reflect credentials
with no restart. Reuses the #53 between-turns pattern: a new input message
(analogous to `SetModelUserMessage`) tells a running agent to re-read
`auth.json`, re-run the fetch+filter (B), and re-emit
`ModelsAvailableAgentMessage` — the existing carrier the picker already
consumes. The trigger is the login PTY tearing down (D) or the paste write
completing (F).

**Scope: broadcast to all running pi agents.** Because the credential change is
global (`~/.pi/agent/auth.json` + env) and Settings has no "current agent"
concept, the refresh fans out to every running pi task. (Alternative — refresh
lazily on each agent's next turn — is simpler but violates the "without a
restart, when the terminal closes" intent for an idle agent; rejected.) An
agent mid-turn applies the refresh between turns, exactly like `set_model`.

### H. Empty / error state (REQ-UI-5, REQ-ERR-1) — **CHOSEN: both surfaces + a backend-catalog signal**

> **Amended — see `agent_docs/no-usable-model-guard/design.md`.** Two gaps surfaced
> after ship: (1) the "empty picker" below assumes the empty state is reachable at
> start-time, but a *previously-selected* model is retained even with no providers, so
> `available_models` is `[<that model>]`, not `[]` — the empty state never renders
> (fixed by emptying the catalog for an unusable selection). (2) The failed-turn surface
> is *post-hoc*: nothing guards the Send button, so the message is sent and crashes into
> `PiCrashError` first. The amendment adds a pre-send guard that replaces Send with a
> **generic** "Go to harness configuration" CTA (harness-owned destination: pi → Pi,
> Claude → Dependencies), so the crash path is never entered.

**Both** surfaces carry the verbatim copy "No models available — please log in
to authenticate":

- **Empty picker (start-time 0-models).** Today an empty pi catalog leaves
  `available_models` empty, so `ModelSelector` wrongly falls back to the Claude
  `PRODUCTION_MODELS` list. The fix is a **backend-catalog signal**: the
  harness's `sources_backend_models()` method (true for pi / false for Claude),
  provided by the graduated model-selection work and surfaced to the frontend
  the same way `supports_model_selection` already is (a derived view field, read
  through the existing gate — not a direct harness-capability read, honoring that
  ratchet). `ModelSelector` then branches: `sourcesBackendModels && backendModels
  empty` → the empty state (verbatim copy + "Open pi login" CTA, which opens D);
  otherwise → the Claude `PRODUCTION_MODELS` fallback, unchanged (REQ-COMPAT-1).
- **Failed turn.** `test_pi_turn_error.py` already renders a clean per-turn
  error block with a "Try another model" CTA when a turn fails on a provider
  with no/invalid key. Extend it so an auth-shaped failure's CTA also
  deep-links into the login flow (D).

Both CTAs route into the same PiLoginService `/login` flow (D). The "Open pi
login" CTA from the picker (in a workspace) deep-links to Settings → Pi →
Providers with the login pane open.

## Data Model Changes

- **No DB schema change.** `auth.json` is pi's own store (the credential source
  of truth); `AgentTaskStateV2.available_models` / `current_model` already
  exist (#53) and now hold the *filtered* set.
- **New API types (web/data_types):** an authenticated-providers response
  (catalog entry × {in auth.json?, env-detected?, group}); a paste-key request
  (provider id + key value/kind). Regenerate FE types (`just generate-api`);
  any new `ElementIds` for tests also require regeneration.
- **Picker signal (reused):** the harness's `sources_backend_models()` method
  (true for pi / false for Claude), from the graduated model-selection work,
  distinguishes "pi agent, empty authenticated catalog" from "Claude," surfaced
  to the frontend the same way `supports_model_selection` is, so empty ≠ Claude
  fallback (H). Avoids overloading `available_models` emptiness.
- **No `PiConfig` schema growth required** for v1 (auth.json is the store, not
  config). The existing `api_key_env_var_names` continues to drive env
  injection; env **detection** for the authenticated set derives from the
  provider table (B), which is broader than that injection list.

## Migration Strategy

No migration. The feature is additive: a new Settings area + endpoints, a new
filter applied to an already-curated catalog, and an extended empty/error
state. US-1 (existing pi users) works on first run because the wrapper reads
their existing `auth.json` (zero re-auth). No data backfill, no compatibility
window. Existing pi agents pick up filtering on their next catalog
fetch/refresh.

## Files to Modify / Create / Delete

**Create**

- Sculptor provider catalog table module (backend) — provider id ↔ env-var(s)
  ↔ display ↔ group ↔ subscription flag (mirrors `providers.md`).
- `auth.json` read + merge-safe write helper (backend) — read authenticated
  set; `0600` merge write for paste-key.
- Settings Providers UI components (frontend) — Connected cards + Add-a-provider
  grid + Session-only callout, plus a login modal (PiLoginDialog) hosting the
  embedded login terminal and the paste-key form.
- New endpoints in `web/app.py`: `GET …/pi/providers/authenticated`,
  `POST …/pi/providers/paste-key`, `POST …/pi/login`, and the WS route
  `GET …/pi/login/{id}/ws`.
- `PiLoginService` (backend) — ephemeral login/logout PTY lifecycle owner (no
  Task): spawn a standalone `LocalTerminalManager` running interactive pi, type
  `/login`|`/logout`, tear down + fire refresh on close.
- Integration tests (fake_pi) + real_pi conformance tests (Testing Strategy).

**Modify**

- `sculptor/agents/pi_agent/agent_wrapper.py` — authenticated-set computation;
  apply the filter in `_fetch_models_into_state` + `fetch_available_models_probe`
  (the `_curate_models` chokepoint); add the refresh-models input handler (G).
- `sculptor/agents/pi_agent/harness.py` — `sources_backend_models()` already
  returns True for pi (the signal H; reused from the graduated model-selection
  work, not added here).
- `frontend/.../PiSettingsSection.tsx` — host the new Providers area.
- `frontend/.../ModelSelector.tsx` + `ModelSelectOptions.tsx` — empty-state copy
  + "Open pi login" CTA, gated by the backend-catalog flag (H).
- `frontend/.../ChatInput.tsx` / model atoms (`common/state/atoms/tasks.ts`) —
  thread the backend-catalog flag to the picker.
- `web/app.py` model-state plumbing for the live refresh (G).
- `tests/integration/frontend/test_pi_turn_error.py` — failed-turn CTA deep-link
  to login (H).

**Delete**: none.

## Alternatives Considered

- **Put the filter in the harness `get_available_models` instead of the
  wrapper.** Rejected: the harness reads pre-persisted state and lacks the live
  `os.environ` / `auth.json` view; the wrapper is the only place that sees the
  real authenticated set at fetch time, and it must filter both the probe and
  the running fetch (REQ-FILTER-2 names the wrapper curation as the chokepoint).
- **Sculptor writes all credentials directly to `auth.json` (skip interactive
  `/login`).** Rejected by the locked decision: pi owns all writes (no clobber),
  one path covers API-key + OAuth/subscription, and US-2 standalone-persistence
  comes for free. Direct write survives only as the *optional* power-user
  paste-key path (F).
- **Isolated `PI_CODING_AGENT_DIR` per Sculptor.** Rejected (locked): the global
  `~/.pi/agent/auth.json` is the shared source of truth so standalone pi and
  Sculptor-managed pi converge.
- **Write pi `settings.json` defaults (`defaultProvider`/`defaultModel`).**
  Out of scope: active-model selection stays with the #53 picker.
- **UI Variant A (flat list) / Variant C (master/detail).** Variant C was the
  initial pick, then superseded by **Variant B (connected cards + add grid)** for a
  lighter two-section layout with a modal login; Variant A (flat list) stays
  rejected. (See the Tweaks Log in `mocks.context.md`.)

## Risks and Mitigations

- **pi-core feasibility (gate item).** The design needs no pi-core change: it
  uses only existing RPCs, drives pi's own `/login` / `/logout`, and
  reads/merge-writes `auth.json` — all empirically proven in the phase-0 spike.
  *No pi-core feasibility risk identified at the architecture gate.* The one
  open empirical item is `/logout` **granularity** (per-provider vs
  all-or-nothing), a non-blocking build-time check that only adjusts the
  disconnect UI (E).
- **`/login` is a TUI slash command, not a CLI flag.** The terminal hosts an
  interactive `pi`; reaching the `/login` screen may need a typed `/login`
  (injected into the PTY like `write_launch_command`, with a user-types
  fallback + on-screen guidance). Build-time detail; does not change the
  architecture.
- **Settings is global, terminal agents are workspace-scoped.** Resolved by 1b:
  the login PTY is decoupled from the Task machinery (PiLoginService + a new WS
  route, D). Residual cost — a second terminal WS route and a small PTY
  lifecycle owner — is the accepted price of not fabricating a workspace for a
  global action; mitigated by reusing `LocalTerminalManager`,
  `write_launch_command`, and `_connect_terminal_websocket` rather than new PTY
  plumbing.
- **Empty-catalog falls back to the Claude list (wrong for pi).** Mitigated by
  the `sources_backend_models` signal (H) so a pi agent with 0 authenticated
  providers shows the CTA, not Claude models.
- **Stray ambient provider keys.** The whole point of REQ-FILTER — the
  authenticated-set filter removes providers the user did not deliberately
  authenticate (presence-gated catalog leak).
- **Secret hygiene.** Paste-key values are written only to `auth.json` (`0600`,
  pi's own store) and never persisted in Sculptor config; `$ENV`/`!cmd`
  references avoid plaintext at rest.

## Testing Strategy

Split along the fake_pi / real_pi seam:

- **fake_pi integration (deterministic, no real pi):** the Settings Providers
  UI (Connected cards + Add grid grouping, modal login, modal paste-key); the
  authenticated-set **filter** (a fake catalog spanning providers ∩ a controlled
  `auth.json`/env shows only authenticated ones); the **empty state** (0
  authenticated → verbatim copy + CTA, not the Claude list); the failed-turn
  CTA (extending `test_pi_turn_error.py`); the live **refresh** after a
  simulated credential change.
- **real_pi conformance (real binary, gated):** the interactive `/login` /
  `/logout` actually drives pi and round-trips `~/.pi/agent/auth.json`; the
  merge-safe paste-key write preserves unknown/OAuth entries and produces a
  file real pi honors; `/logout` granularity (the build-time check).
- **Unchanged-behavior guards:** Claude's picker and per-turn model path
  (REQ-COMPAT-1); the #53 seam for already-authenticated pi (REQ-COMPAT-2).

## Open Questions

The cycle is feasibility-first; the pi-core feasibility is **clear** (see
Risks). All three architecture-level questions are now resolved:

1. **Login-terminal mechanism (REQ-UI-3) — 1b, Settings-scoped ephemeral PTY**
   (no Task; PiLoginService + a new `/pi/login/{id}/ws` route; D). Refresh
   trigger (REQ-FILTER-3): PTY teardown / paste write → **broadcast** re-read +
   re-probe + re-emit to all running pi agents (G).
2. **Empty/error wiring (REQ-UI-5, REQ-ERR-1) — both surfaces** (empty picker +
   failed-turn block), gated by the `sources_backend_models` signal so
   empty ≠ Claude fallback; both CTAs route into D (H).
3. **Test split — the drafted fake_pi / real_pi split** (see Testing Strategy).

**Remaining non-blocking item (does not gate the plan):**

- **Build-time check:** confirm pi `/logout` granularity (per-provider vs
  all-or-nothing) against the real binary; if not per-provider, adjust the
  disconnect UI/mock (E, REQ-AUTH-3).

**For the Spec tab (not blocking; flag only):** the spec's own Open Questions
list still frames items 1–3 as open — they are settled here. No spec change is
required to proceed, but the spec's Open Questions are now superseded by this
section.

**Build-time (non-blocking) check:** confirm pi `/logout` granularity against
the real binary; if not per-provider, adjust the disconnect UI/mock (E,
REQ-AUTH-3).
