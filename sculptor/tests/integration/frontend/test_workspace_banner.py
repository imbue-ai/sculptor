"""Integration tests for the redesigned workspace metadata banner.

Tests verify that the new banner components (diff summary, repo segment with
mode label, branch name) render correctly and respond to user interactions.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to see the diff summary after agent makes file changes")
def test_diff_summary_appears_on_file_changes(sculptor_instance_: SculptorInstance) -> None:
    """Diff summary should appear in the banner when the agent creates files."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:write_file `{"file_path": "test_file.py", "content": "print(\'hello\')"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    diff_summary = task_page.get_diff_summary()
    expect(diff_summary).to_be_visible()


@user_story("to see that clone mode does not show a mode badge")
def test_repo_segment_shows_mode_label(sculptor_instance_: SculptorInstance) -> None:
    """Clone mode should not display a mode badge in the workspace banner."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello!")

    mode_badge = task_page.get_mode_badge()
    expect(mode_badge).not_to_be_visible()


@user_story("to see the branch name in the workspace banner")
def test_branch_name_visible(sculptor_instance_: SculptorInstance) -> None:
    """Branch name should be visible in the workspace banner."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello!")

    task_page.get_branch_name_element()


@user_story("to see diff stats in the workspace banner after making changes")
def test_banner_shows_diff_stats(sculptor_instance_: SculptorInstance) -> None:
    """The workspace banner should show target-branch diff stats (+N -N files)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:write_file `{"file_path": "hello.py", "content": "print(\'hello\')"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    diff_summary = task_page.get_diff_summary()
    expect(diff_summary).to_be_visible()
    expect(diff_summary).to_contain_text("+")
    expect(diff_summary).to_contain_text("file")


@user_story("to click banner diff stats and be taken to the Changes tab with All scope")
def test_banner_click_navigates_to_changes_all(sculptor_instance_: SculptorInstance) -> None:
    """Clicking the diff stats in the banner should navigate to Changes tab
    with the All (vs-target-branch) scope selected."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:write_file `{"file_path": "hello.py", "content": "print(\'hello\')"}`',
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    diff_summary = task_page.get_diff_summary()
    expect(diff_summary).to_be_visible()
    diff_summary.click()

    changes_panel = task_page.get_changes_panel()
    expect(changes_panel).to_be_visible()

    scope_all = changes_panel.get_scope_all()
    expect(scope_all).to_have_attribute("data-state", "on")

    changes_tree = changes_panel.get_changes_tree()
    expect(changes_tree).to_be_visible()
    tree_rows = changes_tree.get_tree_rows()
    expect(tree_rows.filter(has_text="hello.py")).to_be_visible()
