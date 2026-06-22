# Pi Provider Authentication — Mock Context

## Description

A Sculptor **Settings → Pi → Providers** area for authenticating pi's many
LLM providers (Anthropic, OpenAI, Google, OpenRouter, Groq, Mistral, xAI,
DeepSeek, and the multi-value providers Azure / Bedrock / Cloudflare), plus an
**authenticated-only** pi model picker that extends the #53 provider-grouped
dropdown.

Anchored to the locked decisions in `agent_docs/pi-auth/requirements.md`:

- `~/.pi/agent/auth.json` is the shared, bidirectional source of truth. Sculptor
  reads the user's existing pi credentials (US-1: zero re-auth) and persists
  anything it helps configure back to the same file (US-2: persist for real pi).
- **Primary authenticate action = interactive pi `/login`** (US-3): the
  affordance opens an interactive `pi` in Sculptor's terminal-agent stack at its
  login screen; pi writes its own `auth.json`. Covers API-key *and*
  OAuth/subscription providers.
- **Disconnect = pi's native `/logout`**, driven through the same interactive
  terminal path.
- **Optional power-user path:** a "paste API key" form → merge-safe `auth.json`
  write (literal key or `$ENV` pointer).
- **Authenticated-set filter:** the model picker shows ONLY models for providers
  in `keys(auth.json) ∪ env-detected`. Empty state message is locked verbatim:
  *"No models available — please log in to authenticate"* with a login CTA.
- **Multi-value providers** (Azure/Bedrock/Cloudflare) work in-session via env
  vars; full standalone persistence is deferred — surfaced as a distinct state.
- No `settings.json` defaults written; active-model selection stays with the #53
  picker.

Visual anchor: Sculptor's dark default theme (monochrome gray accent, indigo
`#3d63dd` primary buttons, green = connected, red = disconnect), the existing
`PiSettingsSection` card + `SettingRow` layout, the `SettingsPage` left-nav
shell, and the `ModelSelector` / `ModelSelectOptions` ghost-`Select` dropdown.

## Decisions

- **Chosen direction: Variant C — Master / detail.** A provider rail on the left
  (grouped Connected / Available / Session-only, with status dots), a detail pane
  on the right that shows the selected provider's auth status, models unlocked,
  and actions. The `pi /login` terminal is **embedded inline in the detail pane**
  (not a modal), and the "Paste API key" power-user path is a **collapsible inside
  the pane**. Scales well to many providers and gives per-provider detail + the
  terminal room to breathe.

End-to-end flow the chosen mock settles (consistent across all variants, anchored
to `requirements.md` — lift-ready for the spec):

- **Authenticate = interactive `pi /login`**, launched into the detail pane via
  Sculptor's terminal-agent stack. One path covers both API-key and
  OAuth/subscription providers; pi writes its own `~/.pi/agent/auth.json`.
- **Disconnect = `pi /logout`**, shown running inline in the detail pane; the
  provider then moves from the Connected rail group back to Available. (Open
  question per requirements: per-provider vs all-at-once granularity — mock shows
  per-provider.)
- **Paste API key = secondary, collapsible path** inside the pane. Choice of a
  literal key or a `$ENV`/`!command` reference; written merge-safe to `auth.json`
  (mode `0600`), other entries untouched.
- **US-1 zero re-auth is visible:** the Connected rail group is pre-populated from
  the user's existing `auth.json` (a "imported from ~/.pi/agent/auth.json"
  affordance), no re-entry required.
- **Model picker (extends #53):** shows **only authenticated providers' models**,
  grouped by provider. Empty state uses the locked copy verbatim — *"No models
  available — please log in to authenticate"* — with an "Open pi login" CTA that
  routes into the same `/login` flow.
- **Session-only providers** (Azure / Bedrock / Cloudflare) appear as a distinct
  rail group with an explicit "works this session; full standalone persistence
  later" explainer, reflecting the deferred multi-value scope.
- No `settings.json` defaults are written; active-model selection stays with the
  #53 picker.

## Rejected Alternatives

- **Variant A — Unified single list.** One flat, dense list with a per-row status
  + single contextual action and an overlay terminal. Rejected in favor of C's
  master/detail, which gives the terminal and per-provider detail more room.
  (Kept in `mocks.html` for reference.)
- **Variant B — Connected vs. Add (two sections).** Connected provider cards with
  model chips over an "add a provider" grid; centered modal login. Rejected in
  favor of C; its model-chip idea and "what this unlocks" framing may still be
  worth grafting into C's detail pane. (Kept in `mocks.html` for reference.)

## Tweaks Log

- Requested: After reviewing all three in Chrome, chose Variant C (master/detail)
  as the direction.
  Changed: Recorded C as the decision; moved A and B to Rejected Alternatives
  (kept in HTML). Made C the default-active tab on load and marked it as the
  chosen direction in the tab bar.
- Requested: Skip further UI refinement for now — proceed to build the end-to-end
  flow; UI polish is a later priority.
  Changed: Expanded Decisions into a lift-ready end-to-end flow summary for the
  Spec agent (authenticate, disconnect, paste-key, US-1 import, model picker +
  empty state, session-only providers) and wrapped up the mock session.
