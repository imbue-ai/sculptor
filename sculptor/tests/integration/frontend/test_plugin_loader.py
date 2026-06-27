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

import json
import shutil
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
from sculptor.web.app import _display_path

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


def _local_plugin_populator(folder_path: Path) -> None:
    """Seed the per-test sculptor folder with the flag on AND a drop-in plugin.

    Writes a complete plugin under ``<folder>/plugins/local-hello/`` — exactly
    the "drop a folder into ``~/.sculptor/plugins/``" flow — so the backend
    discovers it and the renderer auto-loads it as a read-only "local" source,
    with no user action and no cross-origin dev server. This proves the host can
    run *arbitrary* local plugin code end-to-end.
    """
    _enable_frontend_plugins_populator(folder_path)
    plugin_dir = folder_path / "plugins" / "local-hello"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    (plugin_dir / "manifest.json").write_text(
        json.dumps(_valid_manifest("local-hello", name="Local Hello", version="0.2.0"))
    )
    (plugin_dir / "main.js").write_text(_VALID_PLUGIN_JS)


def _competing_local_plugins_populator(folder_path: Path) -> None:
    """Seed two local plugins that declare the SAME manifest id, so they compete.

    On boot only one may be active; the other is shown but "shadowed" with its
    enable toggle locked. The two are equal priority (both local), so the
    discovery order (sorted by directory name) breaks the tie — ``dupe-a`` wins.
    """
    _enable_frontend_plugins_populator(folder_path)
    for dir_name in ("dupe-a", "dupe-b"):
        plugin_dir = folder_path / "plugins" / dir_name
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "manifest.json").write_text(
            json.dumps(_valid_manifest("dupe-demo", name="Dupe Demo", version="0.1.0"))
        )
        (plugin_dir / "main.js").write_text(_VALID_PLUGIN_JS)


def _broken_local_plugin_populator(folder_path: Path) -> None:
    """Seed a local plugin whose manifest fails validation (missing required
    fields). The loader's error handling is shared with the URL path, but this
    proves an error row renders for a discovered *local* source too.
    """
    _enable_frontend_plugins_populator(folder_path)
    plugin_dir = folder_path / "plugins" / "broken-local"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    # No `entry` / `sdkVersion`: validateManifest rejects it (validate phase).
    (plugin_dir / "manifest.json").write_text(json.dumps({"id": "broken-local", "name": "Broken", "version": "0.1.0"}))


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


def _exercise_disable_and_enable(plugins: PlaywrightPluginsSettingsElement, server: PluginFixtureServer) -> None:
    """A loaded source can be disabled (parked, not loaded) and re-enabled.

    Disabling is the opt-out path: the source stays on the list but does not
    load, so a remotely-pulled-in plugin can be silenced without deleting the
    reference. Re-enabling loads it again. (That the disabled choice survives a
    relaunch is covered by the manager's bootstrap unit test.)
    """
    source = server.add_plugin(
        "toggle-me",
        manifest=_valid_manifest("toggle-me", name="Toggle Me"),
        entry_js=_VALID_PLUGIN_JS,
    )

    plugins.add_source(source)
    plugins.expect_loaded(source, name="Toggle Me", version="0.1.0")

    # Disable: the row stays on the list but parks in the disabled state.
    plugins.set_enabled(source, enabled=False)
    plugins.expect_disabled(source)

    # Re-enable: it loads again from scratch.
    plugins.set_enabled(source, enabled=True)
    plugins.expect_loaded(source, name="Toggle Me", version="0.1.0")

    plugins.remove_source(source)
    expect(plugins.get_source_row(source)).to_have_count(0)


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_plugin_source_can_be_disabled_and_re_enabled(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """A loaded source can be disabled without removal and later re-enabled."""
    with (
        sculptor_instance_factory_.spawn_instance() as instance,
        spawn_plugin_fixture_server() as server,
    ):
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        _exercise_disable_and_enable(plugins, server)


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


@custom_sculptor_folder_populator.with_args(_local_plugin_populator)
def test_local_plugin_is_discovered_and_loaded(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """A plugin dropped into ``~/.sculptor/plugins/`` is auto-discovered and loaded.

    No source is added by hand: on boot the backend lists the directory, the
    renderer registers each entry as a read-only "local" source, and the normal
    loader fetches + imports + activates it. The row shows the plugin's
    name/version, is tagged ``local``, and offers no Remove control (removing
    would be meaningless — it would reappear on the next rescan).
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()

        local_rows = plugins.get_rows_by_kind("local")
        expect(local_rows).to_have_count(1)
        row = local_rows.first
        expect(row).to_have_attribute("data-status", "loaded")
        expect(row).to_contain_text("Local Hello")
        expect(row).to_contain_text("v0.2.0")
        # Read-only: a discovered local plugin can't be removed from the UI.
        expect(plugins.get_remove_button_in(row)).to_have_count(0)


@custom_sculptor_folder_populator.with_args(_competing_local_plugins_populator)
def test_competing_plugins_one_active_one_shadowed(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """Two sources providing the same plugin id: one loads, the other is shadowed.

    Both rows are shown. The shadowed one carries a locked enable toggle (you
    can't run two versions of one plugin at once) — the manifest of "the local
    dev / workspace / remote version" story. Switching is manual: disable the
    active one first.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()

        expect(plugins.get_rows_by_kind("local")).to_have_count(2)
        expect(plugins.get_rows_by_kind_and_status(kind="local", status="loaded")).to_have_count(1)
        shadowed = plugins.get_rows_by_kind_and_status(kind="local", status="shadowed")
        expect(shadowed).to_have_count(1)
        # The shadowed version's toggle is locked while the other is active.
        expect(plugins.get_toggle_in(shadowed)).to_be_disabled()


@custom_sculptor_folder_populator.with_args(_broken_local_plugin_populator)
def test_local_plugin_with_invalid_manifest_shows_error(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """A discovered local plugin whose manifest fails validation surfaces as an
    error row tagged with the failing phase — the same loader contract as a
    malformed URL source, exercised here for the local path.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()

        errored = plugins.get_rows_by_kind_and_status(kind="local", status="error")
        expect(errored).to_have_count(1)
        expect(errored).to_have_attribute("data-phase", "validate")


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_refresh_discovers_added_plugin_and_dead_traces_a_removed_one(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """The manual Refresh button re-scans ``~/.sculptor/plugins/`` live.

    Two halves of the same contract: (1) a plugin folder dropped in *after* the
    app loaded is picked up by Refresh — no hard reload — and (2) once the user
    has a persisted on/off choice for a local plugin, removing it from disk
    leaves a ``missing`` dead-trace row (so the choice is visible and re-applied
    if it returns) rather than vanishing silently; that row can be forgotten with
    Remove.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()

        # Nothing under ~/.sculptor/plugins/ at boot.
        expect(plugins.get_rows_by_kind("local")).to_have_count(0)

        # Drop a complete plugin in while the app is running. The source identity
        # is the port-stable relative dir, so we can address its row directly.
        source = "/plugins/local/late-arrival"
        plugin_dir = instance.sculptor_folder / "plugins" / "late-arrival"
        plugin_dir.mkdir(parents=True, exist_ok=True)
        (plugin_dir / "manifest.json").write_text(
            json.dumps(_valid_manifest("late-arrival", name="Late Arrival", version="1.2.3"))
        )
        (plugin_dir / "main.js").write_text(_VALID_PLUGIN_JS)

        # Refresh discovers and loads it — no full reload.
        plugins.refresh()
        plugins.expect_loaded(source, name="Late Arrival", version="1.2.3")

        # Give it a persisted choice (disable it), then remove it from disk.
        plugins.set_enabled(source, enabled=False)
        plugins.expect_disabled(source)
        shutil.rmtree(plugin_dir)

        # It's gone from disk but the choice is remembered, so it stays as a
        # "missing" dead-trace row (not loaded, so safe to drop the live plugin).
        plugins.refresh()
        expect(plugins.get_source_row(source)).to_have_attribute("data-status", "missing")

        # The dead-trace row is forgettable via Remove (a present local row is not).
        plugins.remove_source(source)
        expect(plugins.get_source_row(source)).to_have_count(0)


@custom_sculptor_folder_populator.with_args(_enable_frontend_plugins_populator)
def test_plugins_directory_shows_real_backend_path(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """The directory chip shows this instance's real data folder, not a placeholder.

    The section renders the plugins directory the backend reports (home collapsed
    to ``~``), with a layered fallback. Asserting the chip matches that real path
    guards against the hardcoded ``~/.sculptor/plugins`` placeholder leaking
    through when the real directory differs — the regression this addresses.

    Scope: here the dedicated ``/api/v1/plugins/dir`` endpoint and the
    health-check fallback resolve to the *same* string — the per-test data folder
    is outside ``$HOME``, so ``_display_path`` has no ``~`` to collapse — so this
    asserts the rendered path is correct without isolating which source produced
    it. The endpoint's home-collapse formatting is covered separately by the
    backend unit tests in ``app_local_plugins_test.py``.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()

        expected = _display_path(instance.sculptor_folder / "plugins")
        # Sanity-check the assertion is meaningful: the real path must differ from
        # the hardcoded placeholder, or this test couldn't catch that regression.
        assert expected != "~/.sculptor/plugins"
        expect(plugins.get_directory_label()).to_have_text(expected)


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
    coverage rides the shared instance. The broad UI suite pins the plugin
    system off (see ``_make_test_user_config``), so we flip it on through the
    Plugins section's master switch (live, no reload) before driving the section,
    and flip it back off afterward so later Electron tests start from a clean
    flag. (The error rows the run leaves behind are renderer-local and harmless
    -- no other Electron test reads plugin sources -- so we don't bother removing
    them.)
    """
    settings_page = navigate_to_settings_page(page=sculptor_instance_.page)
    plugins = settings_page.click_on_plugins()
    plugins.set_frontend_plugins(enabled=True)
    try:
        with spawn_plugin_fixture_server() as server:
            _exercise_error_modes(plugins, server)
            _exercise_valid_load_and_remove(plugins, server)
    finally:
        # Restore the shared instance's flag for later Electron tests. Let this
        # raise on failure rather than swallowing it: a silent cleanup failure
        # would leave the instance in a bad state for the next test, so it's
        # better to surface it (worst case, a double exception with the body).
        plugins.set_frontend_plugins(enabled=False)
