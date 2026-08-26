# No-usable-model guard — empty the catalog for an unusable selection, and route to harness configuration

Builds on the pi-auth work (provider auth + the authenticated-only picker) and the
`supports_model_selection` seam.

## Problem

Two coupled defects:

1. **The state can't represent "no usable model."** A pi agent's *selected* model is exempt
   from the authenticated-providers filter, so once a model has been picked, losing every
   provider leaves `available_models = [that one unusable model]` — never `[]`. The designed
   empty state is unreachable in exactly the case a user hits.
2. **The composer has no send-guard.** The stale model stays sendable, so a turn is sent and
   fails at provider-call time; the only remedy is a post-hoc error CTA.

## Decision 1 — empty the catalog for an unusable selection

Wherever the catalog is computed (start-time fetch, live credential refresh, the
pre-message probe, and the pre-workspace modal probe — see
`agent_docs/pi-modal-model-picker/spec.md`): if the selected model's provider is unauthenticated **and** no
authenticated fallback exists, drop the selection (`current_model → None`) so curation yields
`[]`. Emit that empty catalog rather than falling back to the built-in list.

**Invariant:** a retained `current_model` is always authenticated. Selection is tied to
availability, `available_models == []` means exactly "no usable model", and the contradictory
"no providers, yet a non-empty catalog" state can no longer be produced.

This closes the gap by **removing a representable-but-wrong state, not by adding one**: no
"providers active" flag joins the task state (it is derivable from `auth.json` at read); the
existing `available_models` is simply made truthful.

**Keep the cosmetic exemption.** The current model stays exempt from the *cosmetic* curation
rules (obsolete-id blacklist, dated-pin dedup, models pi does not enumerate) — those keep a
*usable* current model from vanishing. Only the auth-filter/no-fallback plank changes: when an
authenticated model remains, the agent switches to it; only when nothing authenticated remains
does the selection drop. The empty catalog is a designed surface (below), so reaching it —
including on a mid-session disconnect of the last provider — is correct, not a blank switcher.

## Decision 2 — picker disabled, Send replaced by a harness-config CTA

When the harness has no usable model:

- **Model picker: disabled** — it states the fact ("No models available") and carries no
  action.
- **Send button: replaced** by a single **"Go to harness configuration"** button that opens
  the harness's own configuration destination. No message can be sent.

One predicate drives both surfaces — **`hasNoUsableModel`** := the harness sources a backend
catalog **and** `available_models` is a fetched-but-empty `[]` (`NOT_FETCHED_YET`, still
loading, is excluded). It is defined once and shared, so the disabled picker and the blocked
Send cannot disagree. The guard blocks *every* send path — the keyboard send binding as well as
the button, since swapping the rendered button alone would leave the binding open.

### Harness-owned destination

The composer must not branch on harness identity. A **`configuration_settings_section()`** on
the harness returns the `SettingsSection` the CTA routes to — `PI` for pi, `DEPENDENCIES` by
default (Claude authenticates through its binary's login under Settings → Dependencies, not a
provider catalog). It is surfaced as a derived field on the task view and read once by the CTA.

- Not on `HarnessCapabilities` — that set is bool-only by contract.
- Not a frontend harness→section map — that needs harness identity on the task view, which the
  frontend deliberately never sees; it renders backend-owned facts and never branches on which
  harness it is.

Only a backend-catalog harness with zero providers can satisfy the predicate — pi today.
Claude's static list never empties, so its destination is defined for future harnesses but is
otherwise unread.

## Target state

| | Before | After |
|---|---|---|
| `available_models` (pi, no providers, had a selection) | `[selected]` | `[]` |
| Model picker | the stale, unusable model | disabled ("No models available") |
| Send | enabled → sent → fails at the provider | replaced by "Go to harness configuration" |
| Fix-it CTA | post-hoc, on the error | up-front, on the composer |
| Destination | pi-hardcoded | harness-owned (pi → Pi, else Dependencies) |

## Follow-up

Claude's destination (Settings → Dependencies) shows auth *status* but no sign-in action; an
actionable "Sign in to Claude" there would make it as useful as pi's. Not required by this
design — Claude cannot reach the predicate.
