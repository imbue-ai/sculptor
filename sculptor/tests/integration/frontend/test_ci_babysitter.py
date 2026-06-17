"""Integration tests for the CI Babysitter feature.

Each test installs a fake ``glab`` CLI that returns a controlled MR
state (failed pipeline, merge conflict, merged, etc.) and asserts that
``CIBabysitterCoordinator`` reacts correctly: a "CI Babysitter" agent
tab is spawned, the configured prompt is delivered, the agent is
retired on merge, and pause prevents prompts.

The classifier's first-poll baseline behavior (architecture's "Risks
and Mitigations" section) requires PIPELINE_FAILED to fire only on a
*change* of pipeline id, not on the very first poll. Tests therefore
write an initial pipeline_id (the baseline) before starting the
workspace, wait for that baseline poll to land, and then bump the
pipeline_id to trigger an actionable transition. The bump-after-wait
pattern is encapsulated in `_bump_pipeline_id_after_baseline`.
"""

import stat
import textwrap
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.agent_tab import PlaywrightAgentTabBarElement
from sculptor.testing.elements.alpha_chat_view import get_alpha_chat_view
from sculptor.testing.elements.pr_popover import PlaywrightPrPopoverElement
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_MERGED_MODE_STABLE_WAIT_MS = 25_000
# Time to wait between baseline-recording poll and the next state-changing
# poll. The polling service uses a 10s minimum interval in tests; 12s is a
# safe lower bound that still keeps the test snappy.
_BASELINE_POLL_SETTLE_MS = 12_000

_FAKE_GITLAB_REMOTE = "https://gitlab.com/test-org/test-repo.git"

# Shared fake glab script driven by a `state_file` (mode) and a `pipeline_id_file`.
#   mode = failed   → MR is open with a failed pipeline of the given id.
#   mode = merged   → MR is merged.
#   mode = closed   → MR is closed without merging.
_FAKE_GLAB_STATE_SCRIPT = """\
#!/bin/bash
MODE=$(cat "{state_file}")
PIPELINE_ID=$(cat "{pipeline_id_file}")
case "$MODE" in
    failed)
        if [[ "$*" == *"mr list"* && "$*" == *"--merged"* ]]; then
            echo "[]"
        elif [[ "$*" == *"mr list"* && "$*" == *"--closed"* ]]; then
            echo "[]"
        elif [[ "$*" == *"mr list"* ]]; then
            echo '[{{"iid": 7, "title": "Test MR", "web_url": "https://gitlab.com/test/repo/-/merge_requests/7", "target_branch": "main", "has_conflicts": false}}]'
        elif [[ "$*" == *"mr view"* ]]; then
            echo "{{\\"iid\\": 7, \\"title\\": \\"Test MR\\", \\"web_url\\": \\"https://gitlab.com/test/repo/-/merge_requests/7\\", \\"target_branch\\": \\"main\\", \\"has_conflicts\\": false, \\"pipeline\\": {{\\"id\\": $PIPELINE_ID, \\"status\\": \\"failed\\", \\"web_url\\": \\"https://gitlab.com/test/repo/-/pipelines/$PIPELINE_ID\\", \\"updated_at\\": \\"2026-01-01T00:00:00Z\\"}}}}"
        elif [[ "$*" == *"approvals"* ]]; then
            echo '{{"approved_by": []}}'
        elif [[ "$*" == *"discussions"* ]]; then
            echo '[]'
        else
            exit 1
        fi
        ;;
    merged)
        if [[ "$*" == *"mr list"* && "$*" == *"--merged"* ]]; then
            echo '[{{"iid": 7, "title": "Test MR", "web_url": "https://gitlab.com/test/repo/-/merge_requests/7", "target_branch": "main"}}]'
        else
            echo "[]"
        fi
        ;;
    *)
        echo "[]"
        ;;
esac
"""


def _install_fake_glab(fake_bin_dir: Path, script: str) -> None:
    script_path = fake_bin_dir / "glab"
    script_path.write_text(textwrap.dedent(script))
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)


def _install_state_driven_glab(instance: SculptorInstance, state_file: Path, pipeline_id_file: Path) -> None:
    _install_fake_glab(
        instance.fake_bin_dir,
        _FAKE_GLAB_STATE_SCRIPT.format(state_file=state_file, pipeline_id_file=pipeline_id_file),
    )


def _set_remote(instance: SculptorInstance, url: str) -> None:
    repo = instance.repo
    try:
        repo.repo.run_git(("remote", "remove", "origin"))
    except Exception:
        pass
    repo.repo.run_git(("remote", "add", "origin", url))
    full_spa_reload(instance.page)


_CONFIG_API_TIMEOUT_MS = 30_000


def _enable_babysitter(instance: SculptorInstance) -> None:
    """Enable the CI Babysitter via the user-config API.

    Also sets default_llm to FAKE_CLAUDE so the coordinator-spawned babysitter
    agent uses the deterministic test model. The babysitter normally inherits
    its model from the workspace's most recent agent, but the polling cycle
    can fire before the parent agent's first chat message is committed, so
    we set the user-config fallback explicitly here.
    """
    base_url = instance.backend_api_url.rstrip("/")
    response = instance.page.request.get(f"{base_url}/api/v1/config", timeout=_CONFIG_API_TIMEOUT_MS)
    assert response.ok, f"GET /api/v1/config failed: {response.status}"
    config = response.json()
    babysitter = dict(config.get("ciBabysitter") or {})
    babysitter["enabled"] = True
    config["ciBabysitter"] = babysitter
    config["defaultLlm"] = "FAKE_CLAUDE"
    put_response = instance.page.request.put(
        f"{base_url}/api/v1/config",
        data={"userConfig": config},
        timeout=_CONFIG_API_TIMEOUT_MS,
    )
    assert put_response.ok, f"PUT /api/v1/config failed: {put_response.status}"


_PIPELINE_PROMPT_FRAGMENT = "Investigate the failing pipeline for this MR"


def _bump_pipeline_id_after_baseline(page, pipeline_id_file: Path, new_id: str) -> None:
    """Wait for the baseline poll to land, then write a new pipeline id.

    The classifier records the first-seen `pipeline_id` as the baseline
    for a workspace. Tests must let that baseline poll happen before
    changing the id, or the new id is itself the baseline and no
    transition is observed.
    """
    page.wait_for_timeout(_BASELINE_POLL_SETTLE_MS)
    pipeline_id_file.write_text(new_id)


@user_story("to have Sculptor's CI Babysitter automatically investigate a failed pipeline")
def test_scenario_1_failed_pipeline_creates_babysitter(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """When CI fails on an MR opened from a workspace, the coordinator spawns
    a 'CI Babysitter' agent tab and delivers the configured prompt verbatim.
    """
    state_file = tmp_path / "glab_state"
    pipeline_id_file = tmp_path / "pipeline_id"
    state_file.write_text("failed")
    pipeline_id_file.write_text("100")

    _enable_babysitter(sculptor_instance_)
    _install_state_driven_glab(sculptor_instance_, state_file, pipeline_id_file)
    _set_remote(sculptor_instance_, _FAKE_GITLAB_REMOTE)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _bump_pipeline_id_after_baseline(sculptor_instance_.page, pipeline_id_file, "101")

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)

    babysitter_tab.first.click()
    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    pipeline_prompt_messages = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
    expect(pipeline_prompt_messages.first).to_be_visible()


@user_story("to retain babysitter history after the MR is merged, with no further automated prompts")
def test_scenario_7_merged_mr_retires_babysitter(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Once an MR is merged, the coordinator stops sending prompts but
    the babysitter task and its conversation history remain.
    """
    state_file = tmp_path / "glab_state"
    pipeline_id_file = tmp_path / "pipeline_id"
    state_file.write_text("failed")
    pipeline_id_file.write_text("100")

    _install_state_driven_glab(sculptor_instance_, state_file, pipeline_id_file)
    _set_remote(sculptor_instance_, _FAKE_GITLAB_REMOTE)
    _enable_babysitter(sculptor_instance_)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _bump_pipeline_id_after_baseline(sculptor_instance_.page, pipeline_id_file, "101")

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)
    babysitter_tab.first.click()

    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    pipeline_prompts = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
    expect(pipeline_prompts).to_have_count(1)

    state_file.write_text("merged")
    sculptor_instance_.page.wait_for_timeout(_MERGED_MODE_STABLE_WAIT_MS)
    expect(pipeline_prompts).to_have_count(1)

    expect(babysitter_tab.first).to_be_visible()


@user_story("to silence the CI Babysitter for an MR while still seeing the babysitter tab")
def test_scenario_4_pause_toggle_prevents_prompt(sculptor_instance_: SculptorInstance, tmp_path: Path) -> None:
    """Toggling pause in the PR popover stops the coordinator from sending
    further prompts to the babysitter for this MR. Unpausing resumes
    listening but does not retro-fire for the existing red state.
    """
    state_file = tmp_path / "glab_state"
    pipeline_id_file = tmp_path / "pipeline_id"
    state_file.write_text("failed")
    pipeline_id_file.write_text("100")

    _install_state_driven_glab(sculptor_instance_, state_file, pipeline_id_file)
    _set_remote(sculptor_instance_, _FAKE_GITLAB_REMOTE)
    _enable_babysitter(sculptor_instance_)

    start_task_and_wait_for_ready(sculptor_instance_.page, "say hello")
    _bump_pipeline_id_after_baseline(sculptor_instance_.page, pipeline_id_file, "101")

    agent_tabs = PlaywrightAgentTabBarElement(sculptor_instance_.page)
    babysitter_tab = agent_tabs.get_agent_tab_by_name("CI Babysitter")
    expect(babysitter_tab.first).to_be_visible(timeout=60_000)

    pr_popover = PlaywrightPrPopoverElement(sculptor_instance_.page)
    pr_chevron = pr_popover.get_chevron()
    expect(pr_chevron).to_be_visible(timeout=60_000)
    pr_chevron.click()

    pause_toggle = pr_popover.get_babysitter_pause_toggle()
    expect(pause_toggle).to_be_visible()
    pause_toggle.click()
    sculptor_instance_.page.keyboard.press("Escape")

    babysitter_tab.first.click()
    alpha_chat = get_alpha_chat_view(sculptor_instance_.page)
    pipeline_prompts = alpha_chat.get_messages().filter(has_text=_PIPELINE_PROMPT_FRAGMENT)
    expect(pipeline_prompts).to_have_count(1)

    pipeline_id_file.write_text("102")
    sculptor_instance_.page.wait_for_timeout(_MERGED_MODE_STABLE_WAIT_MS)
    expect(pipeline_prompts).to_have_count(1)
