"""Integration coverage for recovering a jj workspace's stale working copy from its banner.

The working copy goes stale the way it does for a user: an edit is snapshotted in
the workspace, then an operation restore in the main repository rewinds past it.
Sculptor notices only when one of its own snapshotting calls fails, such as the
read behind the Revisions panel. Until the user updates it, that read answers with
the revisions as the repository last recorded them. See `sculptor.testing.jj_sculptor_instance`
for the setup.
"""

import re
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.commits_panel import get_commits_panel_in
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import make_workspace_stale
from sculptor.testing.jj_sculptor_instance import bash_step
from sculptor.testing.jj_sculptor_instance import colocate_base_repo_with_origin
from sculptor.testing.jj_sculptor_instance import find_jj_workspace_root
from sculptor.testing.jj_sculptor_instance import multi_step_prompt
from sculptor.testing.jj_sculptor_instance import open_jj_workspace_agent
from sculptor.testing.jj_sculptor_instance import use_jj_binary
from sculptor.testing.jj_sculptor_instance import write_file_step
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BOOKMARK = "jj-stale"
_REVISIONS_ROUTE = re.compile(r"/api/v1/workspaces/[^/]+/revisions$")


@user_story("to see my stale jj workspace's revisions and bring its working copy up to date with one click")
def test_a_stale_working_copy_keeps_its_revisions_and_shows_a_banner_that_updates_it(
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
        task_page, workspace_id = open_jj_workspace_agent(page, _BOOKMARK)
        chat_panel = task_page.get_chat_panel()
        pill = task_page.get_jj_identity_pill()
        stale_banner = task_page.get_jj_stale_banner()
        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [write_file_step("notes.md", "first notes\n"), bash_step(f"{jj} describe -m 'Add notes'")]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)
        expect(pill).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")
        expect(stale_banner).to_have_count(0)

        make_workspace_stale(jj_binary, repo_path, find_jj_workspace_root(jj_binary, repo_path, workspace_id))

        # Nothing has read the revisions yet, so the panel's first read finds the working copy stale.
        with page.expect_response(_REVISIONS_ROUTE) as revisions_response:
            revisions_panel = get_commits_panel_in(open_panel(page, "commits", sub_section="left"), page)
        assert revisions_response.value.status == 200, revisions_response.value.text()

        # That read marks the workspace stale, and the panel keeps the revisions as last recorded.
        expect(stale_banner).to_contain_text("This workspace's working copy is stale")
        revisions = revisions_panel.get_revision_entries()
        expect(revisions.filter(has_text="Add notes")).to_contain_text(_BOOKMARK)
        pill.hover()
        card = task_page.get_jj_identity_card()
        expect(card).to_contain_text("stale")
        expect(card).to_contain_text(re.compile(r"Commit\s*[0-9a-f]{8}"))
        page.mouse.move(0, 0)

        task_page.get_jj_update_stale_button().click()

        expect(stale_banner).to_have_count(0)
        # jj snapshots again: a new described change shows above the bookmark.
        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [
                    bash_step(f"{jj} new"),
                    write_file_step("more.md", "more notes\n"),
                    bash_step(f"{jj} describe -m 'Add more notes'"),
                ]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)
        expect(revisions.filter(has_text="Add more notes")).to_have_count(1)
        expect(task_page.get_jj_unbookmarked_marker()).to_have_text("↑1")
        expect(stale_banner).to_have_count(0)
