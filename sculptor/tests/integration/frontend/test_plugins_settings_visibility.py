"""Integration tests for the experimental frontend-plugins gating.

The plugin system ships behind the experimental `enable_frontend_plugins`
UserConfig flag. With the flag off (the default) the Plugins settings section
must be absent from the sidebar; with it on, the section appears, and toggling
the switch flips that visibility live (no reload needed for the section itself).

Two instances are used deliberately:
  - the shared `sculptor_instance_` asserts the default-off behavior without
    mutating any config, so it leaves no state behind;
  - a fresh factory instance, seeded with the flag on via a folder populator,
    owns all the mutation and is torn down (process + temp folder) when its
    `spawn_instance()` context exits.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.resources import _default_sculptor_folder_populator
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory


def test_plugins_section_hidden_by_default(sculptor_instance_: SculptorInstance) -> None:
    """With the default config (flag off), the Plugins nav item is absent.

    Uses the shared instance and mutates nothing, so there is nothing to clean
    up — the assertion is purely read-only.
    """
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)

    # The section is gated off by default, so the nav item should not render.
    expect(settings_page.get_plugins_nav()).to_have_count(0)

    # Sanity: the Experimental section is reachable and the flag toggle exists
    # but is off — confirming the gating wiring (not just a missing test id).
    experimental = settings_page.click_on_experimental()
    expect(experimental.get_frontend_plugins_toggle()).to_have_attribute("data-state", "unchecked")


def _enable_frontend_plugins_populator(folder_path: Path) -> None:
    """Seed the per-test sculptor folder with `enable_frontend_plugins=True`."""
    _default_sculptor_folder_populator(folder_path)
    config_path = folder_path / "internal" / "config.toml"
    config = load_config(config_path).model_copy(update={"enable_frontend_plugins": True})
    save_config(config, config_path)


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_plugins_section_visible_and_toggles_with_switch(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Seeded on, the Plugins section shows; the switch hides/shows it live.

    A fresh factory instance keeps this mutation isolated; it is fully torn
    down when the `spawn_instance()` context exits.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settings_page = navigate_to_settings_page(page=page)

        # Seeded with the flag on -> the section is present.
        expect(settings_page.get_plugins_nav()).to_be_visible()

        # Turning the switch off removes the section without a reload.
        experimental = settings_page.click_on_experimental()
        experimental.set_frontend_plugins(enabled=False)
        expect(settings_page.get_plugins_nav()).to_have_count(0)

        # Turning it back on brings the section back.
        experimental.set_frontend_plugins(enabled=True)
        expect(settings_page.get_plugins_nav()).to_be_visible()
