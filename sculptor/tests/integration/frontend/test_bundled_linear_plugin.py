"""Integration test for the bundled Linear example plugin (SCU-1552).

Unlike test_plugin_loader.py — which exercises the loader against synthetic
fixture-server plugins — this targets the *real* bundled `linear-issue` plugin,
the one the host Vite build compiles into `public/plugins/`. It asserts the
built-in source both:

  1. loads — the bundle was fetched, validated, imported, and activated, and
  2. renders its own React — the plugin's settings component mounts and shows
     its content.

A broken build fails here: a bundle that throws at import (e.g. a dev-JSX build
that dragged `process.env.NODE_ENV` in) never reaches "loaded"; one that throws
at render (e.g. calling `jsxDEV` against a host that only ships the prod JSX
runtime) trips the plugin error boundary, so the settings text never appears.

Runs in both browser and electron launch modes, since the plugin ships bundled
into the served build for every mode.
"""

from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.settings_plugins import PlaywrightPluginsSettingsElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.resources import _default_sculptor_folder_populator
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

# The built-in source the host registers for the bundled Linear plugin.
LINEAR_SOURCE = "/plugins/linear-issue"
# Stable text from the plugin's own settings component (LinearSettings). The
# plugin error boundary would replace it on a render failure, so asserting it
# confirms the plugin's React actually ran.
LINEAR_SETTINGS_TEXT = "Personal API key from Linear"


def _enable_frontend_plugins_populator(folder_path: Path) -> None:
    """Seed the per-test sculptor folder with ``enable_frontend_plugins=True``."""
    _default_sculptor_folder_populator(folder_path)
    config_path = folder_path / "internal" / "config.toml"
    config = load_config(config_path).model_copy(update={"enable_frontend_plugins": True})
    save_config(config, config_path)


def _assert_linear_plugin_loads_and_renders(plugins: PlaywrightPluginsSettingsElement) -> None:
    """The built-in Linear plugin loads, then renders its own settings React."""
    plugins.expect_loaded(LINEAR_SOURCE, name="Linear", version="0.1.0")
    plugins.open_source_settings(LINEAR_SOURCE)
    expect(plugins.get_source_row(LINEAR_SOURCE)).to_contain_text(LINEAR_SETTINGS_TEXT)


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_bundled_linear_plugin_loads_and_renders(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """In a browser, the bundled Linear plugin loads and renders its UI."""
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        _assert_linear_plugin_loads_and_renders(plugins)


@pytest.mark.electron
def test_bundled_linear_plugin_loads_and_renders_in_electron(
    sculptor_instance_: SculptorInstance,
) -> None:
    """In Electron, the bundled Linear plugin loads and renders its UI."""
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    settings_page.click_on_experimental().set_frontend_plugins(enabled=True)
    try:
        plugins = settings_page.click_on_plugins()
        _assert_linear_plugin_loads_and_renders(plugins)
    finally:
        # Leave the shared instance's flag as we found it for the next test.
        settings_page.click_on_experimental().set_frontend_plugins(enabled=False)
