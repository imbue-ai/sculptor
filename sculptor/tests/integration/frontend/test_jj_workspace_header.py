"""Integration coverage for a jj workspace's header: its bookmark pill and its target bookmark.

Each test spawns its own instance, because it colocates its repository with jj and
leaves a `.jj` behind; see `sculptor.testing.jj_sculptor_instance` for the setup.
The agent runs jj by its absolute path, so these tests do not depend on what jj
the agent's PATH holds; `test_jj_agent_launch.py` covers that.
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
from sculptor.testing.jj_sculptor_instance import JJ_TEST_TARGET_BOOKMARK
from sculptor.testing.jj_sculptor_instance import bash_step
from sculptor.testing.jj_sculptor_instance import colocate_base_repo_with_origin
from sculptor.testing.jj_sculptor_instance import multi_step_prompt
from sculptor.testing.jj_sculptor_instance import open_jj_workspace_agent
from sculptor.testing.jj_sculptor_instance import use_jj_binary
from sculptor.testing.jj_sculptor_instance import write_file_step
from sculptor.testing.playwright_utils import full_spa_reload
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BOOKMARK = "jj-header"
_RELEASE_TARGET = "release@origin"


@user_story("to see my jj workspace named by the bookmark it asked for, and then by the bookmark Sculptor creates")
def test_the_pill_ghosts_the_requested_bookmark_until_sculptor_creates_it_after_a_turn(
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
        pill = task_page.get_jj_identity_pill()
        card = task_page.get_jj_identity_card()

        # No bookmark yet: the pill shows the requested name, and a click would copy the change id.
        expect(pill).to_contain_text(_BOOKMARK, timeout=60_000)
        expect(pill).to_have_attribute("aria-label", re.compile(r"^Copy change id "))
        pill.hover()
        expect(card).to_contain_text(f"None yet. Sculptor sets {_BOOKMARK} on the newest described revision.")
        page.mouse.move(0, 0)
        expect(card).to_be_hidden()

        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [write_file_step("notes.md", "first notes\n"), bash_step(f"{jj} describe -m 'Add notes'")]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

        # After the turn, Sculptor puts the requested bookmark on the described change.
        expect(pill).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")
        expect(task_page.get_jj_unbookmarked_marker()).to_have_count(0)
        pill.hover()
        expect(card).not_to_contain_text("None yet")
        expect(card).to_contain_text(_BOOKMARK)
        page.mouse.move(0, 0)
        expect(card).to_be_hidden()

        # A described change above the bookmark shows as `↑1`; the bookmark stays where it is.
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

        expect(task_page.get_jj_unbookmarked_marker()).to_have_text("↑1")
        expect(pill).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")
        pill.hover()
        expect(card).to_contain_text(f"1 described revision above {_BOOKMARK}")


@user_story("to see the bookmark Sculptor creates after a turn on its revision in the open Revisions panel")
def test_the_open_revisions_panel_shows_the_bookmark_sculptor_creates_after_a_turn(
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
        revisions = get_commits_panel_in(open_panel(page, "commits", sub_section="left"), page).get_revision_entries()
        expect(revisions).to_have_count(1, timeout=60_000)

        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [write_file_step("notes.md", "first notes\n"), bash_step(f"{jj} describe -m 'Add notes'")]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)
        expect(task_page.get_jj_identity_pill()).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")

        described = revisions.filter(has_text="Add notes")
        expect(described).to_have_count(1)
        expect(described).to_contain_text(_BOOKMARK)


@user_story("to point my jj workspace at another target bookmark and see its revisions counted from there")
def test_changing_the_target_bookmark_moves_the_fork_point_and_persists(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_base_repo_with_origin(
        sculptor_instance_factory_, jj_binary, tmp_path / "origin.git", other_remote_branches=("release",)
    )

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        task_page, _ = open_jj_workspace_agent(page, _BOOKMARK)
        selector = task_page.get_target_branch_selector()
        expect(selector).to_contain_text(JJ_TEST_TARGET_BOOKMARK, timeout=60_000)

        revisions_panel = get_commits_panel_in(open_panel(page, "commits", sub_section="left"), page)
        fork_point = revisions_panel.get_revisions_fork_point()
        expect(fork_point).to_contain_text(f"fork point ({JJ_TEST_TARGET_BOOKMARK} · ")

        selector.click()
        release_option = task_page.get_target_branch_options().filter(has_text=_RELEASE_TARGET)
        expect(release_option).to_be_visible()
        release_option.click()

        expect(selector).to_contain_text(_RELEASE_TARGET)
        expect(fork_point).to_contain_text(f"fork point ({_RELEASE_TARGET} · ")
        task_page.get_jj_identity_pill().hover()
        expect(task_page.get_jj_identity_card()).to_contain_text(re.compile(rf"Target\s*{re.escape(_RELEASE_TARGET)}"))

        full_spa_reload(page)

        expect(task_page.get_target_branch_selector()).to_contain_text(_RELEASE_TARGET, timeout=60_000)
