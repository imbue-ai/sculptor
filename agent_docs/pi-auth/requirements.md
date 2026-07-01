# pi-auth — Requirements

Phase 6 of the pi multi-harness initiative (cycle slug: `pi-auth`). Follows the
graduated `pi-capabilities` cycle and builds directly on its
`supports_model_selection` seam (PR #53). pi-core is immutable: pi-side reach is
limited to Sculptor's pinned extension set + Sculptor-side wiring; anything that
would need a pi-core change defers.

## Goals

1. Let users authenticate pi's many LLM providers **organically from Sculptor's
   Settings page**, working *with* pi's native credential store
   (`~/.pi/agent/auth.json`) rather than around it.
2. Make the pi model picker list **only the models the user is actually
   authenticated for**, not pi's full (presence-gated) catalog.

## Durable design decision (locked)

**`~/.pi/agent/auth.json` is the shared source of truth, used bidirectionally.**
Sculptor reads the user's existing pi credentials and persists any it helps
configure back to the same file, so Sculptor-managed pi and standalone pi
converge on one credential set.

> This supersedes an earlier exploration of env-injection-only into an *isolated*
> `PI_CODING_AGENT_DIR`. The direction flip-flopped during the Q&A; it is now
> durable and explicitly recorded so later phases do not re-open it.

## User stories (the heart of this cycle)

### US-1 — Existing pi users: zero re-auth

A user who already uses pi independently has authenticated some subset of
providers. The moment they activate pi in Sculptor, they get **that entire set**
— no re-auth, no re-write, no extra environment variables to provide.

### US-2 — New pi users: provide once, persist for real pi

A user who does not use pi is prompted (in Sculptor) to provide keys/credentials
(exact entry UX deliberately unspecified for now). Whatever they provide **must
persist into regular pi's store**, so that if they later install unmanaged pi
they have the same set already.

### US-3 — Interactive auth via the shell / CLI-agent (opportunity, not a requirement)

Where a provider needs an interactive login, Sculptor *may* leverage the existing
terminal / "shell agent" capability to pop open an interactive pi at its auth
screen (`/login`) and let the user complete it there — pi writes its own
`auth.json`. This is an opportunity to exploit if it fits, **not** a mandated part
of the flow.

## Scope & locked decisions (v1)

- **Interactive pi `/login` is the PRIMARY authenticate action** (US-3): the
  "Authenticate a provider" affordance opens an interactive `pi` (terminal-agent
  stack) at `/login`; pi writes its own `auth.json`. Covers API-key *and*
  OAuth/subscription providers, makes pi own all writes (no clobber), and gives
  US-2 standalone-persistence for free.
- **Authenticated-set read + filter** (US-1 + goal #2): Sculptor computes the
  authenticated set (`keys(auth.json)` ∪ env-detected providers) and filters the
  picker to it. Read-only; no writes.
- **Optional power-user path:** a "paste API key" form → merge-safe `auth.json`
  write (`$ENV` pointer or literal).
- **Single-key providers fully covered** in v1 (Anthropic, OpenAI, Google,
  OpenRouter, Groq, Mistral, xAI, DeepSeek, …).
- **Multi-value providers** (Azure/Bedrock/Cloudflare) work **in-session via env
  vars**; their **full standalone persistence is DEFERRED to a future session**
  (their non-key config is not expressible in `auth.json`).
- **Disconnect/remove IS included** — via pi's native `/logout` (it "manage[s]
  OAuth or API-key credentials", `usage.md`), driven through the same
  interactive-pi terminal path.
- **No `settings.json` defaults** — Sculptor does not write `defaultProvider`/
  `defaultModel`; active-model selection stays with the #53 picker.
- **Actionable empty-catalog error:** extend the existing non-authenticated /
  empty-models failure to a clear message — *"No models available — please log in
  to authenticate"* — routing the user to the interactive `/login`.
- **Out of scope (v1):** headless OAuth/subscription login (pi exposes none);
  full standalone persistence of multi-value providers' env config.

## Established facts (phase-0 spike, pi 0.78.0 — empirical)

- **No headless auth interface.** Subcommands are `install/remove/update/list/
  config`; the only model RPCs are `set_model` + `get_available_models`; `/login`
  and `pi config` are interactive TUI. → programmatic auth = env vars and/or
  writing `auth.json`; interactive auth = US-3.
- **The catalog gates on credential PRESENCE, not validity.** `get_available_models`:
  no creds → 0 models; a present (even bogus) key → that provider's full model
  set; multiple → the union (measured: anthropic 24, google 16, openai 42). →
  Sculptor-side filtering keyed on the *known-authenticated* set is mandatory
  (a stray ambient provider key would otherwise leak into the picker).
- **A Sculptor-written `auth.json` is honored:** literal key works; `$ENV_VAR`
  (and `!command`, e.g. keychain / `op read`) indirection works (no plaintext
  needed); unknown/OAuth entries survive a read-modify-write **merge**. The file
  is created `0600`, and **`auth.json` credentials take priority over environment
  variables**.
- **`auth.json` top-level keys are the catalog provider identifiers** (e.g. Gemini
  → `google`; verified empirically `{anthropic, google}` → 24 + 16 models), each
  mapping to a conventional env var (full table in `.venv/pi/docs/providers.md`;
  authoritative source `packages/ai/src/env-api-keys.ts`). → authenticated set ≈
  `keys(auth.json)` ∪ providers-with-env-keys.
- **Multi-value providers (Azure, Bedrock, Cloudflare) draw their *non-key*
  config from environment variables, not `auth.json`** (region, base URL, account
  ID, gateway ID, AWS profile/IAM). An `auth.json` entry alone is insufficient for
  them, so persisting them "for real pi" (US-2) needs env persistence too.
- **US-3 is well-supported with no pi-core change.** Sculptor's terminal-agent
  stack (`TerminalHarness`, `run_terminal_agent_task_v1`, `SpawnedPtyProcess`
  with a parameterizable shell/command, `write_launch_command()`,
  `AgentTerminalPanel` xterm.js over `/api/v1/agents/{id}/terminal/ws`, and the
  `~/.sculptor/terminal_agents/*.toml` registry) can launch an interactive `pi`
  at `/login`; pi then writes its own `auth.json`.
- **`PI_CODING_AGENT_DIR`** redirects pi's whole config dir. Today Sculptor sets
  no override, so its pi already uses the user's global `~/.pi/agent` — i.e. US-1
  already holds at the pi runtime level; the gap is the Settings UX + accurate
  picker filtering.
- **Today's launch env** = `os.environ` ∪ project `.env` ∪ injected secrets;
  `api_key_env_var_names` (default `ANTHROPIC_API_KEY`) is read from `os.environ`
  and injected as a `Secret`. The pi subprocess already inherits the user's
  ambient provider keys.

## Open questions (for spec / build)

- Exact UX of the authenticated-providers list in Settings, and where the picker
  filter lives (`_curate_models` vs the harness `get_available_models`).
- `/logout` granularity (per-provider vs all) — confirm at build; affects the
  "Disconnect" UX.
- Wiring the empty-catalog error message to a one-click "open pi login" action,
  and exactly which existing surface it extends (the start-time 0-models path in
  `_fetch_models_into_state` and/or the failed-turn error surfacing added in #53,
  `test_pi_turn_error.py`).

_(Resolved: primary auth = interactive pi `/login` (US-3); single-key providers
full in v1, multi-value in-session-only with full persistence deferred; no
`settings.json` defaults; removal included via `/logout`; env-vs-`auth.json`
precedence — `auth.json` wins.)_
