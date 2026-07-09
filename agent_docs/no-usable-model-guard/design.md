# No-usable-model guard — empty the catalog for an unusable selection, and route to harness configuration

- **Status:** Design. Implementation pending (docs first; code "later").
- **Scope:** builds on `agent_docs/pi-auth/` (provider auth + authenticated-only picker)
  and the `supports_model_selection` seam (#53). No Linear ticket filed yet.
- **Owner:** design captured with Claude; decisions made by the maintainer.

## Summary

Two coupled defects, one design.

1. **The internal state cannot represent "no usable model."** For a pi agent, once a
   model has been *selected*, removing every provider (deleting `auth.json`) does **not**
   empty the catalog. The selected model is *exempt* from the authenticated-providers
   filter, so `available_models` resolves to `[<that one unusable model>]` — never `[]`.
   The designed "No models available — please log in to authenticate" empty state (and
   its login CTA) is therefore **unreachable** in the exact case a real user hits.

2. **The composer has no send-guard.** With that stale model still shown in the picker,
   the Send button stays enabled, the message is sent, and the turn crashes at
   provider-call time (`PiCrashError` → `ConcurrencyExceptionGroup("Agent crashed")`),
   surfacing an ugly two-block error whose only remedy is a *post-hoc* "Open pi login".

**The fix, in two decisions:**

- **Decision 1 (backend):** empty the catalog when the selected model's provider is
  unauthenticated **and** there is no authenticated fallback, so `available_models` reaches
  `[]` and the *already-built* empty state renders. (Chesterton's-fence-checked — §4.)
- **Decision 2 (frontend + a new harness seam):** when there is no usable model, replace
  the **Send** button with a **generic "Go to harness configuration"** button that routes
  to a **harness-owned settings destination** — pi → Settings → Pi, Claude → Settings →
  Dependencies — instead of letting the send fail into a crash.

The target external state matches the intended CTA: *"You have selected the Pi agent, but
you cannot send any messages until you authenticate with a provider."*

## The triggering scenario (empirically verified)

Reproduced in dev Sculptor and confirmed from the server log:

1. Select a pi model (e.g. `qwen/qwen3.7-max`, served via the `openrouter` provider) while
   providers are authenticated.
2. Delete `auth.json` (disables every provider). Restart.
3. The agent re-probes its catalog. Because the current model is exempt from the auth
   filter and there is no authenticated model to switch to, the catalog resolves to the
   single unusable model. The picker shows "Qwen: Qwen3.7 Max"; Send is enabled.
4. Send anything → the turn runs → the provider rejects it (no key) → crash.

Server-log evidence (paths elided), task `tsk_…zf3`, at the moment of the screenshotted send:

```
_reselect_unauthenticated_current_model: PiAgent current model qwen/qwen3.7-max is
    no longer authenticated and no authenticated model is available to switch to
_fetch_models_into_state:  PiAgent fetched 1 model(s) from pi at start; current model=qwen/qwen3.7-max
… (send) …
PiCrashError: "This model isn't available — it may require authentication with its
    provider. Try another model.\n\nDetails: No API key found for openrouter. …"
AgentCrashed("Agent crashed") → ConcurrencyExceptionGroup('Agent crashed', None, None) (2 sub-exceptions)
    → UnexpectedErrorRunnerMessage
```

Every catalog fetch that day returned **`1 model`**; the "found no usable models" (empty
`[]`) path was taken **zero** times. So the empty state is not merely rare here — it is
**structurally unreachable** for a user who had previously picked a model.

## Part 1 — Internal state: which flags represent it, and why they can't

### The fields in play

For a pi task, what the composer/switcher sees comes off `AgentTaskStateV2`, surfaced through
`CodingAgentTaskView` (`sculptor/sculptor/web/derived.py`):

| Field (backend → frontend) | Type | Value in the scenario | Meaning |
|---|---|---|---|
| `harness_capabilities.supports_model_selection` | `bool` | `True` | *static:* "this harness has a model picker" (`harness.py:160`) |
| `sources_backend_models` | `bool` | `True` | *static:* "catalog comes from the pi backend, not the built-in Claude list" (`harness.py:188`) |
| `available_models` | `list[ModelOption] \| ModelCatalogState` | **`[qwen]`** | the **only** field encoding "how many models" — tri-state: `NOT_FETCHED_YET` / `[]` / non-empty (`state/messages.py:50-69`) |
| `current_model` → `selected_model_id` | `ModelOption \| None` → `str \| None` | `qwen` | the persisted selection (`harness.py:181`) |

Provider authentication is **not on task state at all.** "Are any providers active" is only
ever computed by `compute_authenticated_provider_ids()` = `keys(auth.json) ∪ env-detected`
(`agents/pi_agent/authenticated_providers.py:71`), and is surfaced *only* to the Settings
page (`/pi/authenticated-providers`). The composer never sees it.

### The intended encoding — and why it fails

The design *intends* "Pi enabled, no providers, no models" to be:
`supports_model_selection=True ∧ sources_backend_models=True ∧ available_models == []`.
That empty list does triple duty: it is the "no models" signal, the (proxy for) "no
providers" signal, and the trigger for the `ModelSelector` empty-state CTA
(`ModelSelector.tsx:108-122`).

It is **not correctly capable** of representing the state, for three reasons:

1. **Three independent facts collapse into one overloaded value.** "no providers active,"
   "no models available," and "probe failed (best-effort)" all map to
   `available_models == []` (`tasks/handlers/run_agent/v1.py:877, 900`). There is no
   first-class "providers active" flag on task state — only a fragile proxy.
2. **The selection is decoupled from availability.** `current_model` / `selected_model_id`
   is a separate field with no invariant tying it to `available_models` or to
   authentication. So the *representable* state is the contradictory one we hit:
   **catalog `[qwen]`, selection `qwen`, providers `∅`** — a "usable" model that cannot run.
   (Corroborating: the crashed chat message even recorded `model_name=CLAUDE_4_OPUS` while
   pi ran Qwen — the Claude per-turn `model_name` field is meaningless for pi, which is
   server-driven via `current_model`.)
3. **`supports_model_selection` is capability, not liveness.** It stays `True` with zero
   usable models, so it structurally cannot carry "no models available."

**Nothing on the task state answers the real question — "is there at least one model I can
actually send to right now?"** That is the gap this design closes.

## Part 2 — Why the catalog isn't empty (the exact mechanism)

`_curate_models` (`agents/pi_agent/agent_wrapper.py:320-356`) trims pi's raw catalog and
**exempts the current model from every rule**, including the authenticated-providers
filter:

> "The current model is always kept even if a rule would drop it, so the switcher never
> shows an empty selection. … The current model is exempt from every rule, including this
> one."

`_reselect_unauthenticated_current_model` (`:1189-1221`) is meant to rescue a deauthorized
selection by switching to an authenticated model — but only if one exists:

> "with no authenticated alternative (the user disconnected their only provider) the
> current model is retained rather than blanking the switcher."

With zero providers there is no replacement, so the selection is retained and
`_curate_models` keeps it → `available_models = [qwen]`. The eager start-time probe
(`fetch_available_models_probe`, `:1308`) applies the same exemption and doesn't even call
the reselect, so a fresh restart lands on `[qwen]` directly.

## Decision 1 — Empty the catalog for an unusable selection

**Change:** when the current model's provider is unauthenticated **and**
`_reselect_unauthenticated_current_model` finds **no authenticated replacement**, drop the
selection (`current_model → None`) instead of retaining it. Then
`_curate_models(options, None, ∅) == []`, `available_models` becomes a fetched-but-empty
`[]`, and the existing `ModelSelector` empty state (login CTA) renders. Apply the same in
the probe path so a fresh restart also empties.

**Keep the rest of the exemption.** The current model stays exempt from the *cosmetic* rules
(the `claude-3-*` blacklist, dated-pin dedup, and "pi didn't enumerate it") — those protect
a **usable** model from vanishing. Only the *auth-filter, no-fallback* plank changes.

### Chesterton's fence — is the exemption safe to narrow?

Yes. The fence is real and deliberate (both commits are the maintainer's), but its
justification for the auth case has since expired:

- `0daafcaf` (Jun 17) introduced "always keeps the current model" **before** any auth
  filter or empty-state existed — it only guarded against the *cosmetic* rules dropping the
  model pi actually runs. **Legitimate; keep.**
- `b78cfe5d` (Jun 23) shipped the designed empty state ("No models available — please log
  in to authenticate").
- `2d86ec40` (Jun 24) added the reselect and chose "retain rather than blank" **one day
  after** the empty state already existed. The fear it guards — "a blank switcher looks
  broken" — was **already obsolete**: an empty catalog is now a *designed, meaningful
  surface*, not a broken one.

**What bull is let loose — by blast radius:**

- **Tear down the whole exemption (do NOT):** a valid, *authenticated* current model that
  trips a cosmetic rule (blacklisted id, dated-pin, or one pi doesn't list) vanishes from
  the picker → a blank "Select model" trigger while the agent runs fine. Real regression.
  Guarded by `test_curate_models_keeps_current_model_even_when_a_rule_would_drop_it` and
  `…_absent_from_catalog`.
- **Narrow to the auth-filter/no-fallback plank (the plan):** the only behavior genuinely
  changed is that a user who disconnects their **only** provider **mid-session** now sees
  the switcher go empty (the login CTA) instead of showing a dead model. That is arguably
  *correct*, and the **send-guard** (Decision 2), not the catalog, is the real protection
  against the crash.

**Not a fence to bulldoze — a single plank to remove**, and only because we ship the empty
state + send-guard that give "empty" a meaning.

## Decision 2 — Generic "Go to harness configuration" CTA + send-guard

### Target external state

When the harness has **no usable model**:

- **Model picker: empty.** For pi this is the existing "No models available — please log in
  to authenticate" empty state (now actually reached, per Decision 1).
- **Send button: replaced**, not merely disabled, by a **"Go to harness configuration"**
  button. Clicking it opens the harness's own configuration destination. No message can be
  sent; the crash path is never entered.

This replaces today's failure mode (send → `PiCrashError` → `ConcurrencyExceptionGroup` →
two red error blocks with a *post-hoc* "Open pi login") with an *up-front* actionable CTA.

### The generic seam (harness-owned destination)

The composer must not hardcode "Pi". Today the "authenticate" CTA is hardcoded to
`SettingsSection.PI` in **three** places (`ChatInput.tsx:500-502`,
`AgentSettingsControls.tsx:55-57`, and the `ModelSelector` `onAuthenticate` prop). Generalize:

1. **Backend:** add `configuration_settings_section(self) -> str` to the `Harness` ABC
   (`interfaces/agents/harness.py`), parallel to `sources_backend_models()`. Each harness
   owns its destination:
   - `PiHarness` → `"PI"`
   - `ClaudeCodeHarness` → `"DEPENDENCIES"`  (see rationale below)
   - base default → `"DEPENDENCIES"` (or `"GENERAL"`) — decide in review.

   Do **not** put this on `HarnessCapabilities` — that model is bool-only by contract
   (docstring-enforced).
2. **Derived view:** expose it as a `@computed_field` on `CodingAgentTaskView`
   (`web/derived.py`, beside `sources_backend_models`), delegating to `_resolve_harness()`.
   It rides the existing task snapshot to the generated TS twin automatically.
3. **Frontend:** read it via a `useTaskHelpers` accessor (like `useTaskSourcesBackendModels`)
   and have the composer call `useOpenSettings(task.configurationSettingsSection)` — the
   canonical navigator (`common/state/hooks/useOpenSettings.ts`) — instead of the hardcoded
   `SettingsSection.PI`. This collapses the three hardcoded sites into one harness-driven value.

### Claude's destination = `SettingsSection.DEPENDENCIES`

`SettingsSection` is a frontend-only enum (`pages/settings/sections.ts`, 15 members). Claude
authenticates **differently from pi**: not via a provider/API-key catalog, but via the
`claude` binary's `claude auth login` (OAuth/subscription), managed by
`DependencyManagementService` (`check_authenticated` / `start_auth_login` / `submit_auth_code`)
and surfaced under **Settings → Dependencies** (and first-run onboarding). That is already
where `ClaudeBinaryNotFoundError` routes (`AlphaErrorBlock.tsx:30-32`). The "Claude"-labeled
`AGENT` section holds only default-model / fast-mode / effort preferences — the wrong target.

> **Follow-up worth filing:** Dependencies shows Claude auth *status* but has no "Sign in to
> Claude" button in Settings today (only onboarding does). Landing the seam on an actionable
> control — reusing `POST /api/v1/dependencies/auth` — would make Claude's destination as
> useful as pi's. Not required for this change.

### The activation predicate ("no usable model")

- **pi:** `sources_backend_models && available_models` is a fetched-but-empty `[]`
  (i.e. `NOT_FETCHED_YET` excluded — that stays "Loading models…"). Decision 1 makes this
  reachable. Lift the predicate out of `ModelSelector` into a shared helper so the
  send-guard and the picker agree on one definition.
- **Claude:** sources a static built-in list, so "zero models" never fires on count; the
  seam is built generic for the **destination** and for future/other harnesses. Claude's
  own not-authenticated state is surfaced separately (onboarding + error blocks) and is out
  of scope for this send-guard — noted so we don't conflate the two.

The send-guard folds the predicate into the Send button's `disabled`/replace logic
(`ChatInput.tsx:788`, which today checks only in-flight / queued / empty-draft) and the
parallel `AgentSettingsControls`.

## Target states — before / after

| | Today (bug) | After |
|---|---|---|
| `available_models` (pi, no providers, had selection) | `[qwen]` | `[]` |
| Model picker | shows "Qwen: Qwen3.7 Max" (unusable) | empty state + login CTA |
| Send button | enabled → send → crash | replaced by "Go to harness configuration" |
| Error surface | `PiCrashError` + `ConcurrencyExceptionGroup` (2 blocks) | none — send is never attempted |
| CTA timing | post-hoc ("Open pi login" on the error) | up-front (on the composer) |
| CTA destination | hardcoded `PI` | harness-owned (`pi`→PI, `claude`→DEPENDENCIES) |

## Implementation scope (code — pending, "the spot" to update later)

Backend:
- `agents/pi_agent/agent_wrapper.py`: `_reselect_unauthenticated_current_model` returns
  `ModelOption | None` (drop on no-fallback); callers in `_fetch_models_into_state` and the
  probe path handle `None` → empty catalog.
- `interfaces/agents/harness.py`: new `configuration_settings_section()` on the ABC + per-harness overrides.
- `web/derived.py`: new `@computed_field` surfacing it.

Frontend:
- `common/state/hooks/useTaskHelpers.ts`: new accessor.
- shared helper for the "no usable model" predicate (next to `routeModelChange` in
  `common/modelConstants.ts`).
- `ChatInput.tsx` + `AgentSettingsControls.tsx`: send-guard + swap Send → "Go to harness
  configuration"; replace the hardcoded `SettingsSection.PI` with the harness value.
- `ModelSelector.tsx`: reuse the shared predicate; the empty-state CTA label/destination
  becomes harness-driven.
- `just generate-api` after new `ElementIds` / view fields.

## Test impact

- **Flip:** `test_curate_models_retains_current_model_even_when_provider_unauthenticated`
  and the reselect "only provider disconnected → retained" test now assert **drop → empty**.
- **Keep:** the two cosmetic-exemption tests
  (`…_keeps_current_model_even_when_a_rule_would_drop_it`, `…_absent_from_catalog`).
- **Add:** a send-guard test (no usable model → Send replaced, no POST), and a
  harness-destination test (pi→PI, claude→DEPENDENCIES).
- Integration: extend the pi empty-state / picker-live-refresh suites for the
  had-a-selection path.

## Documentation impact

- **Now (design docs):** this file; forward-pointer notes in `agent_docs/pi-auth/`
  (`architecture.md` §B and §H, `review.md` REQ-COMPAT-2) where the "current model always
  retained / never goes empty" invariant is asserted — those two statements are the only
  load-bearing contradictions.
- **On ship (shipped-behavior mirrors — do NOT edit ahead of the code, to avoid describing
  unshipped behavior as current):**
  - `docs/help/integrated_harnesses.md:60` ("picker stays empty … until you authenticate" —
    already inaccurate for a pre-selected model).
  - `docs/specs/SPEC.md:345-346`, `docs/specs/scenarios.md` (CHAT-046, WS-002 send-disabled),
    `docs/specs/scenario_coverage.md:261`. Note the product specs use the alternate wording
    *"Authenticate a provider"*; reconcile against the pi-auth copy on ship.
- **Copy constraint:** `docs/development/review/design.md:202` — empty/error states must say
  what happened and what to do next, in plain language.

## Open questions / to confirm in review

1. **Base-harness default destination:** `"DEPENDENCIES"` vs `"GENERAL"` for harnesses that
   declare nothing (terminal/hello never reach the composer send path, so this is a
   safety default).
2. **Mid-session live-disconnect:** confirm we accept the one behavior change — the switcher
   goes empty (login CTA) when the only provider is disconnected mid-session — rather than
   preserving "retain" only for that sub-case.
3. **Claude sign-in control:** file the follow-up to add an actionable "Sign in to Claude"
   under Dependencies so Claude's destination is as useful as pi's?
4. **Naming:** `configuration_settings_section` vs a shorter `settings_section` /
   `config_destination`.
