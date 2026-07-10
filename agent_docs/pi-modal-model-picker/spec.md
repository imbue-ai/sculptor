# Pre-workspace pi model picker — spec

Make pi model selection possible in the New Workspace modal, so a pi creation
carries a real, validated model and the initial prompt is valid by
construction.

## Problem

A pi agent created from the New Workspace modal with an initial prompt can
crash before the user can intervene: the prompt is queued at creation and
processed at startup, but pi's model is only selectable after the workspace
starts. For a user with no authenticated pi provider, the first turn runs
against a model that cannot run; the resulting auth failure (`PiCrashError`)
is uncaught on the prompt-turn path and tears the whole agent down.

The contract is dishonest in two places:

- The modal shows a hint ("Select your model after the workspace starts")
  instead of a model picker, so a pi creation cannot express a model
  selection.
- The backend rejects any prompt without a model, so the frontend sends a
  **placeholder Claude model** with pi prompts — a value pi discards. The
  queued message therefore looks valid while naming no usable model.

The in-workspace composer refuses to send when the catalog has no usable
model (`hasNoUsableModel`), but the modal path never passes through the
composer, so nothing validates a pi prompt before the agent processes it.

## Fact base

The design rests on facts the codebase already relies on elsewhere:

- **Catalog discovery is headless.** `PiAgent.fetch_available_models_probe`
  enumerates pi's catalog by running `pi --mode rpc --no-extensions` as a
  short-lived subprocess and issuing the `get_available_models` / `get_state`
  RPCs — no TTY, no agent session, no interaction. Only *authentication*
  (`/login`) is interactive.
- **The authenticated-provider set needs no pi at all.**
  `compute_authenticated_provider_ids()` is a read of pi's `auth.json` plus
  env-var detection.
- **Execution environments are local.** Agents run on the user's machine with
  the user's `$HOME`, so a host-side probe sees the same binary, `auth.json`,
  and ambient env an in-workspace probe sees. The Settings login flow already
  runs the pi binary host-side with no workspace.

Therefore pi's catalog is knowable before any workspace exists, and the modal
can offer the same picker the composer has.

## Design

### 1. Global catalog endpoint

`GET /api/v1/pi/models` — the host-side equivalent of the in-task probe.
(pi-named, matching the existing `pi/providers/*` and `pi/login` surfaces;
the modal is inherently harness-aware — it picks the agent type — unlike the
composer, which never branches on harness identity.) Extract the probe's
core (spawn `pi --mode rpc`, two RPCs, curate, authenticated-filter) into a
helper that does not require an `AgentExecutionEnvironment`:

- **binary**: resolved through the dependency-management service
  (managed-or-custom), exactly as the Settings login flow resolves it;
- **session dir**: a throwaway directory under Sculptor's own state dir;
- **env**: the backend process env + PATH plus the configured pi api-key env
  vars — the same inputs the in-task probe merges.

Response: `{ available_models: list[ModelOption], default_model: ModelOption
| None }`, where `default_model` is pi's own current model when usable.
Curation and the authenticated filter are shared code with the in-task probe
so the two surfaces cannot disagree. Best-effort like the in-task probe: any
failure yields an empty catalog, not an error.

**Freshness requirement:** the modal must reflect credential changes made
while it is open — a login round-trip through Settings is picked up on
return. On-demand client fetch with re-query (e.g. on focus) satisfies this;
there is no server-side cache to invalidate.

### 2. Modal: a real pi model picker

Replace the pi hint in the New Workspace form's agent-settings row with the
shared `ModelSelector` in backend-models mode, fed by the endpoint.

One rule governs submission — the composer's `hasNoUsableModel` predicate
applied one screen earlier, sharing its empty-state copy:

> **A pi prompt is submittable only against a resolved, non-empty catalog
> with a selection. A promptless create never waits on the catalog.**

Everything else derives from that rule and the observed catalog state: while
resolving, the picker is disabled and Create is blocked only if a prompt is
present; when populated, the picker preselects `default_model` and the
selection is a `ModelOption` identity `(provider, model_id)`; when empty, the
existing no-usable-model surface renders ("No models available" + the login
CTA routing to Settings → Pi) and a prompt cannot be submitted. Creating the
workspace without a prompt is always available — a promptless pi agent is
safe, and post-start selection still exists for it.

### 3. Honest create contract

`CreateAgentRequest` carries the model on the harness's own terms:

- Claude: `model: LLMModel` (unchanged).
- pi: a new optional `backend_model` carrying the chosen `ModelOption`
  (provider, model id, display name — so the seeded selection can render in
  the switcher before pi confirms it). The placeholder Claude `model` is no
  longer sent for pi, and `StartTaskRequest.model` becomes optional to match.

**Invariant:** `model` and `backend_model` are mutually exclusive — a create
names its model on exactly one harness's terms, or (promptless) not at all.

Validation when a pi create carries a prompt: `backend_model` is required,
and its `provider` must be in `compute_authenticated_provider_ids()` at
create time — an instant host-side check; otherwise 422 with an actionable
message. Full catalog-membership re-validation is deliberately skipped:
provider auth is the crash class, and the `model_id` came from the probe
moments earlier.

The create transaction persists the accepted selection as the task's
`current_model`. No set-model message is enqueued — there is no live agent
yet; the wrapper's start-time adoption consumes `current_model`.
(`ChatInputUserMessage.model_name` and `AgentTaskInputsV2.default_model` are
already nullable; pi creates leave them unset.)

### 4. Startup adoption

The pi wrapper already reconciles pi to task state: it is constructed with
`preselected_model = task_state.current_model` and issues pi's `set_model`
during start. With `current_model` seeded at create, the queued initial
prompt runs under the validated selection. The ordering the crash violated —
auth determined → catalog known → selection validated → prompt processed —
now holds by construction, because each step happens before the workspace is
created.

### 5. Defense in depth

Create-time validation is a point-in-time check; credentials can change
between create and start. Two backstops:

- The start-time reselect already drops or switches an unauthenticated
  selection when the wrapper fetches the catalog.
- `_run_prompt_turn` converts the turn pump's `PiCrashError` onto the
  contained `AgentClientError` rail (`PiTurnError`), so the existing per-turn
  error block (which carries the login CTA) is emitted instead of the
  exception killing the agent — the same containment `_run_wake_turn` already
  has. A doomed turn becomes a recoverable error in a live agent.

Each layer is the sole enforcer at its own trust boundary: the modal gate
(client), the create 422 (API, the sole server-side pre-persistence check),
the start-time reselect (agent boot), the composer guard (live session), and
containment (runtime backstop). The modal and composer share one predicate
and one empty-state copy so they cannot drift.

Turn admission stays simple: drive the turn, contain the failure. No
parking/holding of queued prompts.

## Deletions

- The modal hint ("Select your model after the workspace starts"), its
  `NEW_WORKSPACE_PI_SETTINGS_HINT` element id, and every test asserting it.
- The placeholder-Claude-model contract for pi prompts in
  `useCreateWorkspace` and the tests locking it in.
- The unconditional "Model is required when providing a prompt" 422 in
  `create_workspace_agent` (superseded by the per-harness requirement above).
- Documentation claims that pi's models are only knowable after the workspace
  starts.

## Non-goals

- Remote execution environments. The design leans on locality — the same
  assumption the login flow and `auth.json` sharing already lean on.
- Embedding the login terminal in the modal (the CTA routes to Settings).
- pi-core changes; the post-start composer, `set_model`, and
  credential-refresh flows are untouched.
- Unifying Claude and pi create-model representations under one
  `ModelOption`-shaped field (Claude's `model_id` is already the `LLMModel`
  value) — a real representation cleanup, but it touches the Claude create
  path this change otherwise leaves alone. Deferred; the exclusivity
  invariant carries the constraint.

## Testing

- **Endpoint**: catalog under fake `auth.json`/env permutations —
  authenticated, empty, probe failure → empty.
- **Modal**: the admission rule across catalog states — prompt submission
  blocked while resolving and when empty; populated → create request carries
  `(provider, model_id)` and no Claude placeholder; promptless create never
  blocked.
- **Create validation**: pi prompt without `backend_model` → 422;
  unauthenticated provider → 422; `current_model` seeded on accept; `model` +
  `backend_model` together rejected.
- **End-to-end**: unauthenticated pi + modal prompt → blocked in the modal,
  no crash; authenticated → prompt runs under the selected model
  (`set_model` observed at start).
- **Containment**: an auth-shaped failure on a prompt turn renders the error
  block and the agent stays alive.
