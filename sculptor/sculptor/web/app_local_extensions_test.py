"""Tests for the local-extensions endpoints: directory scan (`get_local_extensions`)
and the display-path report (`get_local_extensions_directory`).

The static serving of the files themselves (the `/extensions/local` mount) is
covered end-to-end by the frontend integration tests; here we only exercise the
directory-scan logic and the path formatting, the parts with branches worth
pinning down.
"""

from pathlib import Path

import sculptor.web.app as app_module
from sculptor.web.app import get_local_extensions
from sculptor.web.app import get_local_extensions_directory


def _write_extension(extensions_dir: Path, extension_id: str, *, with_manifest: bool = True) -> None:
    extension_dir = extensions_dir / extension_id
    extension_dir.mkdir(parents=True)
    if with_manifest:
        (extension_dir / "manifest.json").write_text('{"id": "' + extension_id + '"}')
        (extension_dir / "main.js").write_text("export default () => {};")


def test_lists_only_directories_with_a_manifest_sorted_by_name(tmp_path: Path, monkeypatch) -> None:
    extensions_dir = tmp_path / "extensions"
    # Out-of-order on purpose: the endpoint sorts for a stable row order.
    _write_extension(extensions_dir, "beta")
    _write_extension(extensions_dir, "alpha")
    # A directory without a manifest, and a stray file, must both be skipped.
    _write_extension(extensions_dir, "no-manifest", with_manifest=False)
    (extensions_dir / "stray.txt").write_text("not an extension")
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")

    result = get_local_extensions()

    assert [extension.id for extension in result] == ["alpha", "beta"]
    assert result[0].manifest_url == "/extensions/local/alpha/manifest.json"


def test_empty_when_extensions_dir_absent(tmp_path: Path, monkeypatch) -> None:
    # tmp_path has no `extensions/` subdirectory — a fresh install before the mount
    # has created it, or a user who never added an extension.
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")

    assert get_local_extensions() == []


def test_percent_encodes_directory_names_with_url_special_chars(tmp_path: Path, monkeypatch) -> None:
    # A space (and other URL-special chars) in an extension folder name must be
    # encoded, or the manifest URL the frontend fetches would be corrupted.
    extensions_dir = tmp_path / "extensions"
    _write_extension(extensions_dir, "needs encoding")
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")

    result = get_local_extensions()

    assert result[0].id == "needs encoding"
    assert result[0].manifest_url == "/extensions/local/needs%20encoding/manifest.json"


def test_extensions_directory_collapses_home_to_tilde(monkeypatch) -> None:
    # The packaged-build case: the data folder is under the user's home, so the
    # reported path collapses the home prefix to ~ (the settings UI never shows
    # the absolute path that embeds the username).
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: Path.home() / ".sculptor" / "extensions")

    assert get_local_extensions_directory().path == "~/.sculptor/extensions"


def test_extensions_directory_kept_absolute_when_outside_home(monkeypatch) -> None:
    # A data folder outside $HOME (e.g. a from-source checkout elsewhere) has no
    # home prefix to collapse, so the full path is shown as-is.
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: Path("/opt/sculptor-data/extensions"))

    assert get_local_extensions_directory().path == "/opt/sculptor-data/extensions"
