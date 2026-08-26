"""Integration coverage for the authenticated-set model-picker filter.

FakePi's catalog spans two providers (anthropic + google); only anthropic is
authenticated (the harness sets ANTHROPIC_API_KEY and auth.json has anthropic, while
GEMINI_API_KEY is unset and auth.json has no google entry). So the picker must show
only the anthropic-provider model, not the google one — even though pi's catalog
lists both. auth.json is isolated via PI_CODING_AGENT_DIR.
"""

import json
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

# Two anthropic models so the (authenticated-only) picker keeps >1 option and stays
# enabled — the switcher disables itself with a single model — plus a google model
# that must be filtered out when google is not authenticated.
_MULTI_PROVIDER_CATALOG = json.dumps(
    [
        {"id": "fake-anthropic-x", "name": "FakePi Anthropic X", "provider": "anthropic"},
        {"id": "fake-anthropic-y", "name": "FakePi Anthropic Y", "provider": "anthropic"},
        {"id": "fake-google-x", "name": "FakePi Google X", "provider": "google"},
    ]
)


@user_story("to see only authenticated providers' models in the pi picker")
def test_pi_picker_shows_only_authenticated_providers(
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
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            workspace_name="Pi Picker Filter",
            model_name=None,
            agent_type="pi",
        )
        chat_panel = task_page.get_chat_panel()

        # The current (anthropic) model surfaces from the catalog probe.
        expect(chat_panel.get_model_selector()).to_contain_text("FakePi Anthropic X", timeout=30_000)

        chat_panel.get_model_selector().click()
        # The anthropic models (authenticated) appear; the google model (no
        # GEMINI_API_KEY, not in auth.json) is filtered out of the picker.
        expect(chat_panel.get_model_option("fake-anthropic-x")).to_be_visible()
        expect(chat_panel.get_model_option("fake-anthropic-y")).to_be_visible()
        expect(chat_panel.get_model_option("fake-google-x")).to_have_count(0)
