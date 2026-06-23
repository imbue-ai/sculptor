"""Integration test for panel open-state after a plugin panel is unloaded.

When a plugin contributes a panel and that panel is the *active* one in its
zone, unloading the plugin (turning it off) must fall back to an **enabled**
sibling panel — never to a panel the user has disabled.

The reproducer mirrors a real user setup: the bundled Linear plugin docks its
panel in the top-right zone (alongside the built-in, disabled-by-default
Browser panel). If the disabled Browser panel happens to sit ahead of the
remaining enabled panels in that zone's order, unloading the active Linear
panel used to select Browser as the fallback and actually render it — even
though the user never enabled it. This drives that exact arrangement through
the UI and asserts the fallback lands on an enabled panel instead.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.panel_zones import PlaywrightPanelZonesElement
from sculptor.testing.elements.panels import ensure_right_area_visible
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
        browser_panel = page.get_by_test_id(ElementIDs.BROWSER_PANEL)
        skills_panel = page.get_by_test_id(ElementIDs.SKILLS_PANEL)

        # The bundled Linear plugin auto-loads and docks a panel in top-right.
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()
        plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")

        # Arrange the top-right order so the disabled Browser panel sits *before*
        # the remaining enabled panel. The default order is
        # [actions, skills, browser]; moving the two enabled built-ins out and
        # one back (each move appends to the target zone's order) leaves
        # [browser (disabled), linear-issue, skills (enabled)].
        panels = settings_page.click_on_panels()
        panels.set_panel_zone("skills", "bottom-right")
        panels.set_panel_zone("actions", "bottom-right")
        panels.set_panel_zone("skills", "top-right")

        # Open the Linear panel so it is the active top-right panel.
        task_page.get_workspace_tabs().first.click()
        ensure_right_area_visible(page)
        zones.activate_plugin_panel("linear-issue")
        expect(zones.get_top_right_zone()).to_be_visible()
        # The disabled Browser panel must not be showing while Linear is active.
        expect(browser_panel).not_to_be_visible()

        # Turn the plugin off while its panel is the active one.
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()
        plugins.set_enabled(LINEAR_SOURCE, enabled=False)
        plugins.expect_disabled(LINEAR_SOURCE)

        # Back in the workspace, the zone must fall back to the enabled Skills
        # panel — never the disabled Browser panel.
        task_page.get_workspace_tabs().first.click()
        expect(browser_panel).not_to_be_visible()
        expect(skills_panel).to_be_visible()
