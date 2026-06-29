"""Tests for the `sculpt plugin` command/install/remove endpoints.

The end-to-end flow (a real renderer loading a served plugin) is covered by the
frontend integration tests; here we pin down the branches worth guarding without
a live UI: the agent-loading switch, plugin-id and path-traversal validation,
dev-vs-persist placement, and the no-window command path.

Endpoint functions are called directly (not over HTTP) with ``get_sculptor_folder``
and ``get_user_config_instance`` monkeypatched, mirroring ``app_local_plugins_test``.
"""

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import sculptor.web.app as app_module
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.app import post_plugin_command
from sculptor.web.app import post_plugin_install
from sculptor.web.data_types import InstallPluginRequest
from sculptor.web.data_types import PluginCommandRequest
from sculptor.web.data_types import PluginFile


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode("ascii")


def _allow(monkeypatch, allowed: bool) -> None:
    monkeypatch.setattr(
        app_module, "get_user_config_instance", lambda: SimpleNamespace(allow_agent_plugin_loading=allowed)
    )


def _manifest_files() -> list[PluginFile]:
    return [
        PluginFile(path="manifest.json", content_base64=_b64('{"id": "demo"}')),
        PluginFile(path="main.js", content_base64=_b64("export default () => {};")),
    ]


def test_install_writes_dev_tree_nested_by_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)
    _allow(monkeypatch, True)
    workspace_id = str(WorkspaceID())

    response = post_plugin_install(workspace_id, InstallPluginRequest(plugin_id="demo", files=_manifest_files()))

    assert response.manifest_url == f"/plugins/local/dev/{workspace_id}/demo/manifest.json"
    written = tmp_path / "plugins" / "dev" / workspace_id / "demo" / "manifest.json"
    assert written.read_text() == '{"id": "demo"}'


def test_install_persist_writes_top_level(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)
    _allow(monkeypatch, True)

    response = post_plugin_install(
        str(WorkspaceID()), InstallPluginRequest(plugin_id="demo", files=_manifest_files(), persist=True)
    )

    assert response.manifest_url == "/plugins/local/demo/manifest.json"
    assert (tmp_path / "plugins" / "demo" / "main.js").is_file()


def test_install_rewrites_existing_dir(tmp_path: Path, monkeypatch) -> None:
    # A reload re-installs; stale files from a previous package must not linger.
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)
    _allow(monkeypatch, True)
    workspace_id = str(WorkspaceID())

    post_plugin_install(
        workspace_id,
        InstallPluginRequest(
            plugin_id="demo",
            files=[
                PluginFile(path="manifest.json", content_base64=_b64("{}")),
                PluginFile(path="old.js", content_base64=_b64("x")),
            ],
        ),
    )
    post_plugin_install(workspace_id, InstallPluginRequest(plugin_id="demo", files=_manifest_files()))

    plugin_dir = tmp_path / "plugins" / "dev" / workspace_id / "demo"
    assert (plugin_dir / "main.js").is_file()
    assert not (plugin_dir / "old.js").exists()


def test_install_blocked_when_switch_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)
    _allow(monkeypatch, False)

    with pytest.raises(HTTPException) as excinfo:
        post_plugin_install(str(WorkspaceID()), InstallPluginRequest(plugin_id="demo", files=_manifest_files()))
    assert excinfo.value.status_code == 403


def test_install_requires_a_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)
    _allow(monkeypatch, True)

    with pytest.raises(HTTPException) as excinfo:
        post_plugin_install(
            str(WorkspaceID()),
            InstallPluginRequest(plugin_id="demo", files=[PluginFile(path="main.js", content_base64=_b64("x"))]),
        )
    assert excinfo.value.status_code == 400


def test_install_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_sculptor_folder", lambda: tmp_path)
    _allow(monkeypatch, True)
    files = [
        PluginFile(path="manifest.json", content_base64=_b64("{}")),
        PluginFile(path="../../escape.js", content_base64=_b64("pwn")),
    ]

    with pytest.raises(HTTPException) as excinfo:
        post_plugin_install(str(WorkspaceID()), InstallPluginRequest(plugin_id="demo", files=files))
    assert excinfo.value.status_code == 400
    assert not (tmp_path / "escape.js").exists()


@pytest.mark.parametrize("bad_id", ["", "a/b", "a\\b", "..", ".", "dev"])
def test_validate_plugin_id_rejects_unsafe(bad_id: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        app_module._validate_plugin_id(bad_id)
    assert excinfo.value.status_code == 400


def test_validate_plugin_id_accepts_a_normal_name() -> None:
    assert app_module._validate_plugin_id("linear-issue") == "linear-issue"


def test_command_write_op_blocked_when_switch_off(monkeypatch) -> None:
    _allow(monkeypatch, False)
    with pytest.raises(HTTPException) as excinfo:
        post_plugin_command(
            str(WorkspaceID()), PluginCommandRequest(op="load", source="/plugins/local/demo/manifest.json")
        )
    assert excinfo.value.status_code == 403


def test_command_inspect_is_ungated_and_returns_empty_without_renderers(monkeypatch) -> None:
    # inspect is read-only: it must NOT require the switch, and with no connected
    # renderer it returns an empty result list (the CLI renders "no window
    # responded"). Shrink the wait so the no-window path is fast.
    _allow(monkeypatch, False)
    monkeypatch.setattr(app_module, "_PLUGIN_COMMAND_TIMEOUT_SECONDS", 0.05)

    response = post_plugin_command(str(WorkspaceID()), PluginCommandRequest(op="inspect", plugin_id="demo"))

    assert response.results == []
    assert response.correlation_id
