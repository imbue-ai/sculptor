"""Integration coverage for the inline pi login terminal in Settings -> Pi -> Providers.

Authenticate spawns an interactive pi PTY embedded in the detail pane; Done tears it
down. The PTY hosts a real login shell regardless of the pi binary, so this verifies
the inline-terminal wiring end-to-end without a real /login. The credential
round-trip (pi writing auth.json) is real_pi (Task 7.1). auth.json is isolated via
PI_CODING_AGENT_DIR so the developer's real credentials are untouched.
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
    """Pre-stage FakePi as the managed pi binary so it resolves without a download."""
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


@user_story("to authenticate a pi provider from Settings via an inline login terminal")
def test_pi_login_terminal_mounts_and_done_unmounts(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    """Authenticate mounts the inline login terminal; Done tears it down."""
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()
    # Empty auth.json: openrouter is an unconfigured single-key provider -> Available.
    (agent_dir / "auth.json").write_text(json.dumps({}), encoding="utf-8")
    sculptor_instance_factory_.update_environment(PI_CODING_AGENT_DIR=str(agent_dir))
    _set_pi_config_managed(sculptor_instance_factory_)
    _stage_fake_pi_managed_binary(sculptor_instance_factory_)

    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        pi_section = settings_page.click_on_pi()

        pi_section.get_provider_row("openrouter").click()
        authenticate_button = pi_section.get_authenticate_button()
        expect(authenticate_button).to_be_visible()
        authenticate_button.click()

        # The inline login terminal mounts and useTerminal connects the PTY WebSocket
        # (the container survives the brief 4404 retry while the PTY registers).
        expect(pi_section.get_login_terminal()).to_be_visible(timeout=30_000)

        pi_section.get_login_done_button().click()

        # Done tears down the session; the terminal unmounts and the actions return.
        expect(pi_section.get_login_terminal()).to_have_count(0)
        expect(pi_section.get_authenticate_button()).to_be_visible()
