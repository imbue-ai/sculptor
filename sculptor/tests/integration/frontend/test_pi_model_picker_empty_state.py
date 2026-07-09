"""Integration coverage for the pi model-picker empty state + send-slot config CTA.

When a pi agent has no models to offer (no authenticated providers), the picker is
shown disabled with the verbatim "No models available" copy — never the Claude
fallback list — and the Send button is replaced by a "Go to harness configuration"
button that routes to Settings -> Pi. FakePi reports an empty catalog
(FAKE_PI_CATALOG="[]"); auth.json is isolated via PI_CODING_AGENT_DIR.
"""

import re
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_NO_MODELS_COPY = "No models available"


@user_story("to be routed to configure a provider when a pi agent has no authenticated providers")
def test_pi_picker_empty_state_shows_config_cta(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    agent_dir = tmp_path / "pi-agent"
    agent_dir.mkdir()  # no auth.json -> nothing imported
    sculptor_instance_factory_.update_environment(
        PI_CODING_AGENT_DIR=str(agent_dir),
        FAKE_PI_CATALOG="[]",  # pi reports no models
    )

    with sculptor_instance_factory_.spawn_instance() as instance:
        install_fake_pi_binary(instance.fake_bin_dir)
        page = instance.page
        task_page = start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Pi Empty Picker",
            model_name=None,
            agent_type="pi",
        )
        chat_panel = task_page.get_chat_panel()

        # The picker is disabled with the verbatim copy; the Claude fallback list does not show.
        empty_state = chat_panel.get_picker_empty_state()
        expect(empty_state).to_be_visible(timeout=30_000)
        expect(empty_state).to_contain_text(_NO_MODELS_COPY)
        expect(chat_panel.get_model_selector()).to_have_count(0)

        # Send is replaced by a "Go to harness configuration" CTA that routes to Settings -> Pi.
        config_cta = chat_panel.get_harness_config_cta()
        expect(config_cta).to_be_visible()
        config_cta.click()
        expect(page).to_have_url(re.compile("section=PI"))
