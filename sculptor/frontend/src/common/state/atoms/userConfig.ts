import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

import { isLlmModel } from "~/common/Guards.ts";
import { getTelemetryEnabled } from "~/common/Telemetry.ts";

import type { CiBabysitterConfig, CustomActionsConfig, UserConfig } from "../../../api";
import { LlmModel } from "../../../api";
import { themeBuilderSettingsAtom } from "./themeBuilder";

/**
 * PRIMARY ATOM: Global UserConfig State
 *
 * This atom serves as the single source of truth for all user configuration.
 * It mirrors the backend UserConfig model.
 *
 * Lifecycle:
 * 1. Initialized as null on app startup
 * 2. Populated during app initialization via GET /api/v1/config
 * 3. Updated whenever settings are changed via PUT /api/v1/config
 * 4. Eventually will be updated via WebSocket streams when we migrate to database storage
 */
export const userConfigAtom = atom<UserConfig | null>(null);

/**
 * DERIVED ATOMS: Semantic Setting Accessors
 *
 * These atoms provide clean, typed access to specific settings while automatically
 * reacting to changes in the primary userConfig atom. This pattern eliminates the
 * need for manual subscription management and ensures consistent behavior.
 */

// Theme setting — derives from the theme builder (localStorage) so that the
// Radix <Theme> appearance and all consumers (e.g. diff panel CodeMirror)
// stay in sync.  The server-side userConfig.appTheme field is no longer used.
export const appThemeAtom = atom<"light" | "dark" | "system">((get) => {
  return get(themeBuilderSettingsAtom).appearance;
});

// Experimental settings

export const isAlwaysInterruptAndSendAtom = atom<boolean>(
  (get) => get(userConfigAtom)?.isAlwaysInterruptAndSend ?? false,
);

// Model preferences

export const lastUsedModelAtom = atomWithStorage<string | null>("sculptor-last-used-model", null);

export const configuredDefaultModelAtom = atom<string | null>((get) => get(userConfigAtom)?.defaultLlm ?? null);

export const defaultModelAtom = atom<string>((get) => {
  const configuredDefaultModel = get(configuredDefaultModelAtom);
  if (configuredDefaultModel && isLlmModel(configuredDefaultModel)) {
    return configuredDefaultModel;
  }
  const lastUsedModel = get(lastUsedModelAtom);
  if (lastUsedModel && isLlmModel(lastUsedModel)) {
    return lastUsedModel;
  }
  return LlmModel.CLAUDE_FABLE_5;
});

// User identity settings
export const userEmailAtom = atom<string | undefined>((get) => get(userConfigAtom)?.userEmail);

export const userFullNameAtom = atom<string | undefined>((get) => get(userConfigAtom)?.userFullName ?? undefined);

export const isTelemetryEnabledAtom = atom<boolean>((get) => {
  const config = get(userConfigAtom);
  if (config == null) {
    // Pre-handshake, mirror Telemetry.ts's runtime gate — which already
    // honors the persisted opt-out from a previous session — so the UI never
    // disagrees with the actual SDK gating after a restart.
    return getTelemetryEnabled();
  }
  // Must match Telemetry.ts's computeIsTelemetryEnabled: the backend
  // normalizes mixed configs to all-off on load, and the AND keeps the same
  // conservative bias here.
  return (config.isErrorReportingEnabled ?? false) && (config.isProductAnalyticsEnabled ?? false);
});

// Custom actions
const EMPTY_CUSTOM_ACTIONS: CustomActionsConfig = { actions: [], groups: [] };

export const customActionsAtom = atom<CustomActionsConfig>((get) => {
  const config = get(userConfigAtom);
  const raw = config?.customActions as Record<string, unknown> | null | undefined;
  if (raw == null || typeof raw !== "object" || !Array.isArray(raw.actions) || !Array.isArray(raw.groups)) {
    return EMPTY_CUSTOM_ACTIONS;
  }
  return raw as CustomActionsConfig;
});

// PR creation settings
const DEFAULT_PR_CREATION_PROMPT =
  "Push my changes to origin and create a pull request. Check whether the repo uses GitHub (gh) or GitLab (glab) and use the appropriate tool. Write a clear description summarizing the changes.";

export const prCreationPromptAtom = atom<string>(
  (get) => get(userConfigAtom)?.prCreationPrompt ?? DEFAULT_PR_CREATION_PROMPT,
);

export const isPrPollingEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.prPollingEnabled ?? true);

export const prPollIntervalAtom = atom<number>((get) => get(userConfigAtom)?.prPollIntervalSeconds ?? 30);

export const prPollClosedMultiplierAtom = atom<number>((get) => get(userConfigAtom)?.prPollClosedMultiplier ?? 6);

export const prDefaultTargetBranchAtom = atom<string>(
  (get) => get(userConfigAtom)?.prDefaultTargetBranch ?? "origin/main",
);

// CI Babysitter settings (experimental). The full nested config lives under
// userConfig.ciBabysitter on the backend; individual atoms below derive from
// that object with sensible per-field defaults for when the config hasn't
// been loaded yet.
const DEFAULT_CI_BABYSITTER_PIPELINE_PROMPT =
  "Investigate the failing pipeline for this MR, identify the root cause, fix the code, commit, and push.";
const DEFAULT_CI_BABYSITTER_MERGE_CONFLICT_PROMPT =
  "This MR has a merge conflict with its base branch. Fetch the latest, then rebase against the base branch, resolve all conflicts, and force-push the result.";

export const ciBabysitterConfigAtom = atom<CiBabysitterConfig | null>(
  (get) => get(userConfigAtom)?.ciBabysitter ?? null,
);

export const isCiBabysitterEnabledAtom = atom<boolean>((get) => get(ciBabysitterConfigAtom)?.enabled ?? false);

export const ciBabysitterRetryCapAtom = atom<number>((get) => get(ciBabysitterConfigAtom)?.retryCap ?? 3);

export const ciBabysitterPipelineFailedPromptAtom = atom<string>(
  (get) => get(ciBabysitterConfigAtom)?.pipelineFailedPrompt ?? DEFAULT_CI_BABYSITTER_PIPELINE_PROMPT,
);

export const ciBabysitterMergeConflictPromptAtom = atom<string>(
  (get) => get(ciBabysitterConfigAtom)?.mergeConflictPrompt ?? DEFAULT_CI_BABYSITTER_MERGE_CONFLICT_PROMPT,
);

// File browser settings
export const fileBrowserSplitRatioAtom = atom<number>((get) => get(userConfigAtom)?.fileBrowserDefaultSplitRatio ?? 50);

export const fileBrowserTabCloseBehaviorAtom = atom<"mru" | "adjacent">(
  (get) => (get(userConfigAtom)?.fileBrowserTabCloseBehavior as "mru" | "adjacent") ?? "mru",
);

export const fileBrowserLineWrappingAtom = atom<"wrap" | "scroll">(
  (get) => (get(userConfigAtom)?.fileBrowserLineWrapping as "wrap" | "scroll") ?? "wrap",
);

export const fileBrowserDiffViewTypeAtom = atom<"unified" | "split">(
  (get) => (get(userConfigAtom)?.fileBrowserDiffViewType as "unified" | "split") ?? "unified",
);

// Commit button settings
export const DEFAULT_COMMIT_PROMPT =
  "Stage every changed and untracked file, then commit with a comprehensive commit message. Do not leave any files unstaged.";

export const commitPromptAtom = atom<string>((get) => get(userConfigAtom)?.commitPrompt ?? DEFAULT_COMMIT_PROMPT);

// Project environment variable settings
export const envVarOverrideEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.envVarOverrideEnabled ?? false);

// Smooth streaming preference
export const isSmoothStreamingUserPreferenceAtom = atom<boolean>(
  (get) => (get(userConfigAtom)?.isSmoothStreamingEnabled as boolean | undefined) ?? true,
);

// Per-workspace panel layout
export const isPanelLayoutPerWorkspaceAtom = atom<boolean>(
  (get) => get(userConfigAtom)?.isPanelLayoutPerWorkspace ?? false,
);

// In-place workspaces (opt-in — off by default)
export const isInPlaceWorkspacesEnabledAtom = atom<boolean>(
  (get) => get(userConfigAtom)?.enableInPlaceWorkspaces ?? false,
);

// Clone workspaces (opt-in — off by default; worktree is the default mode)
export const isCloneWorkspacesEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.enableCloneWorkspaces ?? false);

// Default branch-naming pattern (user-global default)
export const defaultWorkspaceBranchNamingPatternAtom = atom<string>(
  (get) => get(userConfigAtom)?.defaultWorkspaceBranchNamingPattern ?? "<user>/<slug>",
);

// Branch deletion policy (tri-state)
export const workspaceBranchDeletionPolicyAtom = atom<"never" | "delete_if_safe" | "always">(
  (get) =>
    (get(userConfigAtom)?.workspaceBranchDeletionPolicy as "never" | "delete_if_safe" | "always" | undefined) ??
    "delete_if_safe",
);

// Review All combined diff view (experimental — off by default)
export const isReviewAllEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.enableReviewAll ?? false);

// Entity mentions (experimental — off by default)
export const isEntityMentionsEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.enableEntityMentions ?? false);

// Rich markdown rendering (experimental — off by default)
export const isRichMarkdownRenderingEnabledAtom = atom<boolean>(
  (get) => get(userConfigAtom)?.enableRichMarkdownRendering ?? false,
);

// Multi-harness / pi (experimental — off by default). Gates only the
// new-workspace harness picker and the harness badge; the workspace.harness
// execution path is independent of this flag, so existing pi workspaces run pi
// regardless.
export const isMultiHarnessEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.enableMultiHarness ?? false);

// Frontend plugin system (experimental — off by default). Gates plugin
// loading at boot and the Plugins settings section. Plugins load once per
// page load, so toggling takes effect after an app reload.
export const isFrontendPluginsEnabledAtom = atom<boolean>((get) => get(userConfigAtom)?.enableFrontendPlugins ?? false);

// Agent defaults
export const isDefaultFastModeAtom = atom<boolean>((get) => get(userConfigAtom)?.defaultFastMode ?? false);

export const defaultEffortLevelAtom = atom<string>((get) => get(userConfigAtom)?.defaultEffortLevel ?? "xhigh");
