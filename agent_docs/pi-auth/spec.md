# pi Provider Authentication & Authenticated-Only Model Picker

## Mocks

See [mocks.html](./mocks.html) for interactive HTML mocks. The chosen direction is
**Variant B (Connected vs. Add)**: a **Connected** list of provider cards (each
naming how it authenticated, with a Disconnect action) over an **Add a provider**
grid of the remaining single-key providers, plus a Session-only explainer callout.
`pi /login` (and `/logout`) open in a **centered modal**, and the paste-key path is a
"Paste API key instead" switch inside that modal. Variants A and C are retained in
the file as record (see Rejected Alternatives in [mocks.context.md](./mocks.context.md)).

## Overview

pi differs from Claude: it authenticates to *many* LLM providers (Anthropic,
OpenAI, Google, OpenRouter, Groq, Mistral, xAI, …) and its model catalog spans
all of them. Today Sculptor's pi already inherits the user's environment and
reads their global `~/.pi/agent/auth.json`, but:

- There is **no Settings affordance** to authenticate a provider for pi — a user
  must already have set env vars or used standalone pi.
- The model picker (shipped in #53) shows pi's **full, presence-gated catalog**,
  which can include providers the user is not actually authenticated for, and
  gives no guidance when nothing is authenticated.

This feature makes provider auth **organic from Sculptor's Settings page** and the
model picker **authenticated-only**, treating pi's own `~/.pi/agent/auth.json` as
the **shared source of truth** so Sculptor-managed pi and standalone pi converge.
It builds on #53's `supports_model_selection` seam. **pi-core is immutable** — all
pi-side reach is via the pinned extension set, Sculptor-side wiring, and driving
pi's own interactive `/login`.

Full requirements, the three user stories, and the empirical phase-0 feasibility
spike (pi 0.78.0) are recorded in [requirements.md](./requirements.md).

## User Scenarios

The pi provider-auth UI is a two-section **"Providers" area** in Settings → Pi
(Variant B): a **Connected** list of provider cards (each with its auth source and a
Disconnect action) over an **Add a provider** grid of the remaining single-key
providers, with Azure / Bedrock / Cloudflare in a **Session-only** explainer
callout. Authenticate / Disconnect / Paste key all run in a centered modal.

### US-1 — Existing pi user: zero re-auth `REQ-FILTER-1` `REQ-FILTER-2` `REQ-UI-2`
A developer already uses standalone pi and has authenticated Anthropic + OpenAI
(entries in `~/.pi/agent/auth.json`). They start a pi workspace in Sculptor. The
model picker shows exactly their Anthropic + OpenAI models — nothing else — with
no extra steps. In Settings, the **Connected** section is pre-populated from
their existing `auth.json` (an "imported from `~/.pi/agent/auth.json`" affordance);
nothing to re-enter.

### US-2 — New pi user: authenticate once, persists for real pi `REQ-AUTH-1` `REQ-PERSIST-1`
A developer new to pi opens Settings → Pi → Providers, sees no Connected section
yet, picks a provider from the **Add a provider** grid, and clicks **Open pi login**.
An interactive `pi` session opens in a **centered modal** at `/login`; they
complete it and pi writes `~/.pi/agent/auth.json`. The provider moves to Connected
and the picker offers its models. Standalone pi later reuses the same file.

### US-3 — Interactive login is the primary path `REQ-AUTH-1` `REQ-AUTH-2` `REQ-UI-3`
"Authenticate" always routes through an interactive `pi /login` embedded in a
centered modal (Sculptor's terminal-agent stack); pi owns the write. One path covers
API-key and subscription/OAuth providers alike.

### Power-user paste `REQ-AUTH-4` `REQ-UI-4`
A "Paste API key instead" path inside the login modal lets a user enter a
literal key or a `$ENV` / `!command` reference; Sculptor performs a merge-safe
`auth.json` write (`0600`), leaving all other entries untouched.

### Disconnect a provider `REQ-AUTH-3`
From a Connected card the user disconnects; Sculptor drives pi's `/logout` in the
modal, as-is. Whatever `/logout` clears moves from Connected back to the Add grid and
leaves the picker, which refreshes live (`REQ-FILTER-3`). (The mock assumes
per-provider; if pi's `/logout` granularity differs, the UI is adjusted to match.)

### Session-only (multi-value) providers `REQ-PERSIST-3`
Azure / Bedrock / Cloudflare appear in a distinct **Session-only** explainer callout
noting that they work this session via env vars and that full standalone persistence
is deferred.

### Empty / not-authenticated state `REQ-ERR-1` `REQ-UI-5`
With nothing authenticated, the model picker is empty and shows the verbatim
message *"No models available — please log in to authenticate"* with an "Open pi
login" CTA that routes into the same `/login` flow; an attempted turn surfaces the
same actionable message.

## Requirements

### Authentication (REQ-AUTH)
- **REQ-AUTH-1 (MUST):** Settings MUST provide an "Authenticate a provider" action
  that opens an interactive pi session at `/login` (reusing the terminal-agent
  stack), so pi writes its own `~/.pi/agent/auth.json`.
- **REQ-AUTH-2 (MUST):** Interactive login MUST operate on the user's global pi
  config dir (no isolated `PI_CODING_AGENT_DIR`), so credentials are shared with
  standalone pi.
- **REQ-AUTH-3 (SHOULD):** Settings SHOULD offer disconnect, driven through pi's
  native `/logout` **as-is** (no Sculptor-side credential deletion). Disconnect
  granularity follows pi's actual `/logout`; the mock assumes per-provider, and if
  `/logout` differs the UI/mock is adjusted to match at that point.
- **REQ-AUTH-4 (MAY):** Settings MAY offer a power-user "paste API key" form that
  performs a merge-safe `auth.json` write (preserving unknown/OAuth entries; `$ENV`
  pointer or literal; file mode `0600`).

### User interface (REQ-UI)
- **REQ-UI-1 (MUST):** The pi provider-auth UI MUST live in Settings → Pi as a
  two-section "Providers" area: a Connected list of provider cards over an
  Add-a-provider grid of the remaining single-key providers, with multi-value
  providers in a Session-only explainer callout.
- **REQ-UI-2 (MUST):** The Connected group MUST be populated from the user's
  existing `auth.json` (US-1) with no re-entry.
- **REQ-UI-3 (MUST):** The interactive `pi /login` MUST render embedded in a
  centered modal, via the terminal-agent stack.
- **REQ-UI-4 (SHOULD):** The paste-key path SHOULD be a secondary control reached
  via "Paste API key instead" inside the login modal.
- **REQ-UI-5 (MUST):** The model picker's empty state MUST show the verbatim copy
  "No models available — please log in to authenticate" with a CTA that opens the
  login flow.

### Authenticated-set filtering (REQ-FILTER)
- **REQ-FILTER-1 (MUST):** The model picker MUST list only models for providers the
  user is authenticated for. Authenticated set = `keys(auth.json)` ∪ providers with
  a detected API-key env var.
- **REQ-FILTER-2 (MUST):** Filtering MUST happen Sculptor-side — pi's
  `get_available_models` gates on credential *presence, not validity*, and can
  surface stray ambient providers. Chokepoint: the pi agent's model curation
  (`_curate_models` / `_fetch_models_into_state`).
- **REQ-FILTER-3 (MUST):** The authenticated set + model picker MUST reflect
  credential changes (after login/logout/paste) on the running agent **without a
  restart** — e.g. re-read `auth.json` / re-probe the catalog when the inline
  `/login` (or `/logout`) terminal closes.

### Persistence (REQ-PERSIST)
- **REQ-PERSIST-1 (MUST):** Credentials a user provides via Sculptor MUST persist in
  pi's own store (`auth.json`) so standalone pi reuses them.
- **REQ-PERSIST-2 (MUST):** Single-key providers (Anthropic, OpenAI, Google,
  OpenRouter, Groq, Mistral, xAI, DeepSeek, …) MUST be fully supported in v1.
- **REQ-PERSIST-3 (MAY):** Multi-value providers (Azure, Bedrock, Cloudflare) MAY
  work in-session via env vars; full standalone persistence of their non-key config
  is explicitly deferred to a future cycle.

### Error / empty state (REQ-ERR)
- **REQ-ERR-1 (MUST):** When no provider is authenticated (empty catalog), Sculptor
  MUST surface an actionable message — *"No models available — please log in to
  authenticate"* — extending the existing empty / failed-turn surface, with a route
  to the interactive `/login`.
  > **Follow-up — see `agent_docs/no-usable-model-guard/design.md`.** As shipped, a
  > *previously-selected* model is retained even with no providers, so the "empty
  > catalog" precondition here is unreachable in that case and the turn is allowed to
  > run and crash. The follow-up empties the catalog for an unusable selection and adds
  > a pre-send guard (a generic "Go to harness configuration" CTA) so this message is
  > shown *before* a doomed send, not after.

### Compatibility (REQ-COMPAT)
- **REQ-COMPAT-1 (MUST):** Claude's model selection and all non-pi behavior MUST
  remain unchanged.
- **REQ-COMPAT-2 (MUST):** #53's `supports_model_selection` seam (catalog fetch,
  `set_model`, provider-grouped picker) MUST keep working for already-authenticated
  pi.
- **REQ-COMPAT-3 (MUST):** No pi-core changes — pi-side reach is limited to the
  pinned extension set and driving pi's own interactive flows.

## Non-Goals
- Headless / non-interactive OAuth or subscription login (pi exposes none).
- Full standalone persistence of multi-value providers' non-key env config (deferred).
- Writing pi `settings.json` defaults (`defaultProvider` / `defaultModel`).
- An isolated Sculptor-managed `PI_CODING_AGENT_DIR` (we use the global config dir).
- Any change to Claude's harness or model picker.
- Modifying pi-core.

## Open Questions
- **Login terminal mechanism:** REQ-UI-3 fixes it embedded in a centered modal; the
  underlying mechanism (a transient terminal-agent instance vs. a registered
  terminal agent, plus lifecycle / return-to-Settings) is for `/architect`.
- **Empty-error wiring:** which surface carries the message (start-time 0-models
  path, the failed-turn error, or both) and how the CTA deep-links to login.
- **Test strategy:** `fake_pi` integration coverage (Settings UI, filtering,
  empty-error) vs. `real_pi` conformance (interactive `/login`, `auth.json`
  read/write round-trip).
- **Build-time check (not a blocker):** confirm pi `/logout` granularity against
  the real binary; if it is not per-provider, adjust the disconnect UI/mock to
  match (REQ-AUTH-3).
