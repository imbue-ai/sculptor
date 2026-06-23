"""Tests for the local-plugins endpoints: directory scan (`get_local_plugins`)
and the display-path report (`get_local_plugins_directory`).

The static serving of the files themselves (the `/plugins/local` mount) is
covered end-to-end by the frontend integration tests; here we only exercise the
directory-scan logic and the path formatting, the parts with branches worth
pinning down.
"""

from pathlib import Path

import sculptor.web.app as app_module
from sculptor.web.app import get_local_plugins
from sculptor.web.app import get_local_plugins_directory


def _write_plugin(plugins_dir: Path, plugin_id: str, *, with_manifest: bool = True) -> None:
    plugin_dir = plugins_dir / plugin_id
    plugin_dir.mkdir(parents=True)
    if with_manifest:
        (plugin_dir / "manifest.json").write_text('{"id": "' + plugin_id + '"}')
        (plugin_dir / "main.js").write_text("export default () => {};")


def test_lists_only_directories_with_a_manifest_sorted_by_name(tmp_path: Path, monkeypatch) -> None:
    plugins_dir = tmp_path / "plugins"
    # Out-of-order on purpose: the endpoint sorts for a stable row order.
    _write_plugin(plugins_dir, "beta")
    _write_plugin(plugins_dir, "alpha")
    # A directory without a manifest, and a stray file, must both be skipped.
    _write_plugin(plugins_dir, "no-manifest", with_manifest=False)
    (plugins_dir / "stray.txt").write_text("not a plugin")
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)

    result = get_local_plugins()

    assert [plugin.id for plugin in result] == ["alpha", "beta"]
    assert result[0].manifest_url == "/plugins/local/alpha/manifest.json"


def test_empty_when_plugins_dir_absent(tmp_path: Path, monkeypatch) -> None:
    # tmp_path has no `plugins/` subdirectory — a fresh install before the mount
    # has created it, or a user who never added a plugin.
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)

    assert get_local_plugins() == []


def test_percent_encodes_directory_names_with_url_special_chars(tmp_path: Path, monkeypatch) -> None:
    # A space (and other URL-special chars) in a plugin folder name must be
    # encoded, or the manifest URL the frontend fetches would be corrupted.
    plugins_dir = tmp_path / "plugins"
    _write_plugin(plugins_dir, "needs encoding")
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)

    result = get_local_plugins()

    assert result[0].id == "needs encoding"
    assert result[0].manifest_url == "/plugins/local/needs%20encoding/manifest.json"


def test_plugins_directory_collapses_home_to_tilde(monkeypatch) -> None:
    # The packaged-build case: the data folder is under the user's home, so the
    # reported path collapses the home prefix to ~ (the settings UI never shows
    # the absolute path that embeds the username).
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: Path.home() / ".sculptor")

    assert get_local_plugins_directory().path == "~/.sculptor/plugins"


def test_plugins_directory_kept_absolute_when_outside_home(monkeypatch) -> None:
    # A data folder outside $HOME (e.g. a from-source checkout elsewhere) has no
    # home prefix to collapse, so the full path is shown as-is.
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: Path("/opt/sculptor-data"))

    assert get_local_plugins_directory().path == "/opt/sculptor-data/plugins"
