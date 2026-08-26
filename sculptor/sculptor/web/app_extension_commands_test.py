"""Tests for the `sculpt extension` command/install/remove endpoints.

The end-to-end flow (a real renderer loading a served extension) is covered by the
frontend integration tests; here we pin down the branches worth guarding without
a live UI: the agent-loading switch, extension-id and path-traversal validation,
dev-vs-persist placement, and the no-window command path.

Endpoint functions are called directly (not over HTTP) with ``get_extensions_directory``
and ``get_user_config_instance`` monkeypatched, mirroring ``app_local_extensions_test``.
"""

import base64
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

import sculptor.web.app as app_module
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.app import post_extension_command
from sculptor.web.app import post_extension_command_result
from sculptor.web.app import post_extension_install
from sculptor.web.data_types import ExtensionCommandRequest
from sculptor.web.data_types import ExtensionCommandResult
from sculptor.web.data_types import ExtensionFile
from sculptor.web.data_types import InstallExtensionRequest
from sculptor.web.data_types import RendererIdentity


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode("ascii")


def _allow(monkeypatch, allowed: bool) -> None:
    monkeypatch.setattr(
        app_module, "get_user_config_instance", lambda: SimpleNamespace(allow_agent_extension_loading=allowed)
    )


def _manifest_files() -> list[ExtensionFile]:
    return [
        ExtensionFile(path="manifest.json", content_base64=_b64('{"id": "demo"}')),
        ExtensionFile(path="main.js", content_base64=_b64("export default () => {};")),
    ]


def test_install_writes_dev_tree_nested_by_workspace(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")
    _allow(monkeypatch, True)
    workspace_id = str(WorkspaceID())

    response = post_extension_install(
        workspace_id, InstallExtensionRequest(extension_id="demo", files=_manifest_files())
    )

    assert response.manifest_url == f"/extensions/local/dev/{workspace_id}/demo/manifest.json"
    written = tmp_path / "extensions" / "dev" / workspace_id / "demo" / "manifest.json"
    assert written.read_text() == '{"id": "demo"}'


def test_install_persist_writes_top_level(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")
    _allow(monkeypatch, True)

    response = post_extension_install(
        str(WorkspaceID()), InstallExtensionRequest(extension_id="demo", files=_manifest_files(), persist=True)
    )

    assert response.manifest_url == "/extensions/local/demo/manifest.json"
    assert (tmp_path / "extensions" / "demo" / "main.js").is_file()


def test_install_rewrites_existing_dir(tmp_path: Path, monkeypatch) -> None:
    # A reload re-installs; stale files from a previous package must not linger.
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")
    _allow(monkeypatch, True)
    workspace_id = str(WorkspaceID())

    post_extension_install(
        workspace_id,
        InstallExtensionRequest(
            extension_id="demo",
            files=[
                ExtensionFile(path="manifest.json", content_base64=_b64("{}")),
                ExtensionFile(path="old.js", content_base64=_b64("x")),
            ],
        ),
    )
    post_extension_install(workspace_id, InstallExtensionRequest(extension_id="demo", files=_manifest_files()))

    extension_dir = tmp_path / "extensions" / "dev" / workspace_id / "demo"
    assert (extension_dir / "main.js").is_file()
    assert not (extension_dir / "old.js").exists()


def test_install_blocked_when_switch_off(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")
    _allow(monkeypatch, False)

    with pytest.raises(HTTPException) as excinfo:
        post_extension_install(
            str(WorkspaceID()), InstallExtensionRequest(extension_id="demo", files=_manifest_files())
        )
    assert excinfo.value.status_code == 403


def test_install_requires_a_manifest(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")
    _allow(monkeypatch, True)

    with pytest.raises(HTTPException) as excinfo:
        post_extension_install(
            str(WorkspaceID()),
            InstallExtensionRequest(
                extension_id="demo", files=[ExtensionFile(path="main.js", content_base64=_b64("x"))]
            ),
        )
    assert excinfo.value.status_code == 400


def test_install_rejects_path_traversal(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(app_module, "get_extensions_directory", lambda: tmp_path / "extensions")
    _allow(monkeypatch, True)
    files = [
        ExtensionFile(path="manifest.json", content_base64=_b64("{}")),
        ExtensionFile(path="../../escape.js", content_base64=_b64("pwn")),
    ]

    with pytest.raises(HTTPException) as excinfo:
        post_extension_install(str(WorkspaceID()), InstallExtensionRequest(extension_id="demo", files=files))
    assert excinfo.value.status_code == 400
    assert not (tmp_path / "escape.js").exists()


@pytest.mark.parametrize("bad_id", ["", "a/b", "a\\b", "..", ".", "dev"])
def test_validate_extension_id_rejects_unsafe(bad_id: str) -> None:
    with pytest.raises(HTTPException) as excinfo:
        app_module._validate_extension_id(bad_id)
    assert excinfo.value.status_code == 400


def test_validate_extension_id_accepts_a_normal_name() -> None:
    assert app_module._validate_extension_id("linear-issue") == "linear-issue"


def test_command_write_op_blocked_when_switch_off(monkeypatch) -> None:
    _allow(monkeypatch, False)
    with pytest.raises(HTTPException) as excinfo:
        post_extension_command(
            str(WorkspaceID()), ExtensionCommandRequest(op="load", source="/extensions/local/demo/manifest.json")
        )
    assert excinfo.value.status_code == 403


def test_command_inspect_is_ungated_and_returns_empty_without_renderers(monkeypatch) -> None:
    # inspect is read-only: it must NOT require the switch, and with no connected
    # renderer it returns an empty result list (the CLI renders "no window
    # responded"). Shrink the wait so the no-window path is fast.
    _allow(monkeypatch, False)
    monkeypatch.setattr(app_module, "_EXTENSION_COMMAND_TIMEOUT_SECONDS", 0.05)

    response = post_extension_command(str(WorkspaceID()), ExtensionCommandRequest(op="inspect", extension_id="demo"))

    assert response.results == []
    assert response.correlation_id


def _renderer_result(correlation_id: str) -> ExtensionCommandResult:
    return ExtensionCommandResult(
        correlation_id=correlation_id,
        renderer=RendererIdentity(renderer_id="r1", environment="electron", origin="http://localhost"),
        op="list",
        ok=True,
        extensions=[],
    )


def test_command_result_rejects_correlation_id_mismatch() -> None:
    # A reply whose body correlation_id disagrees with the path is rejected, so a
    # buggy client can't feed a result into the wrong waiting command.
    with pytest.raises(HTTPException) as excinfo:
        post_extension_command_result("path-id", _renderer_result("different-id"))
    assert excinfo.value.status_code == 400


def test_command_result_accepts_matching_correlation_id() -> None:
    # With no waiter registered it quietly succeeds (204) rather than erroring.
    response = post_extension_command_result("c1", _renderer_result("c1"))
    assert response.status_code == 204
