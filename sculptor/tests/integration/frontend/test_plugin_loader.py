"""Integration tests for adding plugin sources through the settings page.

These exercise the host-side *loader*: a user pastes a plugin source (a URL or
path that contains a ``manifest.json``) into Settings -> Plugins, and the host
fetches the manifest, validates it, dynamic-imports the entry module, and runs
its ``activate``. Each source renders a row whose ``data-status`` reflects the
outcome and, on failure, a ``data-phase`` naming the stage that failed.

The flow lives behind the experimental ``enable_frontend_plugins`` flag. The
browser tests use a fresh factory instance seeded with the flag on; the Electron
variant rides the shared instance (the only path that launches a real,
non-packaged Electron today -- the factory is browser-only) and flips the flag on
at runtime via the Experimental toggle. The same loader assertions back all of
them, shared through ``_exercise_*`` helpers.

Plugin sources are served from a local cross-origin fixture HTTP server (the
shape a plugin dev server takes), which lets each failure mode be reproduced
deterministically -- malformed JSON, a manifest that fails validation, a
CORS-blocked fetch, a missing entry module, and a module that has no default
export or throws on activate. The companion "plugin runtime" tests (a plugin
actually interacting with Sculptor) are intentionally out of scope here.
"""

from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.settings_plugins import PlaywrightPluginsSettingsElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.plugin_fixture_server import PluginFixtureServer
from sculptor.testing.plugin_fixture_server import spawn_plugin_fixture_server
from sculptor.testing.resources import _default_sculptor_folder_populator
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

# A minimal valid plugin entry: a default-exported activate that contributes
# nothing. Reaching "loaded" proves the whole chain ran (fetch -> validate ->
# import -> activate returned without throwing); what the plugin *does* with the
# api is the separate "plugin runtime" suite's concern.
_VALID_PLUGIN_JS = "export default function activate(api) {}\n"

# An entry module with no default export -> the loader has nothing to call.
_NO_DEFAULT_JS = "export const notActivate = 1;\n"

# An entry whose activate throws -> failure surfaces in the activate phase.
_THROWS_ON_ACTIVATE_JS = "export default function activate() { throw new Error('boom'); }\n"


def _enable_frontend_plugins_populator(folder_path: Path) -> None:
    """Seed the per-test sculptor folder with ``enable_frontend_plugins=True``."""
    _default_sculptor_folder_populator(folder_path)
    config_path = folder_path / "internal" / "config.toml"
    config = load_config(config_path).model_copy(update={"enable_frontend_plugins": True})
    save_config(config, config_path)


def _valid_manifest(plugin_id: str, **overrides: object) -> dict[str, object]:
    """A manifest that passes validation, with fields overridable per fixture."""
    manifest: dict[str, object] = {
        "id": plugin_id,
        "name": plugin_id,
        "version": "0.1.0",
        "entry": "main.js",
        "sdkVersion": "^1.0.0",
    }
    manifest.update(overrides)
    return manifest


def _exercise_error_modes(plugins: PlaywrightPluginsSettingsElement, server: PluginFixtureServer) -> list[str]:
    """Add a source for every malformed mode and assert each lands at its phase.

    Returns the sources added, so a caller on a long-lived (shared) instance can
    clean them up afterward.
    """
    # --- malformed data: the manifest can't be parsed or doesn't validate ---
    bad_json = server.add_plugin("bad-json", manifest="{ this is not valid json", entry_js=_VALID_PLUGIN_JS)
    missing_fields = server.add_plugin(
        "missing-fields",
        # No `entry` / `sdkVersion`: validateManifest rejects it.
        manifest={"id": "missing-fields", "name": "Missing Fields", "version": "0.1.0"},
        entry_js=_VALID_PLUGIN_JS,
    )
    sdk_mismatch = server.add_plugin(
        "sdk-mismatch",
        manifest=_valid_manifest("sdk-mismatch", sdkVersion="2.0.0"),
        entry_js=_VALID_PLUGIN_JS,
    )

    # --- fetch failures: reachable-but-404, CORS-blocked, and a same-origin typo ---
    not_found = server.source_for("never-registered")  # nothing registered -> 404
    cors_blocked = server.add_plugin(
        "cors-blocked", manifest=_valid_manifest("cors-blocked"), entry_js=_VALID_PLUGIN_JS, cors=False
    )
    # A same-origin path the user might fat-finger: the SPA catch-all returns
    # index.html (HTML, 200), so JSON parsing fails -> manifest phase.
    same_origin_typo = "/plugins/__does_not_exist__"

    # --- malformed plugin: manifest is fine but the module can't load/activate ---
    entry_missing = server.add_plugin(
        "entry-missing", manifest=_valid_manifest("entry-missing"), entry_js=None
    )  # manifest ok, entry path 404s
    no_default = server.add_plugin("no-default", manifest=_valid_manifest("no-default"), entry_js=_NO_DEFAULT_JS)
    activate_throws = server.add_plugin(
        "activate-throws", manifest=_valid_manifest("activate-throws"), entry_js=_THROWS_ON_ACTIVATE_JS
    )

    cases: list[tuple[str, str]] = [
        (bad_json, "manifest"),
        (not_found, "manifest"),
        (cors_blocked, "manifest"),
        (same_origin_typo, "manifest"),
        (missing_fields, "validate"),
        (sdk_mismatch, "validate"),
        (entry_missing, "import"),
        (no_default, "activate"),
        (activate_throws, "activate"),
    ]

    for source, _phase in cases:
        plugins.add_source(source)
    for source, phase in cases:
        plugins.expect_failed(source, phase=phase)

    return [source for source, _phase in cases]


def _exercise_valid_load_and_remove(plugins: PlaywrightPluginsSettingsElement, server: PluginFixtureServer) -> None:
    """Add a well-formed source, assert it loads (name/version), then remove it."""
    source = server.add_plugin(
        "hello",
        manifest=_valid_manifest("hello", name="Hello Plugin"),
        entry_js=_VALID_PLUGIN_JS,
    )

    plugins.add_source(source)
    plugins.expect_loaded(source, name="Hello Plugin", version="0.1.0")

    plugins.remove_source(source)
    expect(plugins.get_source_row(source)).to_have_count(0)


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_plugin_source_error_modes(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Every malformed-source mode settles the row into an error at its phase.

    This is the user-facing contract behind the loader: a bad source must end up
    as a visible error (never a perpetual spinner), tagged with the stage that
    failed so the message is actionable.
    """
    with (
        sculptor_instance_factory_.spawn_instance() as instance,
        spawn_plugin_fixture_server() as server,
    ):
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        _exercise_error_modes(plugins, server)


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_valid_plugin_loads_and_can_be_removed(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """A well-formed cross-origin source loads (name/version shown) and removes cleanly."""
    with (
        sculptor_instance_factory_.spawn_instance() as instance,
        spawn_plugin_fixture_server() as server,
    ):
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        _exercise_valid_load_and_remove(plugins, server)


@pytest.mark.electron
def test_plugin_loader_in_electron(sculptor_instance_: SculptorInstance) -> None:
    """The same loader flow, exercised inside a real Electron shell.

    Scope: this is *non-packaged* Electron -- the renderer is still served over
    ``http://localhost`` and driven via CDP. So it covers the Electron
    process/IPC model and a real cross-origin fetch + dynamic import from a
    different origin, but NOT the packaged app's ``file://`` origin (where
    ``window.location.origin`` is ``"null"`` and the same-origin/CORS rules
    differ). That packaged ``file://`` case remains a separate, unsolved scenario.

    The factory fixture can't launch a non-packaged Electron, so Electron
    coverage rides the shared instance. That instance ships with the flag off, so
    we flip it on through the Experimental settings (live, no reload) before
    driving the Plugins section, and flip it back off afterward so later
    Electron tests start from a clean flag. (The error rows the run leaves behind
    are renderer-local and harmless -- no other Electron test reads plugin
    sources -- so we don't bother removing them.)
    """
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    settings_page.click_on_experimental().set_frontend_plugins(enabled=True)
    try:
        with spawn_plugin_fixture_server() as server:
            plugins = settings_page.click_on_plugins()
            _exercise_error_modes(plugins, server)
            _exercise_valid_load_and_remove(plugins, server)
    finally:
        # Restore the shared instance's flag for later Electron tests. Let this
        # raise on failure rather than swallowing it: a silent cleanup failure
        # would leave the instance in a bad state for the next test, so it's
        # better to surface it (worst case, a double exception with the body).
        settings_page.click_on_experimental().set_frontend_plugins(enabled=False)
