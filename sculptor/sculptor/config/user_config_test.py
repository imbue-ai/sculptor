from sculptor.config.user_config import CIBabysitterConfig
from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import PiConfig
from sculptor.config.user_config import UserConfig
from sculptor.config.user_config import UserConfigField


def test_ci_babysitter_defaults() -> None:
    config = UserConfig(
        user_email="test@example.com",
        user_id="user123",
        organization_id="org123",
        instance_id="inst123",
    )
    assert isinstance(config.ci_babysitter, CIBabysitterConfig)
    assert config.ci_babysitter.enabled is False
    assert config.ci_babysitter.retry_cap == 3
    assert config.ci_babysitter.pipeline_failed_prompt.startswith("Investigate the failing pipeline")
    assert config.ci_babysitter.merge_conflict_prompt.startswith("This MR has a merge conflict")
    assert UserConfigField["CI_BABYSITTER"].value == "ciBabysitter"


def test_pi_config_defaults_on_user_config() -> None:
    config = UserConfig(
        user_email="test@example.com",
        user_id="user123",
        organization_id="org123",
        instance_id="inst123",
    )
    assert isinstance(config.pi, PiConfig)
    assert config.pi.api_key_env_var_names == ("ANTHROPIC_API_KEY",)
    # pi defaults to MANAGED (mirrors claude); Sculptor downloads/version-pins it.
    assert config.dependency_paths.pi == "MANAGED"
    # The field is still named ``pi`` — only its default value changed.
    assert UserConfigField["PI"].value == "pi"


def test_persisted_bare_pi_value_is_not_migrated() -> None:
    """A previously persisted bare ``"pi"`` survives the default flip verbatim.

    Unlike claude (which has a ``_migrate_claude_binary_mode`` validator), pi has
    no migration validator. An existing config that persisted the old default
    ``"pi"`` must keep that value — it is treated as a CUSTOM/PATH binary at
    resolve time — rather than being rewritten to ``"MANAGED"``.
    """
    config = UserConfig(
        user_email="test@example.com",
        user_id="user123",
        organization_id="org123",
        instance_id="inst123",
        dependency_paths=DependencyPaths(pi="pi"),
    )
    assert config.dependency_paths.pi == "pi"


def test_enable_pi_agent_defaults_off() -> None:
    config = UserConfig(
        user_email="test@example.com",
        user_id="user123",
        organization_id="org123",
        instance_id="inst123",
    )
    assert config.enable_pi_agent is False
    assert UserConfigField["ENABLE_PI_AGENT"].value == "enablePiAgent"


def test_pi_config_round_trips_through_serialization() -> None:
    original = PiConfig(api_key_env_var_names=("ANTHROPIC_API_KEY", "PI_API_KEY"))
    restored = PiConfig.model_validate_json(original.model_dump_json())
    assert restored.api_key_env_var_names == ("ANTHROPIC_API_KEY", "PI_API_KEY")


def test_user_config_silently_ignores_removed_chat_view_legacy_field() -> None:
    """Regression for the delete-classic-chat removal.

    `chat_view_legacy` was a `UserConfig` field that's been deleted. Older
    clients (and stale on-disk configs) may still send / contain a
    `chatViewLegacy: true` value; the validation must accept the payload
    silently rather than raising. `SerializableModel` validates with
    `extra="allow"` and clears `__pydantic_extra__` in `model_post_init`,
    so the value is dropped on the next persistence write.
    """
    config = UserConfig.model_validate(
        {
            "userEmail": "test@example.com",
            "userId": "user123",
            "organizationId": "org123",
            "instanceId": "inst123",
            "chatViewLegacy": True,
        }
    )
    assert not hasattr(config, "chat_view_legacy")
