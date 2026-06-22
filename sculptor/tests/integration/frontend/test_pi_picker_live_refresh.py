"""End-to-end coverage for the live picker refresh without restart (REQ-FILTER-3).

A running pi agent starts with only anthropic authenticated, so its picker hides the
google-provider model. Adding google credentials (paste-key) fires the broadcast,
which re-fetches + re-filters the running agent's catalog — so the google model
appears in the same agent's picker with no restart. auth.json is isolated via
PI_CODING_AGENT_DIR.
"""

import json
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# Two anthropic models so the picker keeps >1 option (the switcher disables itself
# with a single model) while google is initially filtered out for lack of credentials.
_MULTI_PROVIDER_CATALOG = json.dumps(
    [
        {"id": "fake-anthropic-x", "name": "FakePi Anthropic X", "provider": "anthropic"},
        {"id": "fake-anthropic-y", "name": "FakePi Anthropic Y", "provider": "anthropic"},
        {"id": "fake-google-x", "name": "FakePi Google X", "provider": "google"},
    ]
)


@user_story("to see a running pi agent's picker pick up newly-authenticated providers without a restart")
def test_pi_picker_refreshes_live_after_paste_key(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()
    (agent_dir / "auth.json").write_text(json.dumps({"anthropic": {"type": "api_key", "key": "x"}}), encoding="utf-8")
    sculptor_instance_factory_.update_environment(
        PI_CODING_AGENT_DIR=str(agent_dir),
        FAKE_PI_CATALOG=_MULTI_PROVIDER_CATALOG,
    )

    with sculptor_instance_factory_.spawn_instance() as instance:
        install_fake_pi_binary(instance.fake_bin_dir)
        page = instance.page
        # A first turn starts the agent (its message loop must be running to apply
        # the between-turns refresh the broadcast triggers).
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Picker Live Refresh",
            model_name=None,
            agent_type="pi",
            prompt='fake_pi:emit_text `{"text": "ready"}`',
        )
        chat_panel = task_page.get_chat_panel()

        # Initially only anthropic is authenticated, so the google model is hidden.
        chat_panel.get_model_selector().click()
        expect(chat_panel.get_model_option("fake-anthropic-x")).to_be_visible()
        expect(chat_panel.get_model_option("fake-google-x")).to_have_count(0)
        page.keyboard.press("Escape")

        # Authenticate google by writing its credential (the paste-key endpoint that
        # the Settings form drives); the same broadcast fires as in production.
        base_url = page.url.split("#")[0].rstrip("/")
        response = page.request.post(
            f"{base_url}/api/v1/pi/providers/paste-key",
            data={"providerId": "google", "keyValue": "sk-google-test"},
        )
        assert response.ok, f"paste-key failed: {response.status} {response.text()}"

        # Without restarting the agent, its picker now includes the google model —
        # the broadcast re-fetched and re-filtered the running agent's catalog live.
        chat_panel.get_model_selector().click()
        expect(chat_panel.get_model_option("fake-google-x")).to_be_visible(timeout=30_000)
        expect(chat_panel.get_model_option("fake-anthropic-x")).to_be_visible()
