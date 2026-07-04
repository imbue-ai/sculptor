"""Integration coverage for the paste-key path in the Settings -> Pi -> Providers modal.

Pasting a key for an Add-a-provider single-key provider writes auth.json (isolated via
PI_CODING_AGENT_DIR) and moves the provider to Connected. Session-only providers are in
the explainer callout, not the grid, so they offer no paste form.
"""

import json
from pathlib import Path

from playwright.sync_api import expect

from sculptor.services.dependency_management_service import DEPENDENCIES_DIR_NAME
from sculptor.services.dependency_management_service import PI_VERSION_RANGE
from sculptor.services.dependency_management_service import _VERSION_DIR_PREFIX
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


def _set_pi_config_managed(factory: SculptorInstanceFactory) -> None:
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    new_dependency_paths = config.dependency_paths.model_copy(update={"pi": "MANAGED"})
    save_config(config.model_copy(update={"dependency_paths": new_dependency_paths}), config_path)


def _stage_fake_pi_managed_binary(factory: SculptorInstanceFactory) -> None:
    version_dir = (
        factory._delegate.sculptor_folder
        / "internal"
        / DEPENDENCIES_DIR_NAME
        / "pi"
        / f"{_VERSION_DIR_PREFIX}{PI_VERSION_RANGE.recommended_version}"
    )
    pi_tree = version_dir / "pi"
    pi_tree.mkdir(parents=True, exist_ok=True)
    install_fake_pi_binary(pi_tree)


@user_story("to authenticate a pi provider by pasting an API key from Settings")
def test_pi_paste_key_connects_provider(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    """Pasting a key moves an Available provider to Connected and writes auth.json."""
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()
    (agent_dir / "auth.json").write_text(json.dumps({}), encoding="utf-8")
    sculptor_instance_factory_.update_environment(PI_CODING_AGENT_DIR=str(agent_dir))
    _set_pi_config_managed(sculptor_instance_factory_)
    _stage_fake_pi_managed_binary(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        # Open the login modal from openrouter's Add cell, then switch to the paste path.
        pi_section.get_add_provider_cell("openrouter").click()
        pi_section.get_paste_key_switch().click()
        pi_section.get_paste_key_input().fill("sk-or-test-key")
        pi_section.get_paste_key_save().click()

        # Saving closes the modal; the list refetches and openrouter moves to Connected.
        expect(pi_section.get_providers_group_connected()).to_contain_text("OpenRouter", timeout=30_000)

    # The key was merged into the isolated auth.json (never the developer's real file).
    written = json.loads((agent_dir / "auth.json").read_text(encoding="utf-8"))
    assert written["openrouter"] == {"type": "api_key", "key": "sk-or-test-key"}


@user_story("to not be offered a paste-key form for a session-only provider")
def test_pi_paste_key_absent_for_session_only_provider(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    """A session-only provider (amazon-bedrock) shows only the explainer callout — no Add cell, no paste form."""
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()
    (agent_dir / "auth.json").write_text(json.dumps({}), encoding="utf-8")
    sculptor_instance_factory_.update_environment(PI_CODING_AGENT_DIR=str(agent_dir))
    _set_pi_config_managed(sculptor_instance_factory_)
    _stage_fake_pi_managed_binary(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        # A session-only provider lives in the explainer callout, not the Add grid.
        expect(pi_section.get_providers_group_session_only()).to_contain_text("deferred")
        expect(pi_section.get_add_provider_cell("amazon-bedrock")).to_have_count(0)
