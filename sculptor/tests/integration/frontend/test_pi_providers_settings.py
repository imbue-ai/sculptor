"""Integration coverage for the Settings -> Pi -> Providers sections.

Renders the authentication status from GET /api/v1/pi/providers/authenticated and
verifies the Connected cards, the Add-a-provider grid, and the Session-only callout.
auth.json is isolated via PI_CODING_AGENT_DIR (pointed at a temp dir) so the
developer's real ~/.pi/agent/auth.json is never read or mutated.
"""

import json
from pathlib import Path

from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _set_pi_config_custom(factory: SculptorInstanceFactory) -> None:
    """Pin pi to CUSTOM so the spawned backend performs no startup auto-install.

    Mirrors test_pi_managed_install; only the binary-source value matters here —
    the Providers area reads process-global auth.json + env, not the pi binary.
    """
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    new_dependency_paths = config.dependency_paths.model_copy(update={"pi": "CUSTOM"})
    save_config(config.model_copy(update={"dependency_paths": new_dependency_paths}), config_path)


@user_story("to see my pi providers grouped by authentication status in Settings")
def test_pi_providers_settings_groups_and_detail(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    """anthropic (in auth.json) shows as a Connected card, an unconfigured single-key
    provider as an Add-a-provider cell, and a multi-value provider in the Session-only
    callout with the deferred-persistence explainer."""
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()
    (agent_dir / "auth.json").write_text(json.dumps({"anthropic": {"type": "api_key", "key": "x"}}), encoding="utf-8")
    sculptor_instance_factory_.update_environment(PI_CODING_AGENT_DIR=str(agent_dir))
    _set_pi_config_custom(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        # anthropic is in auth.json -> a Connected card with the live status label.
        connected = pi_section.get_providers_group_connected()
        expect(connected).to_contain_text("Anthropic")
        expect(connected).to_contain_text("Connected")

        # A single-key provider with no credential -> a cell in the Add-a-provider grid.
        expect(pi_section.get_providers_group_available()).to_contain_text("OpenRouter")

        # A multi-value provider -> the Session-only callout, with its deferred explainer.
        session_only = pi_section.get_providers_group_session_only()
        expect(session_only).to_contain_text("Amazon Bedrock")
        expect(session_only).to_contain_text("full standalone persistence is deferred")
