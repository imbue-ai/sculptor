import { existsSync, mkdirSync, readFileSync, renameSync, writeFileSync } from "node:fs";
import path from "node:path";

import { parse as parseToml, stringify as stringifyToml } from "smol-toml";
import { z } from "zod";

import { configPath } from "~/config/sculptor_folder";

// Zod schema for the backend's view of config.toml — the on-disk mirror of the
// user_settings row (REQ-DATA-002), written by the Python backend and NOT
// rewritten by the migration (Task 8.1). It mirrors UserConfig in
// sculptor/sculptor/config/user_config.py for the fields the backend reads, with
// defaults filling gaps, and .passthrough() so any legacy/unversioned field an
// older config carries loads without error and round-trips on save
// (REQ-DATA-022). Loosely-typed nested values (keybindings, panel_layout,
// custom_actions, ci_babysitter.agent) are kept permissive so a malformed
// legacy value never fails the whole load.

const DependencyPathsSchema = z
  .object({
    git: z.string().nullable().default(null),
    claude: z.string().default(() => process.env.SCULPTOR_CLAUDE_BINARY_DEFAULT_OVERRIDE ?? "MANAGED"),
    pi: z.string().default("MANAGED"),
  })
  .passthrough();

const PiConfigSchema = z
  .object({
    api_key_env_var_names: z.array(z.string()).default(["ANTHROPIC_API_KEY"]),
  })
  .passthrough();

const CIBabysitterConfigSchema = z
  .object({
    enabled: z.boolean().default(false),
    retry_cap: z.number().int().default(3),
    pipeline_failed_prompt: z.string().default(
      "Investigate the failing pipeline for this MR, identify the root cause, fix the code, commit, and push.",
    ),
    merge_conflict_prompt: z.string().default(
      "This MR has a merge conflict with its base branch. Fetch the latest, then rebase against the base branch, resolve all conflicts, and force-push the result.",
    ),
    agent: z.unknown().optional(),
  })
  .passthrough();

export const UserConfigSchema = z
  .object({
    user_email: z.string().default(""),
    user_full_name: z.string().nullable().default(null),
    user_id: z.string().default(""),
    organization_id: z.string().default(""),
    instance_id: z.string().default(""),
    is_error_reporting_enabled: z.boolean().default(false),
    is_product_analytics_enabled: z.boolean().default(false),
    is_session_recording_enabled: z.boolean().default(false),
    is_privacy_policy_consented: z.boolean().default(false),
    is_telemetry_level_set: z.boolean().default(false),
    keybindings: z.record(z.string(), z.string().nullable()).default({}),
    default_llm: z.string().nullable().default(null),
    update_channel: z.enum(["STABLE", "ALPHA"]).default("STABLE"),
    min_free_disk_gb: z.number().default(2.0),
    panel_layout: z.unknown().nullable().default(null),
    custom_actions: z.unknown().nullable().default(null),
    pr_creation_prompt: z.string().default(
      "Push my changes to origin and create a pull request. Check whether the repo uses GitHub (gh) or GitLab (glab) and use the appropriate tool. Write a clear description summarizing the changes.",
    ),
    pr_polling_enabled: z.boolean().default(true),
    pr_poll_interval_seconds: z.number().int().default(30),
    pr_poll_closed_multiplier: z.number().int().default(6),
    pr_default_target_branch: z.string().default("origin/main"),
    file_browser_default_split_ratio: z.number().int().default(50),
    file_browser_tab_close_behavior: z.string().default("mru"),
    file_browser_line_wrapping: z.string().default("wrap"),
    file_browser_diff_view_type: z.string().default("unified"),
    is_always_interrupt_and_send: z.boolean().default(false),
    commit_prompt: z.string().default(
      "Stage every changed and untracked file, then commit with a comprehensive commit message. Do not leave any files unstaged.",
    ),
    ci_babysitter: CIBabysitterConfigSchema.default({}),
    dependency_paths: DependencyPathsSchema.default({}),
    pi: PiConfigSchema.default({}),
    env_var_override_enabled: z.boolean().default(false),
    is_smooth_streaming_enabled: z.boolean().default(true),
    is_panel_layout_per_workspace: z.boolean().default(false),
    enable_in_place_workspaces: z.boolean().default(false),
    enable_clone_workspaces: z.boolean().default(false),
    default_workspace_branch_naming_pattern: z.string().default("<user>/<slug>"),
    workspace_branch_deletion_policy: z.enum(["never", "delete_if_safe", "always"]).default("delete_if_safe"),
    enable_review_all: z.boolean().default(false),
    enable_entity_mentions: z.boolean().default(false),
    enable_rich_markdown_rendering: z.boolean().default(false),
    enable_pi_agent: z.boolean().default(false),
    enable_frontend_plugins: z.boolean().default(false),
    default_fast_mode: z.boolean().default(false),
    default_effort_level: z.enum(["low", "medium", "high", "xhigh", "max"]).default("xhigh"),
  })
  .passthrough();

export type UserConfig = z.infer<typeof UserConfigSchema>;

export function defaultUserConfig(): UserConfig {
  return UserConfigSchema.parse({});
}

// Loads config.toml, tolerating a missing file (returns defaults), legacy/extra
// fields (preserved via passthrough), and gaps (filled by defaults).
export function loadSettings(file: string = configPath()): UserConfig {
  if (!existsSync(file)) {
    return defaultUserConfig();
  }
  const data = parseToml(readFileSync(file, "utf8"));
  return UserConfigSchema.parse(data);
}

// TOML cannot represent null/undefined; drop those keys recursively (mirrors the
// Python exclude_none behavior) before serializing.
function stripNullish(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.filter((item) => item !== null && item !== undefined).map(stripNullish);
  }
  if (value !== null && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, inner] of Object.entries(value)) {
      if (inner !== null && inner !== undefined) {
        result[key] = stripNullish(inner);
      }
    }
    return result;
  }
  return value;
}

// Writes config.toml atomically (tmp + rename), creating the parent dir.
export function saveSettings(config: UserConfig, file: string = configPath()): void {
  mkdirSync(path.dirname(file), { recursive: true });
  const tmp = `${file}.tmp`;
  writeFileSync(tmp, stringifyToml(stripNullish(config) as Record<string, unknown>));
  renameSync(tmp, file);
}

// The server-side SculptorSettings (config/settings.py) surfaced to the frontend
// on the stream's user_update.settings. The frontend reads TESTING.INTEGRATION_ENABLED
// to gate testing-only affordances (e.g. the Fake Claude model in the switcher);
// it is true exactly when the integration harness sets TESTING__INTEGRATION_ENABLED
// (server_utils.get_testing_environment), mirroring the Python settings env binding.
export function getServerSettings(): Record<string, unknown> {
  return {
    TESTING: {
      INTEGRATION_ENABLED: process.env.TESTING__INTEGRATION_ENABLED === "true",
    },
  };
}
