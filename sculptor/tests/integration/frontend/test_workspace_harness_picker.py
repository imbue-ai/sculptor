"""Workspace harness picker.

Drives the harness selector in the Add Workspace form. The picker is
gated behind the experimental multi-harness flag (off by default), so the
flag-on tests enable it first; verifies the picker is visible, defaults to
Claude, lets the user choose ``pi (experimental)``, and persists the selection
on the created workspace (visible as the harness badge on the recent-workspaces
row). The flag-off test asserts the picker is hidden and creation defaults to
Claude.
"""

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.user_config import disable_multi_harness
from sculptor.testing.elements.user_config import enable_multi_harness
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.playwright_utils import navigate_to_home_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the harness picker default to Claude on the Add Workspace form")
def test_harness_picker_visible_with_claude_default(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    enable_multi_harness(page)
    navigate_to_add_workspace_page(page)
    picker = page.get_by_test_id(ElementIDs.HARNESS_SELECTOR)
    expect(picker).to_be_visible()
    expect(picker).to_contain_text("Claude")


@user_story("to switch the harness to pi (experimental) before creating a workspace")
def test_harness_picker_selects_pi(
    sculptor_instance_: SculptorInstance,
) -> None:
    page = sculptor_instance_.page

    enable_multi_harness(page)
    navigate_to_add_workspace_page(page)
    picker = page.get_by_test_id(ElementIDs.HARNESS_SELECTOR)
    picker.click()
    page.get_by_test_id(ElementIDs.HARNESS_OPTION_PI).click()
    expect(picker).to_contain_text("pi (experimental)")


@user_story("to not see the harness picker, and get a Claude workspace, when multi-harness is disabled")
def test_harness_picker_hidden_and_defaults_to_claude_when_flag_off(
    sculptor_instance_: SculptorInstance,
) -> None:
    """With the multi-harness flag off (the default), the picker is absent and a
    new workspace is created as Claude — indistinguishable from pre-multi-harness."""
    page = sculptor_instance_.page

    # `enable_multi_harness` is sticky on the shared test instance and is set by
    # any sibling that creates a non-Claude workspace (it runs inside
    # `start_task_and_wait_for_ready` whenever a harness is selected). Reset it
    # defensively so this flag-off assertion does not depend on test ordering.
    disable_multi_harness(page)

    navigate_to_add_workspace_page(page)
    expect(page.get_by_test_id(ElementIDs.HARNESS_SELECTOR)).to_have_count(0)

    # `harness=None` means the helper neither enables the flag nor drives the
    # picker, so this exercises the default (no-picker) creation path.
    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Default Harness Workspace",
        model_name=None,
    )

    # The harness badge is hidden while the flag is off; enable it to reveal the
    # badge and assert the persisted harness is Claude.
    enable_multi_harness(page)
    navigate_to_home_page(page)
    workspace_row = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).filter(has_text="Default Harness Workspace")
    expect(workspace_row).to_be_visible(timeout=10_000)
    badge = workspace_row.get_by_test_id(ElementIDs.WORKSPACE_ROW_HARNESS_BADGE)
    expect(badge).to_be_visible()
    expect(badge).to_have_attribute("data-harness", HarnessName.CLAUDE.value)


@user_story("to see the pi harness selection persist on the workspace row after creation")
def test_pi_workspace_persists_and_renders_badge(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Creating a workspace with pi selected must persist `harness=pi` on the
    workspace row so the recent-workspaces list reflects the choice."""
    # FakePi binary is required because the backend's task-creation route
    # builds a PiAgentConfig once `harness=pi` is persisted; the agent will try
    # to spawn `pi --mode rpc ...` immediately.
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page

    start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi Picker Workspace",
        model_name=None,
        harness=HarnessName.PI,
    )

    navigate_to_home_page(page)
    workspace_row = page.get_by_test_id(ElementIDs.WORKSPACE_ROW).filter(has_text="Pi Picker Workspace")
    expect(workspace_row).to_be_visible(timeout=10_000)
    badge = workspace_row.get_by_test_id(ElementIDs.WORKSPACE_ROW_HARNESS_BADGE)
    expect(badge).to_be_visible()
    expect(badge).to_have_attribute("data-harness", HarnessName.PI.value)
    expect(badge).to_contain_text("pi (experimental)")
