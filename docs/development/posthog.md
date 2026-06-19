# PostHog telemetry

This document describes how PostHog analytics work in Sculptor — what IDs we
use, how identity flows from anonymous to identified, and where to add new
events.

> **Phase 1 (current):** PostHog is wired up on the frontend only. Backend
> telemetry is dormant. The mailing-list signup event
> (`onboarding.email_confirmation`) fires from the frontend so downstream
> consumers of that event keep working without backend telemetry.
>
> **Phase 2 (planned, [SCU-764]):** Backend re-enable with synced identity,
> alias call for pre-email backend events, and full lifecycle documentation.

## IDs

| ID | Generated where | Persisted | Stable across | Used as |
|---|---|---|---|---|
| `posthog_anonymous_id` | posthog-js, automatically on init | browser localStorage | page reloads in *this* browser | distinct_id pre-identification on FE |
| `analytics_user_id` | FE, deterministically as `uuid5(SCULPTOR_ANALYTICS_NAMESPACE, email)` | not persisted (pure function of email) | any install, any browser, same email | distinct_id post-identification on FE |
| `instance_id` | BE, at first config creation | `~/.sculptor/config.toml` | restarts of *this* install | event property; will become BE distinct_id in Phase 2 |

PostHog's own concept of `distinct_id` is whatever string we pass to
`posthog.identify()` (or whatever posthog-js auto-generates if we don't call
identify). We don't generate `distinct_id` directly — we choose which of the
IDs above to identify with, and *when*.

## Cross-install user unification

The unification mechanism is **deterministic derivation**, not server-side
merging:

```ts
analytics_user_id = uuid5(SCULPTOR_ANALYTICS_NAMESPACE, email)
```

Two installs of Sculptor with the same email independently compute the same
UUID. PostHog sees identical distinct_ids and treats them as one person —
without ever knowing the events came from different machines.

**`SCULPTOR_ANALYTICS_NAMESPACE` must never change.** Changing it would map
every existing user to a new analytics_user_id, splitting their event history
permanently. The namespace constant lives in
[`sculptor/frontend/src/common/Analytics.ts`](../../sculptor/frontend/src/common/Analytics.ts).

## Lifecycle

### Cold first launch (no email submitted yet)

1. **Main.tsx** runs `initializeTelemetry()` before React mounts. posthog-js
   initializes from the Vite-baked `FRONTEND_POSTHOG_TOKEN` constant and
   generates an anonymous distinct_id, persisting it in localStorage.
2. Pre-handshake events (loading screen, pageload) fire under that anonymous
   distinct_id. Only the `source: sculptor_frontend` super property is
   registered at this point.

   DOM autocapture is **structure-only**: `mask_all_text` strips element text
   (file names, branch names, prompts — private customer data) and an
   attribute ignore-list drops `title`/`aria-label`/`alt`/`placeholder`/
   `href`/`src`, which can embed user content. What's captured per click is
   the element chain — tags, classes, element ids, data-testids, DOM
   position. Pageviews use `capture_pageview: "history_change"`, so SPA route
   changes (hash-router navigations go through the history API) emit
   `$pageview` too.
3. **App.tsx** awaits backend readiness, then calls
   `applyTelemetryInfo(telemetryInfo)`. This registers the `sculptor_version`
   super property (with `instance_id` and `execution_instance_id` nested under
   a `session` super property) and updates the PostHog config from user consent
   flags. Sentry user context is set.
4. The user remains anonymous in PostHog until they submit their email.

### Email submission

1. **OnboardingWizard.tsx** posts to `/api/v1/config/email` (including the
   welcome-step telemetry checkbox as `isTelemetryEnabled`). On success:
2. `updateTelemetryConfig(updatedTelemetryInfo)` reconciles the SDKs with the
   chosen consent and updates consent-driven config and the Sentry user.
3. `identifyAnalyticsUser(email)` computes the analytics_user_id and calls
   `posthog.identify(analytics_user_id, {email})`. posthog-js's implicit
   alias-on-identify merges the previously-anonymous events into the new
   identified person.
4. `posthog.capture('onboarding.email_confirmation', {did_opt_in_to_marketing})`
   fires the mailing-list signup event under the identified user.

Steps 3–4 are skipped when the user unchecked the telemetry checkbox.

### Skipping account setup

The welcome step's "Continue without an account" link posts to
`/api/v1/config/skip_account` instead. No email is stored, so no identify
ever happens — events (if telemetry is on) stay under the anonymous
distinct_id, tied only to the random `instance_id`. This is the *anonymous
telemetry* mode.

### Telemetry opt-out

Telemetry consent is binary (`is_error_reporting_enabled` +
`is_product_analytics_enabled` flipped together; session recording stays
off). It can be changed on the onboarding welcome step (checkbox) and in
Settings → Privacy (switch). `POST /api/v1/config/telemetry` is the only
endpoint allowed to change the flags; `PUT /api/v1/config` rejects attempts.
A mixed config (legacy or hand-edited) is normalized to all-off when the
backend loads it, and the frontend reads the pair with AND — the same
conservative bias — as defense-in-depth.

Enforcement lives in the frontend (the backend doesn't report anything):

- **PostHog**: `posthog.opt_out_capturing()` — persisted by posthog-js in
  localStorage, so restarts respect it before the handshake.
- **Sentry events**: `beforeSend` (`instrument.ts`) drops everything except
  `feedback` events, so the Report a Problem flow keeps working while opted
  out.
- **Sentry Session Replay**: replays never stream continuously. The recorder
  runs in buffer mode (both `replaysSessionSampleRate` and
  `replaysOnErrorSampleRate` are 0; `startBuffering()` keeps the last ~60s in
  memory) and uploads only when the user submits a bug report — the replay
  integration flushes the buffer when a feedback event passes through and
  links it via `contexts.feedback.replay_id`; `submitReportAtom` then stops
  the recorder and re-arms buffering. Replay uploads bypass `beforeSend`, so
  on opt-out the recorder is stopped entirely; the opt-out is also mirrored
  to localStorage (`sculptor.telemetryOptedOut`) so the recorder is never
  armed on later launches.

### Warm restart (email already in config)

1. Main.tsx initializes posthog-js. localStorage already holds the
   `analytics_user_id` from the previous session — posthog-js restores it
   automatically.
2. App.tsx fetches `telemetryInfo`, calls `applyTelemetryInfo`. Since
   `userEmail` is set, `identifyAnalyticsUser` is called. posthog-js's
   compare-before-identify path makes this a no-op refresh of person
   properties (no merge event, since the distinct_id is unchanged).

### Second machine, same user

New `instance_id` (different from machine 1), new `posthog_anonymous_id`. On
email submit, the same email produces the same `analytics_user_id` →
events from both machines land on the same PostHog person. The `instance_id`
super property distinguishes them at the event level.

### Wipe and reinstall

New `instance_id`, new `posthog_anonymous_id` in the fresh browser
localStorage. On email submit, the canonical `analytics_user_id` is the same
as before → no identity loss.

## Reliability gaps (Phase 1)

posthog-js's implicit alias-on-identify has a known silent-failure mode: if
the merge event fails to deliver (sendBeacon dropped on tab close, ad-blocker,
network exhaust), the merge never happens server-side and posthog-js will not
retry on the next page load — pre-identify events orphan. There's no
client-side way to verify the merge succeeded.

For the mailing-list signup event specifically, this isn't load-bearing: the
`onboarding.email_confirmation` event is captured *after* identify, so it
always fires under the canonical user. The orphaning only affects the
loading-screen and pageload events emitted before identify.

Phase 2 (SCU-764) closes this gap by having the backend issue a server-side
alias call from the email-submit endpoint, with retry-until-confirmed
persistence — so even if posthog-js's merge drops, the backend's alias
recovers the link.

## Adding a new FE event

In any FE module:

```ts
import { posthog } from "posthog-js";

posthog.capture("category.action", { key: "value" });
```

Naming convention: `category.action` snake_case (e.g.
`workspace.created`, `agent.message_sent`). Use the existing events as a
guide for property shapes.

## Build configuration

| Variable | Set in | Used by |
|---|---|---|
| `SCULPTOR_FRONTEND_POSTHOG_TOKEN` | `sculptor/builder/cli.py::setup_build_vars` | `vite.electron.config.ts` `define` block |
| `SCULPTOR_FRONTEND_POSTHOG_HOST` | `sculptor/builder/cli.py::setup_build_vars` | `vite.electron.config.ts` `define` block |

Token values are sourced from `sculptor/sculptor/posthog_settings.py`. The
production value is shipped in built distributions; dev and testing values
are used when running from source and in CI respectively. PostHog project
keys are public (PostHog requires them in client code) and append-only.

[SCU-764]: # "Internal ticket SCU-764: PostHog phase 2 — backend re-enable with synced identity"
