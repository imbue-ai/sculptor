"""Integration tests for the Plugins settings section and its master switch.

The Plugins settings section is always present in the sidebar — it hosts the
master switch (the kill switch for the whole plugin system), so it must stay
reachable even when the system is off, to flip it back on. Turning the switch on
reveals the plugin-management UI (the add-source input and the list); turning it
off hides that UI but leaves the section and switch in place, live, with no
reload.

The plugin system ships on by default, but the broad UI integration suite pins
it off (see ``_make_test_user_config``) so panel-layout assertions don't depend
on which plugins ship enabled. These tests therefore exercise the off baseline
and the switch that flips it on.

Two instances are used deliberately:
  - the shared ``sculptor_instance_`` asserts the always-present section without
    mutating any config, so it leaves no state behind;
  - a fresh factory instance owns the switch mutation and is torn down (process
    + temp folder) when its ``spawn_instance()`` context exits.
"""

from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory


def test_plugins_section_always_present(sculptor_instance_: SculptorInstance) -> None:
    """The Plugins section is in the sidebar and hosts the (off) master switch.

    Uses the shared instance and mutates nothing, so there is nothing to clean
    up — the assertion is purely read-only.
    """
    page = sculptor_instance_.page
    settings_page = navigate_to_settings_page(page=page)

    # The section is always present — it stays reachable to flip the system on.
    expect(settings_page.get_plugins_nav()).to_be_visible()

    plugins = settings_page.click_on_plugins()
    # The suite pins the system off, so the switch is off and the management UI
    # (add-source input) is hidden, leaving just the switch.
    expect(plugins.get_frontend_plugins_toggle()).to_have_attribute("data-state", "unchecked")
    expect(plugins.get_source_input()).to_have_count(0)


def test_master_switch_reveals_management_ui_live(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """Toggling the master switch shows/hides the management UI without a reload.

    A fresh factory instance keeps this mutation isolated; it is fully torn down
    when the ``spawn_instance()`` context exits.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settings_page = navigate_to_settings_page(page=page)
        plugins = settings_page.click_on_plugins()

        # Turning the switch on reveals the add-source input and the list.
        plugins.set_frontend_plugins(enabled=True)
        expect(plugins.get_source_input()).to_be_visible()

        # Turning it back off hides the management UI, but the section and switch
        # stay put so the system can be turned on again.
        plugins.set_frontend_plugins(enabled=False)
        expect(settings_page.get_plugins_nav()).to_be_visible()
        expect(plugins.get_source_input()).to_have_count(0)
