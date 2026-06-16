import os
from enum import StrEnum
from typing import Any
from typing import Literal

from loguru import logger
from pydantic import Field
from pydantic import model_validator
from pydantic.alias_generators import to_camel

from sculptor.config.custom_actions import CustomActionsConfig
from sculptor.foundation.pydantic_serialization import SerializableModel

# The free-disk warning threshold is this multiple of the hard minimum, so warnings
# fire before tasks are blocked outright.
_FREE_DISK_GB_WARN_LIMIT_MULTIPLIER: float = 3.0


class UpdateChannel(StrEnum):
    """Update channel for receiving Sculptor updates."""

    STABLE = "STABLE"
    ALPHA = "ALPHA"


class PrivacySettings(SerializableModel):
    """This model contains a subset of the privacy fields that we support."""

    is_error_reporting_enabled: bool = Field(False, description="Whether to enable error reporting, i.e. Sentry")
    is_product_analytics_enabled: bool = Field(
        False, description="Whether to enable product analytics, e.g. through PostHog"
    )
    is_session_recording_enabled: bool = Field(False, description="Whether to enable session recording")


class DependencyPaths(SerializableModel):
    """Configuration for dependency binary resolution.

    The ``claude`` field is a unified mode + path value:
      - ``"MANAGED"`` (default): Sculptor manages the Claude CLI binary.
      - An absolute path (e.g. ``"/usr/local/bin/claude"``): used directly.
      - A bare command name (e.g. ``"claude"``): resolved via the system PATH.

    The default for ``claude`` can be overridden via the
    ``SCULPTOR_CLAUDE_BINARY_DEFAULT_OVERRIDE`` environment variable.  When the
    user explicitly configures a value in Settings, it is persisted to the config
    file and takes precedence over the environment variable.

    The ``git`` field is an optional override path; when ``None``, git is
    resolved from the system PATH.

    The ``pi`` field is a unified mode + path value mirroring ``claude``:
      - ``"MANAGED"`` (default): Sculptor downloads and version-pins the pi CLI.
      - ``"CUSTOM"``, an absolute path, or a bare command name: a user-provided
        binary, resolved via the system PATH.

    There is no migration validator for ``pi``: a previously persisted bare
    ``"pi"`` (the old default) is preserved and resolves via PATH (i.e. treated
    as CUSTOM), so existing setups keep working after the default flips to
    ``"MANAGED"``.
    """

    git: str | None = None
    claude: str = Field(default_factory=lambda: os.environ.get("SCULPTOR_CLAUDE_BINARY_DEFAULT_OVERRIDE", "MANAGED"))
    pi: str = "MANAGED"


class PiConfig(SerializableModel):
    """Configuration for the pi agent harness.

    Pi reads its API key from the user's process environment at launch.
    ``api_key_env_var_names`` lists the environment variable names whose
    values are injected into the pi subprocess via the existing ``Secret``
    machinery — the values themselves are never persisted in config.
    """

    api_key_env_var_names: tuple[str, ...] = ("ANTHROPIC_API_KEY",)


class PanelLayoutConfig(SerializableModel):
    """Panel layout preferences for the workspace page."""

    zone_assignments: dict[str, str] = Field(default_factory=dict)
    active_panel_per_zone: dict[str, str] = Field(default_factory=dict)
    zone_visibility: dict[str, bool] = Field(default_factory=dict)
    zone_sizes: dict[str, float] = Field(default_factory=dict)
    zone_order: dict[str, list[str]] = Field(default_factory=dict)


class CIBabysitterConfig(SerializableModel):
    """Settings for the CI Babysitter — Sculptor watches open MRs and prompts an
    agent to fix pipeline failures and merge conflicts. Experimental; off by default.
    """

    enabled: bool = Field(
        default=False,
        description="Whether the CI Babysitter watches MRs and prompts an agent to fix pipeline failures and merge conflicts. Experimental; off by default.",
    )
    retry_cap: int = Field(
        default=3,
        description="After this many babysitter prompts for an MR without a passing pipeline, no further prompts are sent until the pipeline next passes.",
    )
    pipeline_failed_prompt: str = Field(
        default="Investigate the failing pipeline for this MR, identify the root cause, fix the code, commit, and push.",
        description="Prompt sent to the CI Babysitter agent when an MR's pipeline transitions to failed.",
    )
    merge_conflict_prompt: str = Field(
        default="This MR has a merge conflict with its base branch. Fetch the latest, then rebase against the base branch, resolve all conflicts, and force-push the result.",
        description="Prompt sent to the CI Babysitter agent when an MR develops a merge conflict with its base branch.",
    )


class UserConfig(SerializableModel):
    """Most configuration for user and for Sculptor app behavior should go here.

    All required fields must be provided or validation will fail.

    When you add a new field, you should add it as a field with a default value so that it is backwards compatible.
    """

    user_email: str = Field(default=..., description="User email address")
    user_full_name: str | None = Field(default=None, description="Full name of the user")
    user_id: str = Field(default=..., description="User ID")
    organization_id: str = Field(default=..., description="Organization ID")
    instance_id: str = Field(default=..., description="Instance ID")
    is_error_reporting_enabled: bool = Field(default=False, description="Whether to enable error reporting")
    is_product_analytics_enabled: bool = Field(default=False, description="Whether to enable product analytics")
    is_session_recording_enabled: bool = Field(default=False, description="Whether to enable session recording")
    is_privacy_policy_consented: bool = Field(
        default=False, description="Whether the user consented to our privacy policy"
    )
    is_telemetry_level_set: bool = Field(
        default=False, description="Whether the user consented to our telemetry level"
    )
    # App configuration:
    keybindings: dict[str, str | None] = Field(
        default_factory=dict, description="User-customized keybinding overrides"
    )
    default_llm: str | None = Field(
        default=None,
        description="Default LLM model for new agents. If None, then most recently used LLM will be used.",
    )
    # NOTE: The electron frontend might read this value directly in configFallback.ts. Please remember to keep them in sync.
    update_channel: UpdateChannel = Field(
        default=UpdateChannel.STABLE,
        description="Update channel for receiving Sculptor updates (stable or alpha)",
    )
    min_free_disk_gb: float = Field(
        default=2.0,
        description="The minimum free disk space before Sculptor will stop allowing new tasks and messages",
    )
    panel_layout: PanelLayoutConfig | None = Field(
        default=None,
        description="Panel layout preferences for the workspace page",
    )
    custom_actions: CustomActionsConfig | None = Field(
        default=None,
        description="Custom action buttons configuration",
    )
    pr_creation_prompt: str = Field(
        default="Push my changes to origin and create a pull request. Check whether the repo uses GitHub (gh) or GitLab (glab) and use the appropriate tool. Write a clear description summarizing the changes.",
        description="Default prompt sent to the agent when Create PR is clicked",
    )
    pr_polling_enabled: bool = Field(
        default=True,
        description="Whether to poll for PR/MR status at all. When disabled, the workspace banner shows the last cached status and stops issuing gh/glab calls.",
    )
    pr_poll_interval_seconds: int = Field(
        default=30,
        description="How often (in seconds) to poll for PR status on open workspaces",
    )
    pr_poll_closed_multiplier: int = Field(
        default=6,
        description="Closed workspaces poll every pr_poll_interval_seconds * pr_poll_closed_multiplier seconds. Crank this up to poll closed workspaces much less often.",
    )
    pr_default_target_branch: str = Field(
        default="origin/main",
        description="Default target branch for new workspaces",
    )
    file_browser_default_split_ratio: int = Field(
        default=50,
        description="Default split ratio (percentage for diff panel) when the diff panel opens",
    )
    file_browser_tab_close_behavior: str = Field(
        default="mru",
        description="Which tab becomes active after closing: 'mru' (most recently used) or 'adjacent'",
    )
    file_browser_line_wrapping: str = Field(
        default="wrap",
        description="Diff line wrapping: 'wrap' (soft wrap) or 'scroll' (horizontal scrollbar)",
    )
    file_browser_diff_view_type: str = Field(
        default="unified",
        description="Default diff view: 'unified' or 'split'",
    )
    is_always_interrupt_and_send: bool = Field(
        default=False,
        description="When enabled, sending a message while the agent is busy immediately interrupts and sends instead of queuing",
    )
    commit_prompt: str = Field(
        default="Stage every changed and untracked file, then commit with a comprehensive commit message. Do not leave any files unstaged.",
        description="Default prompt sent to the agent when Commit Changes is clicked",
    )
    ci_babysitter: CIBabysitterConfig = Field(
        default_factory=CIBabysitterConfig,
        description="Configuration for the CI Babysitter — watches MRs and prompts an agent to fix pipeline failures and merge conflicts.",
    )
    dependency_paths: DependencyPaths = Field(
        default_factory=DependencyPaths,
        description="Configuration for dependency binary resolution",
    )
    pi: PiConfig = Field(
        default_factory=PiConfig,
        description="Configuration for the pi agent harness",
    )
    env_var_override_enabled: bool = Field(
        default=False,
        description="When True, .sculptor/.env values override pre-existing environment variables",
    )
    is_smooth_streaming_enabled: bool = Field(
        default=True,
        description="Whether to enable smooth text streaming animation in the chat",
    )
    is_panel_layout_per_workspace: bool = Field(
        default=False,
        description="When enabled, panel visibility and sizes are local to each workspace instead of shared",
    )
    enable_in_place_workspaces: bool = Field(
        default=False,
        description="When enabled, the in-place workspace mode is available during workspace creation",
    )
    enable_clone_workspaces: bool = Field(
        default=False,
        description="When enabled, the legacy clone workspace mode is available during workspace creation. Worktree mode is now the default; this re-exposes clone mode for users who still want it.",
    )
    default_workspace_branch_naming_pattern: str = Field(
        default="<user>/<slug>",
        description="User-global default pattern for auto-generated workspace branch names. Supports <user> and <slug> placeholders. Overridden per-project by Project.naming_pattern.",
    )
    workspace_branch_deletion_policy: Literal["never", "delete_if_safe", "always"] = Field(
        default="delete_if_safe",
        description="What to do with a worktree workspace's auto-generated branch when the workspace is deleted: never (preserve), delete_if_safe (refuses to delete unmerged), always (force-delete).",
    )
    enable_review_all: bool = Field(
        default=False,
        description="When enabled, the Review All combined diff view is available in the File Browser",
    )
    enable_entity_mentions: bool = Field(
        default=False,
        description="When enabled, typing % in the chat input opens entity mention completions for repositories, workspaces, and agents",
    )
    enable_rich_markdown_rendering: bool = Field(
        default=False,
        description="When enabled, .md and .markdown files in the read-only file preview can be shown as rendered markdown via the eye toggle. Off by default while we iterate on the renderer.",
    )
    enable_pi_agent: bool = Field(
        default=False,
        description="When enabled, the agent-type menus offer the experimental pi agent. Off by default. Gates only the creation entry point — an existing pi agent keeps running regardless.",
    )
    default_fast_mode: bool = Field(
        default=False,
        description="When enabled, new agents default to fast mode",
    )
    # pyrefly: ignore [bad-assignment]
    default_effort_level: Literal["low", "medium", "high", "xhigh", "max"] = Field(
        default="xhigh",
        description="Default thinking effort level for new agents (low, medium, high, xhigh, max)",
    )

    @model_validator(mode="before")
    @classmethod
    def _migrate_claude_binary_mode(cls, data: Any) -> Any:
        """Migrate old claude_binary_mode + dependency_paths.claude into unified dependency_paths.claude.

        Old format had:
          - claude_binary_mode: "MANAGED" | "PATH" | "CUSTOM"
          - dependency_paths.claude: optional custom path (used when mode was CUSTOM)

        New format uses dependency_paths.claude as a unified value:
          - "MANAGED" for managed mode, "claude" (bare command) for PATH mode,
            or an absolute path for custom.
        """
        if not isinstance(data, dict):
            return data
        for mode_key, paths_key in (
            ("claude_binary_mode", "dependency_paths"),
            ("claudeBinaryMode", "dependencyPaths"),
        ):
            old_mode = data.pop(mode_key, None)
            if old_mode is None:
                continue
            paths = data.get(paths_key)
            if paths is None:
                paths = {}
                data[paths_key] = paths
            if isinstance(paths, dict):
                claude_key = "claude"
                if old_mode == "CUSTOM" and paths.get(claude_key):
                    pass  # custom path already set in dependency_paths.claude
                elif old_mode == "PATH":
                    paths[claude_key] = "claude"  # bare command, resolved via system PATH
                else:
                    paths[claude_key] = old_mode
        return data

    @model_validator(mode="before")
    @classmethod
    def _sanitize_custom_actions(cls, data: Any) -> Any:
        """Discard custom_actions if it doesn't match the expected schema.

        An earlier prototype stored custom_actions in a different format. Rather
        than crashing the entire config load, we silently drop the invalid value
        so the rest of the configuration is preserved.
        """
        if not isinstance(data, dict):
            return data
        # Check both snake_case (TOML/backend) and camelCase (frontend API) keys
        for key in ("custom_actions", "customActions"):
            value = data.get(key)
            if value is not None and not isinstance(value, (dict, CustomActionsConfig)):
                logger.warning("Ignoring invalid custom_actions config (expected dict, got {})", type(value).__name__)
                data[key] = None
        return data

    @property
    def free_disk_gb_warn_limit(self) -> float:
        return self.min_free_disk_gb * _FREE_DISK_GB_WARN_LIMIT_MULTIPLIER


# At Runtime, ensure that all fields in PrivacySettings are also in UserConfig
for field in PrivacySettings.model_fields:
    assert field in UserConfig.model_fields, f"PrivacySettings field {field} is missing from UserConfig"


def _generate_user_config_field_enum() -> type[StrEnum]:
    """Generate UserConfigField enum from UserConfig model fields"""
    fields = {}
    for field_name in UserConfig.model_fields.keys():
        # Convert field name to SCREAMING_SNAKE_CASE for enum constant
        enum_name = field_name.upper()
        fields[enum_name] = to_camel(field_name)
    # type checkers think this returns a StrEnum instance because they don't model functional enum creation
    # pyrefly: ignore [bad-return]
    return StrEnum("UserConfigField", fields)


UserConfigField: type[StrEnum] = _generate_user_config_field_enum()
