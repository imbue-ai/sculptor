"""Integration coverage for a jj workspace staying a jj workspace after its repository stops creating them.

Turning off "Use jj for new workspaces" changes only what new workspaces are: an
existing jj workspace keeps its kind, its bookmark and a working jj for its agents,
before and after Sculptor restarts. See `sculptor.testing.jj_sculptor_instance` for
the setup.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.new_workspace_dialog import PlaywrightNewWorkspaceDialog
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_sculptor_instance import bash_step
from sculptor.testing.jj_sculptor_instance import colocate_base_repo_with_origin
from sculptor.testing.jj_sculptor_instance import multi_step_prompt
from sculptor.testing.jj_sculptor_instance import open_jj_workspace_agent
from sculptor.testing.jj_sculptor_instance import use_jj_binary
from sculptor.testing.jj_sculptor_instance import write_file_step
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import navigate_to_workspace
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BOOKMARK = "jj-sticky"
_GIT_WORKSPACE_NAME = "git after jj is off"


def _describe_another_change_prompt(jj: str, file_name: str) -> str:
    return multi_step_prompt(
        [
            bash_step(f"{jj} new"),
            write_file_step(file_name, f"{file_name}\n"),
            bash_step(f"{jj} describe -m 'Add {file_name}'"),
        ]
    )


@user_story("to keep using a jj workspace after turning jj off for new workspaces in its repository")
def test_a_jj_workspace_keeps_working_after_its_repository_stops_creating_jj_workspaces(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_base_repo_with_origin(sculptor_instance_factory_, jj_binary, tmp_path / "origin.git")
    jj = f"'{jj_binary.path}'"

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        task_page, _ = open_jj_workspace_agent(page, _BOOKMARK)
        chat_panel = task_page.get_chat_panel()
        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [write_file_step("notes.md", "first notes\n"), bash_step(f"{jj} describe -m 'Add notes'")]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)
        expect(task_page.get_jj_identity_pill()).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")

        repos_settings = navigate_to_settings_page(page=page).click_on_repositories()
        repos_settings.expand_repo_config()
        use_jj_switch = repos_settings.get_use_jj_for_new_workspaces_switch()
        expect(use_jj_switch).to_be_checked()
        use_jj_switch.click()
        expect(use_jj_switch).not_to_be_checked()

        navigate_to_workspace(page, _BOOKMARK)
        expect(task_page.get_mode_badge()).to_have_text("jj")
        expect(task_page.get_jj_identity_pill()).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")
        send_chat_message(chat_panel=chat_panel, message=_describe_another_change_prompt(jj, "more.md"))
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)
        expect(task_page.get_jj_unbookmarked_marker()).to_have_text("↑1")

        # A new workspace in the same repository is a git worktree again.
        dialog = PlaywrightNewWorkspaceDialog(page)
        dialog.open_via_shortcut()
        expect(dialog.get_branch_name_input()).to_have_attribute("placeholder", "Branch name (required)")
        git_task_page = dialog.create_and_wait_for_chat_panel(workspace_name=_GIT_WORKSPACE_NAME)
        expect(git_task_page.get_branch_name_element()).to_be_visible()
        expect(git_task_page.get_jj_identity_pill()).to_have_count(0)
        expect(git_task_page.get_mode_badge()).to_have_count(0)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        navigate_to_workspace(page, _BOOKMARK)
        task_page = PlaywrightTaskPage(page=page)
        expect(task_page.get_mode_badge()).to_have_text("jj")
        expect(task_page.get_jj_identity_pill()).to_have_attribute(
            "aria-label", f"Copy bookmark {_BOOKMARK}", timeout=60_000
        )
        expect(task_page.get_jj_unbookmarked_marker()).to_have_text("↑1")
        chat_panel = task_page.get_chat_panel()
        send_chat_message(chat_panel=chat_panel, message=_describe_another_change_prompt(jj, "after-restart.md"))
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6, timeout=60_000)
        expect(task_page.get_jj_unbookmarked_marker()).to_have_text("↑2")
