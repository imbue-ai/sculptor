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

- **Chosen direction: Variant B — Connected vs. Add.** Two stacked sections: a
  **Connected** list of first-class provider cards (each naming how it
  authenticated, with a Disconnect action) over an **Add a provider** grid of the
  remaining single-key providers. The `pi /login` (and `/logout`) terminal opens in
  a **centered modal**, and the "Paste API key" power-user path is reached via a
  "Paste API key instead" switch **inside that modal**. Session-only providers
  (Azure / Bedrock / Cloudflare) are surfaced as one explainer callout. Emphasizes
  what you already have and keeps the terminal in a focused modal. (The shipped
  cards omit B's per-model chips — see the Tweaks Log.)

End-to-end flow the chosen mock settles (consistent across all variants, anchored
to `requirements.md` — lift-ready for the spec):

- **Authenticate = interactive `pi /login`**, launched in a centered modal via
  Sculptor's terminal-agent stack. One path covers both API-key and
  OAuth/subscription providers; pi writes its own `~/.pi/agent/auth.json`.
- **Disconnect = `pi /logout`**, shown running in the same modal; the provider
  then moves from the Connected section back to the Add-a-provider grid. (Open
  question per requirements: per-provider vs all-at-once granularity — mock shows
  per-provider.)
- **Paste API key = secondary path** reached via "Paste API key instead" inside
  the modal. Choice of a literal key or a `$ENV`/`!command` reference; written
  merge-safe to `auth.json` (mode `0600`), other entries untouched.
- **US-1 zero re-auth is visible:** the Connected section is pre-populated from
  the user's existing `auth.json` (a "imported from ~/.pi/agent/auth.json"
  affordance), no re-entry required.
- **Model picker (extends #53):** shows **only authenticated providers' models**,
  grouped by provider. Empty state uses the locked copy verbatim — *"No models
  available — please log in to authenticate"* — with an "Open pi login" CTA that
  routes into the same `/login` flow.
- **Session-only providers** (Azure / Bedrock / Cloudflare) appear as a distinct
  explainer callout — "works this session; full standalone persistence later" —
  reflecting the deferred multi-value scope.
- No `settings.json` defaults are written; active-model selection stays with the
  #53 picker.

## Rejected Alternatives

- **Variant A — Unified single list.** One flat, dense list with a per-row status
  + single contextual action and an overlay terminal. Rejected: less room for the
  terminal and per-provider detail than the chosen two sections. (Kept in
  `mocks.html` for reference.)
- **Variant C — Master / detail.** A provider rail beside a detail pane with the
  `pi /login` terminal embedded inline and a collapsible paste-key path. Initially
  chosen, then **superseded by Variant B** for a lighter, more scannable
  two-section layout with a focused modal login. (Kept in `mocks.html` for
  reference.)

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
- Requested: Switch the shipped Providers page from the master/detail layout to
  Variant B (Connected cards + Add-a-provider grid) with a centered modal for
  pi /login.
  Changed: Recorded Variant B as the chosen direction and moved Variant C to
  Rejected Alternatives. Two deviations from the B mock: the shipped cards omit
  per-model chips (they keep the card's auth-source line instead), and Disconnect
  stays an interactive pi /logout running in the modal rather than the mock's pure
  confirm dialog (pi /logout is a TUI the user drives).
