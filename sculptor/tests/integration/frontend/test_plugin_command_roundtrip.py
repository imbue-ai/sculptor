"""Integration test for the `sculpt plugin` command round-trip against a live renderer.

This is the first e2e coverage of the plugin *command bridge*: a POST to the
per-workspace ``plugins/command`` endpoint publishes a ``PluginCommandUiAction``
over the per-user stream WebSocket to the connected renderer, which runs the op
through its ``PluginManager`` and POSTs a ``PluginCommandResult`` back, which the
endpoint returns. The backend endpoints and ``PluginManager`` are covered by unit
tests; this proves the whole loop works with a real renderer.

Single window only: a live renderer here is one Playwright page whose
``useUnifiedStream`` opened a stream WS (browser launch mode — the factory
instance is browser-based). Multi-renderer broadcast fan-out is intentionally
deferred (see SCU-1652).
"""

import base64
import json
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

from sculptor.primitives.ids import WorkspaceID
from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.resources import _default_sculptor_folder_populator
from sculptor.testing.resources import custom_sculptor_folder_populator
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

# A minimal valid plugin: a default-exported activate that contributes nothing.
# Reaching "loaded" proves the served bundle was fetched, imported, and activated.
_PROBE_MANIFEST: dict[str, object] = {
    "id": "probe",
    "name": "Probe",
    "version": "0.1.0",
    "entry": "main.js",
    "sdkVersion": "^1.0.0",
}
_PROBE_JS = "export default function activate(api) {}\n"

# How long to wait for the renderer's stream to connect and answer a command
# before giving up — the page is still booting when the test starts.
_RENDERER_READY_ATTEMPTS = 40
_RENDERER_POLL_INTERVAL_MS = 500


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode("ascii")


def _agent_loading_populator(folder_path: Path) -> None:
    """Seed the per-test config with agent plugin loading enabled.

    ``allow_agent_plugin_loading`` is off by default (turning it on lets a
    workspace run frontend code in the UI), and write ops like ``load`` are gated
    on it, so the test must opt in. ``enable_frontend_plugins`` is already on by
    default, so only this flag needs seeding.
    """
    _default_sculptor_folder_populator(folder_path)
    config_path = folder_path / "internal" / "config.toml"
    config = load_config(config_path).model_copy(update={"allow_agent_plugin_loading": True})
    save_config(config, config_path)


def _post_json(instance: SculptorInstance, path: str, body: dict[str, object]) -> dict:
    """POST JSON to the backend from the page's context (carries the session), returning the parsed body."""
    base_url = instance.backend_api_url.rstrip("/")
    response = instance.page.request.post(f"{base_url}{path}", data=body)
    assert response.ok, f"POST {path} -> {response.status}: {response.text()}"
    return response.json()


def _wait_for_renderer(instance: SculptorInstance, workspace_id: str) -> None:
    """Block until the renderer's stream is connected and answers a command.

    A read-only ``list`` returns one reply per connected renderer; polling it
    until it's non-empty confirms the exact precondition a write command needs —
    a subscriber that receives the broadcast and replies over the bridge.

    The page is still booting when the test starts, so a transient request error
    (the backend not yet accepting connections) or an as-yet-empty reply is
    treated as "not ready" and retried, not a failure.
    """
    url = f"{instance.backend_api_url.rstrip('/')}/api/v1/workspaces/{workspace_id}/plugins/command"
    for _ in range(_RENDERER_READY_ATTEMPTS):
        try:
            response = instance.page.request.post(url, data={"op": "list"})
            if response.ok and response.json().get("results"):
                return
        except PlaywrightError:
            pass
        instance.page.wait_for_timeout(_RENDERER_POLL_INTERVAL_MS)
    raise AssertionError("renderer stream never connected / responded to a plugin command")


@custom_sculptor_folder_populator.with_args(_agent_loading_populator)
def test_plugin_command_load_reaches_the_live_renderer(sculptor_instance_factory_: SculptorInstanceFactory) -> None:
    """`plugins/command` op=load fans out to the renderer, which loads a served plugin and replies.

    Mirrors the `sculpt plugin load <dir>` flow: install a packaged plugin into
    the dev tree, then load it by its served manifest URL. Asserts the endpoint
    returns the renderer's reply (real renderer id, ok, the plugin loaded from
    the dev origin) and that the renderer's own Settings -> Plugins list shows it.
    """
    with sculptor_instance_factory_.spawn_instance() as instance:
        # A synthetic workspace id: the desktop renderer streams all scopes, so it
        # receives the command regardless, and the install just nests dev files
        # under it.
        workspace_id = str(WorkspaceID())
        _wait_for_renderer(instance, workspace_id)

        install = _post_json(
            instance,
            f"/api/v1/workspaces/{workspace_id}/plugins/install",
            {
                "pluginId": "probe",
                "files": [
                    {"path": "manifest.json", "contentBase64": _b64(json.dumps(_PROBE_MANIFEST))},
                    {"path": "main.js", "contentBase64": _b64(_PROBE_JS)},
                ],
            },
        )
        manifest_url = install["manifestUrl"]
        assert manifest_url == f"/plugins/local/dev/{workspace_id}/probe/manifest.json"

        loaded = _post_json(
            instance,
            f"/api/v1/workspaces/{workspace_id}/plugins/command",
            {"op": "load", "source": manifest_url},
        )
        results = loaded["results"]
        assert len(results) == 1, f"expected one renderer reply, got {results}"
        result = results[0]
        assert result["ok"] is True, result
        assert result["renderer"]["rendererId"], result["renderer"]
        assert result["renderer"]["environment"] == "browser"
        assert result["plugins"], f"expected the loaded plugin in the reply, got {result}"
        plugin = result["plugins"][0]
        assert plugin["pluginId"] == "probe", plugin
        assert plugin["status"] == "loaded", plugin
        assert plugin["origin"] == "dev", plugin

        # The renderer's own Settings -> Plugins list reflects the load reactively
        # (clicking the gear routes via React Router, keeping the WS alive).
        settings_page = navigate_to_settings_page(page=instance.page)
        plugins = settings_page.click_on_plugins()
        plugins.expect_loaded(plugin["source"], name="Probe", version="0.1.0")
