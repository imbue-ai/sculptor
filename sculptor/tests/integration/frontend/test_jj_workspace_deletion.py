"""Integration coverage for deleting jj workspaces under the default bookmark deletion policy.

Under `delete_if_safe`, deleting a jj workspace forgets each of its bookmarks that
is safe to lose, such as one pushed to `origin` at the same commit, and keeps the
others, as `git branch -d` keeps an unmerged branch. Either way jj forgets the
workspace and Sculptor removes its directory. See
`sculptor.testing.jj_sculptor_instance` for the setup.
"""

from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.workspace_sidebar import get_workspace_sidebar
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_sculptor_instance import bash_step
from sculptor.testing.jj_sculptor_instance import colocate_base_repo_with_origin
from sculptor.testing.jj_sculptor_instance import create_jj_workspace
from sculptor.testing.jj_sculptor_instance import find_jj_workspace_root
from sculptor.testing.jj_sculptor_instance import get_active_project_id
from sculptor.testing.jj_sculptor_instance import list_jj_workspace_names
from sculptor.testing.jj_sculptor_instance import list_local_bookmarks
from sculptor.testing.jj_sculptor_instance import multi_step_prompt
from sculptor.testing.jj_sculptor_instance import open_new_agent_in_workspace
from sculptor.testing.jj_sculptor_instance import set_use_jj_for_new_workspaces
from sculptor.testing.jj_sculptor_instance import use_jj_binary
from sculptor.testing.jj_sculptor_instance import write_file_step
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_PUSHED_BOOKMARK = "jj-pushed-work"
_LOCAL_BOOKMARK = "jj-local-work"
_REMOVAL_TIMEOUT_MS = 30_000


def _wait_for_removal(page: Page, path: Path) -> None:
    """Wait for the background teardown of a deleted workspace, which the UI does not show, to remove its directory."""
    for _ in range(_REMOVAL_TIMEOUT_MS // 100):
        if not path.exists():
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"Sculptor did not remove the jj workspace at {path}")


def _describe_prompt(jj: str, file_name: str) -> str:
    return multi_step_prompt(
        [write_file_step(file_name, f"{file_name}\n"), bash_step(f"{jj} describe -m 'Add {file_name}'")]
    )


@user_story("to delete my jj workspaces and keep only the bookmarks whose work is not safe elsewhere")
def test_deleting_jj_workspaces_forgets_their_pushed_bookmarks_and_keeps_unpushed_ones(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    repo_path = colocate_base_repo_with_origin(sculptor_instance_factory_, jj_binary, tmp_path / "origin.git")
    jj = f"'{jj_binary.path}'"

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        project_id = get_active_project_id(page)
        set_use_jj_for_new_workspaces(page, project_id, True)
        workspace_roots: list[Path] = []
        workspace_ids: list[str] = []
        for bookmark in (_LOCAL_BOOKMARK, _PUSHED_BOOKMARK):
            workspace_id = create_jj_workspace(page, project_id, bookmark)
            task_page = open_new_agent_in_workspace(page, workspace_id)
            chat_panel = task_page.get_chat_panel()
            send_chat_message(chat_panel=chat_panel, message=_describe_prompt(jj, f"{bookmark}.md"))
            wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)
            expect(task_page.get_jj_identity_pill()).to_have_attribute("aria-label", f"Copy bookmark {bookmark}")
            workspace_ids.append(workspace_id)
            workspace_roots.append(find_jj_workspace_root(jj_binary, repo_path, workspace_id))

        # The last workspace's agent pushes its bookmark, so it tracks `origin` at the same commit.
        send_chat_message(
            chat_panel=chat_panel, message=multi_step_prompt([bash_step(f"{jj} git push -b {_PUSHED_BOOKMARK}")])
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)
        assert {_PUSHED_BOOKMARK, _LOCAL_BOOKMARK} <= set(list_local_bookmarks(jj_binary, repo_path))

        sidebar = get_workspace_sidebar(page)
        for bookmark in (_PUSHED_BOOKMARK, _LOCAL_BOOKMARK):
            sidebar.delete_workspace_via_context_menu(sidebar.get_workspace_row_by_name(bookmark))
        expect(sidebar.get_workspace_rows()).to_have_count(0)

        for workspace_root in workspace_roots:
            _wait_for_removal(page, workspace_root)
        remaining_workspaces = list_jj_workspace_names(jj_binary, repo_path)
        assert not set(workspace_ids) & set(remaining_workspaces), f"jj still lists {remaining_workspaces}"
        remaining_bookmarks = list_local_bookmarks(jj_binary, repo_path)
        assert _LOCAL_BOOKMARK in remaining_bookmarks, f"the unpushed bookmark is gone: {remaining_bookmarks}"
        assert _PUSHED_BOOKMARK not in remaining_bookmarks, f"the pushed bookmark is kept: {remaining_bookmarks}"
