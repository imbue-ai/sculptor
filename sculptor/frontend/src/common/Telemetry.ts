/** Telemetry initialization and identity management for PostHog + Sentry.
 *
 * Lifecycle (see `docs/development/posthog.md` for the full picture):
 *
 * 1. `initializeTelemetry()` runs at app mount, before BE is up. Reads the
 *    PostHog token from the Vite-baked `FRONTEND_POSTHOG_TOKEN` constant.
 *    posthog-js generates an anonymous distinct_id and persists it in
 *    localStorage. Pre-BE events (loading screen, pageload) fire under that ID.
 *
 * 2. `applyTelemetryInfo(telemetryInfo)` runs once `/api/v1/telemetry_info`
 *    resolves. Reconciles telemetry consent with the SDKs, registers super
 *    properties (sculptor_version, instance_id), updates Sentry user context,
 *    and — if the user has already submitted their email — calls
 *    `identifyAnalyticsUser` to identify them in PostHog.
 *
 * 3. `identifyAnalyticsUser(email)` is called on email submit (from the
 *    OnboardingWizard). It computes the canonical analytics_user_id from the
 *    email and identifies the user. posthog-js's implicit alias-on-identify
 *    handles merging the pre-email anonymous events into the canonical person.
 *
 * Consent: telemetry is binary — either both SDKs report, or neither does.
 * Users without an email (skipped account setup) stay anonymous: events ride
 * the random distinct_id and no identity is ever attached.
 */

import * as Sentry from "@sentry/react";
import type { AutocaptureConfig, PostHog, PostHogConfig } from "posthog-js";
import { posthog } from "posthog-js";

import { type TelemetryInfo, type UserConfig } from "~/api";

import { computeAnalyticsUserId } from "./Analytics.ts";

// Vite-baked constants (see `vite.electron.config.ts:define` and
// `builder/cli.py::setup_build_vars`).
declare const FRONTEND_POSTHOG_TOKEN: string;
declare const FRONTEND_POSTHOG_HOST: string;

let isInitialized = false;
let hasLoggedImbueDebug = false;

// Mirrors the user's opt-out across restarts so the pre-handshake window
// (Sentry init → /api/v1/telemetry_info resolving) already respects it.
// posthog-js persists its own opt-out state, but Sentry has no equivalent.
const TELEMETRY_OPT_OUT_STORAGE_KEY = "sculptor.telemetryOptedOut";

const readPersistedOptOut = (): boolean => {
  try {
    return window.localStorage.getItem(TELEMETRY_OPT_OUT_STORAGE_KEY) === "true";
  } catch {
    return false;
  }
};

// The frontend Sentry beforeSend (instrument.ts) reads this on every event.
// Defaults to `true` on fresh installs so bootstrap crashes still reach
// Sentry — applyTelemetryInfo overrides it once the BE handshake resolves
// (typically <3s). The config file on the backend stays the source of truth;
// the localStorage mirror only covers the pre-handshake window.
let isTelemetryEnabled: boolean = !readPersistedOptOut();

export const setTelemetryEnabled = (enabled: boolean): void => {
  isTelemetryEnabled = enabled;
  try {
    if (enabled) {
      window.localStorage.removeItem(TELEMETRY_OPT_OUT_STORAGE_KEY);
    } else {
      window.localStorage.setItem(TELEMETRY_OPT_OUT_STORAGE_KEY, "true");
    }
  } catch {
    // localStorage unavailable (e.g. some test environments) — the in-memory
    // flag still gates this session.
  }
};
export const getTelemetryEnabled = (): boolean => isTelemetryEnabled;

/**
 * Telemetry consent is binary: the consent endpoints always write the error
 * reporting and product analytics flags together, and the backend normalizes
 * mixed (legacy / hand-edited) configs to all-off on load. The AND here is
 * defense-in-depth with the same conservative bias. Session recording is
 * excluded — it is always written as off and is not part of the consent.
 */
export const computeIsTelemetryEnabled = (userConfig: UserConfig): boolean => {
  return (userConfig.isErrorReportingEnabled ?? false) && (userConfig.isProductAnalyticsEnabled ?? false);
};

/**
 * For @imbue.com users only: expose `posthog` on `window` for console
 * debugging and log that PostHog debug mode is on.
 *
 * posthog-js's npm import is module-scoped — it does NOT auto-attach to
 * `window` (only the script-tag snippet does that). So without this, you
 * can't inspect or call `posthog` from DevTools.
 */
const maybeEnableImbueDebug = (email: string | undefined): void => {
  const isImbue = email?.toLocaleLowerCase().endsWith("@imbue.com") ?? false;
  if (!isImbue || hasLoggedImbueDebug) return;

  (window as unknown as { posthog: PostHog }).posthog = posthog;
  console.log(`Email ${email} is @imbue.com — enabling PostHog debug mode and exposing window.posthog`);
  hasLoggedImbueDebug = true;
};

// Autocapture is structure-only. Combined with `mask_all_text` (which strips
// element text from the events), this ignore-list drops the attributes that
// can embed user content — tooltips, labels, link targets. What remains per
// click is the element chain: tag names, classes, element ids, data-testids,
// and DOM position — enough to identify the UI element without its content.
const STRUCTURE_ONLY_AUTOCAPTURE: AutocaptureConfig = {
  element_attribute_ignorelist: ["title", "aria-label", "alt", "placeholder", "href", "src"],
};

const buildPostHogConfig = (telemetryInfo: TelemetryInfo | null): Partial<PostHogConfig> => {
  const userConfig = telemetryInfo?.userConfig;
  const isProductAnalyticsEnabled = userConfig?.isProductAnalyticsEnabled ?? true;
  const isSessionRecordingEnabled = userConfig?.isSessionRecordingEnabled ?? false;
  const userEmail = userConfig?.userEmail ?? "";

  return {
    api_host: FRONTEND_POSTHOG_HOST,
    // "history_change" captures the initial pageview plus a $pageview on
    // every history-API navigation — createHashRouter drives navigation
    // through pushState/replaceState, so SPA route changes are covered.
    capture_pageview: isProductAnalyticsEnabled ? "history_change" : false,
    capture_pageleave: isProductAnalyticsEnabled,
    autocapture: isProductAnalyticsEnabled ? STRUCTURE_ONLY_AUTOCAPTURE : false,
    // Never capture element text: file names, branch names, repo/agent names,
    // and prompt fragments are private customer data.
    mask_all_text: true,
    disable_session_recording: !isSessionRecordingEnabled,
    capture_exceptions: false, // Needed for compatibility with Sentry integration
    debug: userEmail.toLocaleLowerCase().endsWith("@imbue.com"),
  };
};

/**
 * Bare-bones PostHog init. Runs at app mount, before any BE call.
 *
 * Reads the token from the Vite-baked constant. If the token is empty (which
 * happens in tests and in builds where SCULPTOR_FRONTEND_POSTHOG_TOKEN wasn't
 * set), this is a no-op and posthog-js stays uninitialized.
 *
 * Does NOT call `posthog.identify` — posthog-js auto-generates an anonymous
 * distinct_id stored in localStorage. We identify later, once we know who the
 * user is (post-email-submit).
 */
export const initializeTelemetry = (): void => {
  if (isInitialized) return;
  if (!FRONTEND_POSTHOG_TOKEN || FRONTEND_POSTHOG_TOKEN === "") {
    console.log("PostHog token not configured, skipping telemetry initialization");
    return;
  }

  posthog.init(FRONTEND_POSTHOG_TOKEN, {
    ...buildPostHogConfig(null),
    loaded: (loadedPosthog) => {
      // Source is the only super property we know pre-handshake. Other
      // session properties get registered when telemetry_info arrives.
      loadedPosthog.register({ source: "sculptor_frontend" });
      // posthog-js sets `$user_state` in persistence to "identified" after
      // any successful identify() call. On warm restart, that value is
      // restored from localStorage along with the canonical distinct_id, so
      // we can tell the difference between a fresh anonymous session and a
      // resumed identified one. Falls back to "anonymous" when the property
      // isn't set (first launch).
      const userState = loadedPosthog.get_property("$user_state") === "identified" ? "identified" : "anonymous";
      console.log(`PostHog telemetry SDK initialized (${userState}).`);
    },
  });

  isInitialized = true;
};

/**
 * Reconcile both SDKs with the user's telemetry consent so flips take effect
 * without a restart. Called from `applyTelemetryInfo` / `updateTelemetryConfig`
 * on every handshake and config change, and from the Settings telemetry switch
 * for its optimistic flip.
 */
export const applyTelemetryConsent = (isEnabled: boolean, userEmail?: string | null): void => {
  setTelemetryEnabled(isEnabled);

  if (isInitialized) {
    // opt_in/opt_out persist in localStorage, overriding any stale state from
    // a previous session. The opt-in is silent — re-running it on every
    // handshake must not fire a meta event.
    if (isEnabled) {
      posthog.opt_in_capturing({ captureEventName: null });
    } else {
      posthog.opt_out_capturing();
    }
  }

  // Session Replay runs in buffer mode: it records the last ~60s into memory
  // and uploads ONLY when the user submits a bug report (the replay
  // integration flushes the buffer when a feedback event passes through).
  // Replay uploads bypass Sentry's beforeSend, so the recorder itself is
  // stopped on opt-out. Both calls are no-ops when the recorder is already in
  // the requested state.
  const replay = Sentry.getReplay();
  if (replay) {
    if (isEnabled) {
      replay.startBuffering();
    } else {
      void replay.stop();
    }
  }

  // Pre-email events stay anonymous in Sentry. Once email is set, we tag
  // events with the canonical analytics_user_id so Sentry and PostHog group
  // them under the same person. When telemetry is off, clear the scope so
  // any in-flight bootstrap event no longer carries the identifying tag.
  if (isEnabled && userEmail) {
    Sentry.setUser({
      id: computeAnalyticsUserId(userEmail),
      email: userEmail,
    });
  } else {
    Sentry.setUser(null);
  }
};

const reconcileTelemetryConsent = (userConfig: UserConfig): boolean => {
  const isEnabled = computeIsTelemetryEnabled(userConfig);
  applyTelemetryConsent(isEnabled, userConfig.userEmail);
  return isEnabled;
};

/**
 * Called when `/api/v1/telemetry_info` resolves. Wires up the rest of the
 * telemetry surface — version/install super properties, consent-driven config,
 * Sentry user context, and the PostHog↔Sentry error-reporting integration.
 *
 * If the user has already submitted their email (warm restart), this also
 * triggers identify. On a cold first launch, the email isn't set yet and the
 * user stays anonymous until the OnboardingWizard calls `identifyAnalyticsUser`
 * directly.
 */
export const applyTelemetryInfo = (telemetryInfo: TelemetryInfo): void => {
  const { userConfig, sculptorVersion, sculptorExecutionInstanceId } = telemetryInfo;

  const isEnabled = reconcileTelemetryConsent(userConfig);

  // Identify FIRST. Everything below is best-effort enrichment (super
  // properties, Sentry integration, consent-driven config) and we don't want
  // a failure in any of those paths to prevent the user from being recognized
  // in PostHog. The identify call itself is small and well-tested.
  if (isEnabled && userConfig.userEmail && isInitialized) {
    identifyAnalyticsUser(userConfig.userEmail);
  }

  if (isInitialized) {
    posthog.set_config(buildPostHogConfig(telemetryInfo));
    maybeEnableImbueDebug(userConfig.userEmail);
    posthog.register({
      sculptor_version: sculptorVersion,
      session: {
        instance_id: userConfig.instanceId,
        execution_instance_id: sculptorExecutionInstanceId,
      },
    });

    if (userConfig.isErrorReportingEnabled) {
      // PostHog→Sentry integration: mirrors PostHog session metadata into
      // Sentry events. Safe to add multiple times — addIntegration de-dupes.
      Sentry.addIntegration(
        posthog.sentryIntegration({
          organization: "Imbue",
          projectId: 136453,
        }),
      );
    }
  }
};

/**
 * Identify the current user in PostHog.
 *
 * Computes `uuid5(SCULPTOR_ANALYTICS_NAMESPACE, email)` as the canonical
 * analytics_user_id and identifies with it. posthog-js's implicit
 * alias-on-identify handles merging pre-identify anonymous events into the
 * canonical person.
 *
 * Idempotent: if posthog-js's current distinct_id already matches, this just
 * refreshes person properties without firing an `$identify` merge event.
 */
export const identifyAnalyticsUser = (email: string, extraProperties: Record<string, unknown> = {}): void => {
  if (!isInitialized) return;

  const analyticsUserId = computeAnalyticsUserId(email);
  const properties = { email, ...extraProperties };

  if (posthog.get_distinct_id() === analyticsUserId) {
    posthog.setPersonProperties(properties);
    return;
  }

  posthog.identify(analyticsUserId, properties);
};

/**
 * Called when telemetry config changes after the initial handshake — e.g. the
 * user toggles a consent setting, or the email is submitted via the
 * OnboardingWizard.
 *
 * Use `applyTelemetryInfo` for the first-time wire-up and this for updates;
 * the difference is that `applyTelemetryInfo` also registers super properties,
 * which only need to happen once.
 */
export const updateTelemetryConfig = (telemetryInfo: TelemetryInfo): void => {
  const { userConfig } = telemetryInfo;

  const isEnabled = reconcileTelemetryConsent(userConfig);

  // Identify FIRST (see rationale in `applyTelemetryInfo`).
  if (isEnabled && userConfig.userEmail && isInitialized) {
    identifyAnalyticsUser(userConfig.userEmail);
  }

  if (isInitialized) {
    posthog.set_config(buildPostHogConfig(telemetryInfo));
    maybeEnableImbueDebug(userConfig.userEmail);
  }
};
