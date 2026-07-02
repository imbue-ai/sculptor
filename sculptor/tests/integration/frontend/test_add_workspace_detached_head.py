"""Regression test for the source-branch dropdown when the base repo is on a
detached HEAD.

``git branch`` (a porcelain command) prints a placeholder line for a detached
HEAD, e.g. ``(HEAD detached at origin/main)``. If that placeholder leaks into
the New Workspace *source* dropdown, a user can select it, and the verbose
string is then handed to ``git worktree add <path> <base_ref>`` as the base
ref — which git rejects, so workspace creation fails. The dropdown must list
only real local branches.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.add_workspace_page import PlaywrightAddWorkspacePage
from sculptor.testing.playwright_utils import navigate_to_add_workspace_page
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story


@user_story("to not see git's '(HEAD detached ...)' placeholder as a selectable source branch")
def test_detached_head_placeholder_not_listed_as_source_branch(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    """On a detached-HEAD base repo, the source dropdown lists real branches only.

    A dedicated factory instance is used so detaching HEAD does not leak into the
    shared instance's checkout (other tests assume it is on ``testing``). The repo
    keeps its real ``main`` and ``testing`` branches; only the working copy is
    detached before the backend enumerates branches.
    """
    # Detach HEAD before the backend starts so get_repo_info enumerates branches
    # against a detached working copy — the exact state that produces the
    # placeholder entry.
    sculptor_instance_factory_.base_repo.repo.run_git(("checkout", "--detach", "HEAD"))

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        navigate_to_add_workspace_page(page)
        add_ws_page = PlaywrightAddWorkspacePage(page=page)

        add_ws_page.open_branch_selector()
        options = add_ws_page.get_branch_options()

        # The real branches must still be offered (this also waits for the
        # dropdown to finish loading before the negative assertion below runs).
        expect(options.filter(has_text="testing")).to_have_count(1)
        expect(options.filter(has_text="main")).to_have_count(1)

        # git's detached-HEAD placeholder must never appear as a selectable option.
        expect(options.filter(has_text="HEAD detached")).to_have_count(0)
