"""Integration tests for the Plugins settings section and its global toggle.

The Plugins settings section is always present in the sidebar — it hosts the
toggle that globally enables or disables the whole plugin system, so it must
stay reachable even when the system is off, to turn it back on. The system is on
by default: the section shows the plugin-management UI (the add-source input and
the list). Turning the toggle off hides that UI but leaves the section and toggle
in place, live, with no reload; turning it on reveals the management UI again.

Two instances are used deliberately:
  - the shared ``sculptor_instance_`` asserts the default-on state without
    mutating any config, so it leaves no state behind;
  - a fresh factory instance owns the toggle mutation and is torn down (process
    + temp folder) when its ``spawn_instance()`` context exits.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory


def test_plugins_section_present_and_on_by_default(sculptor_instance_: SculptorInstance) -> None:
    """The Plugins section is in the sidebar with the system on by default.

    Uses the shared instance and mutates nothing, so there is nothing to clean
    up — the assertion is purely read-only.
    """
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)

    # The section is always present (it stays reachable to turn the system on).
    expect(settings_page.get_plugins_nav()).to_be_visible()

    plugins = settings_page.click_on_plugins()
    # On by default: the toggle is on and the management UI (add-source input) shows.
    expect(plugins.get_frontend_plugins_toggle()).to_have_attribute("data-state", "checked")
    expect(plugins.get_source_input()).to_be_visible()


def test_global_toggle_hides_management_ui_live(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Toggling the global switch hides/shows the management UI without a reload.

    A fresh factory instance keeps this mutation isolated; it is fully torn down
    when the ``spawn_instance()`` context exits.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()

        # Turning the toggle off hides the add-source input and the list, but the
        # section and toggle stay put so the system can be turned back on.
        plugins.set_frontend_plugins(enabled=False)
        expect(settings_page.get_plugins_nav()).to_be_visible()
        expect(plugins.get_source_input()).to_have_count(0)

        # Turning it back on reveals the management UI again.
        plugins.set_frontend_plugins(enabled=True)
        expect(plugins.get_source_input()).to_be_visible()
