"""Integration tests for panel open-state when a plugin's panel is unloaded.

When a plugin contributes a panel and that panel is the *active* one in its
zone, turning the plugin off — or turning it off then on again — must never
leave a panel the user has disabled (e.g. the Browser panel) rendered in that
zone.

The reproducer mirrors a real user setup: the bundled Linear plugin docks its
panel in the top-right zone (alongside the built-in, disabled-by-default
Browser panel). With the disabled Browser panel ordered ahead of the remaining
enabled panel, unloading the active Linear panel used to select Browser as the
fallback and actually render it. These tests drive that arrangement through the
UI and assert the zone falls back to an enabled panel instead — both for a
plain disable and for a disable-then-re-enable cycle.
"""

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.elements.panels import ensure_right_area_visible
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.resources import _default_sculptor_folder_populator
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

LINEAR_SOURCE = "/plugins/linear-issue"


def _enable_frontend_plugins_populator(folder_path: Path) -> None:
    """Seed the per-test sculptor folder with ``enable_frontend_plugins=True``."""
    _default_sculptor_folder_populator(folder_path)
    config_path = folder_path / "internal" / "config.toml"
    config = load_config(config_path).model_copy(update={"enable_frontend_plugins": True})
    save_config(config, config_path)


def _open_linear_with_disabled_browser_ahead(
    page: Page, task_page: PlaywrightTaskPage, zones: PlaywrightPanelZonesElement
) -> None:
    """Order the disabled Browser panel ahead of an enabled panel in top-right,
    then open the Linear plugin panel as the active one in that zone.

    The default top-right order is [actions, skills, browser]; moving the two
    enabled built-ins out and one back (each move appends to the target zone's
    order) leaves [browser (disabled), linear-issue, skills (enabled)] — so the
    disabled Browser panel is the first sibling after Linear is removed.
    """
    settings_page = navigate_to_settings_page(page=page)
    plugins = settings_page.click_on_plugins()
    plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")

    panels = settings_page.click_on_panels()
    panels.set_panel_zone("skills", "bottom-right")
    panels.set_panel_zone("actions", "bottom-right")
    panels.set_panel_zone("skills", "top-right")

    task_page.get_workspace_tabs().first.click()
    ensure_right_area_visible(page)
    zones.activate_plugin_panel("linear-issue")
    expect(zones.get_top_right_zone()).to_be_visible()
    # The disabled Browser panel must not be showing while Linear is active.
    expect(task_page.get_browser_panel_root()).not_to_be_visible()


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
@user_story("to keep a disabled panel hidden when I turn off a plugin whose panel was open")
def test_unloading_active_plugin_panel_falls_back_to_an_enabled_panel(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Turning off a plugin whose panel is the active one must fall back to an
    enabled sibling, not render a disabled panel (e.g. Browser)."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        task_page = start_task_and_wait_for_ready(page, prompt="panel persistence", workspace_name="Panels WS")
        zones = PlaywrightPanelZonesElement(page)
        _open_linear_with_disabled_browser_ahead(page, task_page, zones)

        # Turn the plugin off while its panel is the active one.
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()
        plugins.set_enabled(LINEAR_SOURCE, enabled=False)
        plugins.expect_disabled(LINEAR_SOURCE)

        # Back in the workspace, the zone must fall back to the enabled Skills
        # panel — never the disabled Browser panel.
        task_page.get_workspace_tabs().first.click()
        expect(task_page.get_browser_panel_root()).not_to_be_visible()
        expect(task_page.get_skills_panel()).to_be_visible()


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
@user_story("to keep a disabled panel hidden after I toggle a plugin off and back on")
def test_toggling_plugin_off_then_on_does_not_open_a_disabled_panel(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Disabling and then re-enabling a plugin (both from the settings page)
    must not leave a disabled panel (e.g. Browser) rendered in the zone where
    the plugin panel had been active."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page

        task_page = start_task_and_wait_for_ready(page, prompt="panel persistence", workspace_name="Panels WS")
        zones = PlaywrightPanelZonesElement(page)
        _open_linear_with_disabled_browser_ahead(page, task_page, zones)

        # Toggle the plugin off and then back on, both within the settings page.
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()
        plugins.set_enabled(LINEAR_SOURCE, enabled=False)
        plugins.expect_disabled(LINEAR_SOURCE)
        plugins.set_enabled(LINEAR_SOURCE, enabled=True)
        plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")

        # Back in the workspace, the disabled Browser panel must not be showing;
        # the zone shows the enabled Skills panel and the re-loaded Linear panel
        # is available again in the sidebar.
        task_page.get_workspace_tabs().first.click()
        expect(task_page.get_browser_panel_root()).not_to_be_visible()
        expect(task_page.get_skills_panel()).to_be_visible()
        expect(zones.get_plugin_panel_icon("linear-issue")).to_be_visible()
