"""Integration coverage for a jj workspace's pull request button, keyed on its bookmark.

The repository's `origin` names a GitHub URL, while `pushInsteadOf` sends pushes to
a local bare repository, so the agent can push its bookmark with no network. New
workspaces run no setup command, because the default one fetches from `origin`.

The fake `gh` answers the batched open-PR search with the nodes in a file the test
writes. It cannot read a head from `.git`, because a jj workspace has none, so the
test names the head itself; it also records the `GH_REPO` it was run with, which is
how `gh` finds the repository from a checkout with no `.git`.
"""

import stat
import subprocess
from pathlib import Path

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import make_github_looking_origin
from sculptor.testing.jj_sculptor_instance import bash_step
from sculptor.testing.jj_sculptor_instance import clear_workspace_setup_command
from sculptor.testing.jj_sculptor_instance import colocate_base_repo_with_origin
from sculptor.testing.jj_sculptor_instance import create_jj_workspace
from sculptor.testing.jj_sculptor_instance import get_active_project_id
from sculptor.testing.jj_sculptor_instance import multi_step_prompt
from sculptor.testing.jj_sculptor_instance import open_new_agent_in_workspace
from sculptor.testing.jj_sculptor_instance import set_use_jj_for_new_workspaces
from sculptor.testing.jj_sculptor_instance import update_user_config
from sculptor.testing.jj_sculptor_instance import use_jj_binary
from sculptor.testing.jj_sculptor_instance import write_file_step
from sculptor.testing.playwright_utils import settle_first_run_offer
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BOOKMARK = "jj-pull-request"
_NAME_WITH_OWNER = "sculptor-tests/jj-fixture"
# The poller's floor; the default interval would leave the test waiting on the next round.
_PR_POLL_INTERVAL_SECONDS = 10

# Paths are injected with `.replace(...)`, so the JSON braces need no escaping.
_FAKE_GH = """\
#!/bin/bash
echo "GH_REPO=${GH_REPO:-} $*" >> "{calls_file}"
if [[ "$*" == *"author:@me"* ]]; then
    NODES=$(cat "{nodes_file}")
    echo '{"data":{"search":{"nodes":'"$NODES"',"pageInfo":{"hasNextPage":false,"endCursor":null}},"rateLimit":{"cost":3,"remaining":4997,"limit":5000,"resetAt":"2026-01-01T00:00:00Z"}}}'
elif [[ "$*" == *"graphql"* ]]; then
    echo '{"data":{"repository":{"pullRequests":{"nodes":[]}}}}'
fi
"""

_OPEN_PR_NODES = (
    '[{"number":42,"title":"Add notes","url":"https://github.com/sculptor-tests/jj-fixture/pull/42",'
    + '"state":"OPEN","baseRefName":"main","repository":{"nameWithOwner":"'
    + _NAME_WITH_OWNER
    + '"},"headRefName":"'
    + _BOOKMARK
    + '","mergeable":"MERGEABLE","commits":{"nodes":[{"commit":{"statusCheckRollup":null}}]},'
    + '"latestReviews":{"nodes":[]},"reviewThreads":{"nodes":[]}}]'
)


def _install_fake_gh(fake_bin_dir: Path, nodes_file: Path, calls_file: Path) -> None:
    script_path = fake_bin_dir / "gh"
    script_path.write_text(_FAKE_GH.replace("{nodes_file}", str(nodes_file)).replace("{calls_file}", str(calls_file)))
    script_path.chmod(script_path.stat().st_mode | stat.S_IEXEC)


def _remote_has_branch(remote_path: Path, branch: str) -> bool:
    result = subprocess.run(
        ["git", "--git-dir", str(remote_path), "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


@user_story("to open a pull request from my jj workspace's bookmark and see its status in the header")
def test_the_pr_button_creates_and_then_shows_the_pull_request_of_the_workspace_bookmark(
    sculptor_instance_factory_: SculptorInstanceFactory,
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    tmp_path: Path,
) -> None:
    use_jj_binary(sculptor_instance_factory_, jj_binary)
    update_user_config(sculptor_instance_factory_, pr_poll_interval_seconds=_PR_POLL_INTERVAL_SECONDS)
    origin_path = tmp_path / "origin.git"
    repo_path = colocate_base_repo_with_origin(sculptor_instance_factory_, jj_binary, origin_path)
    make_github_looking_origin(repo_path, origin_path)
    nodes_file = tmp_path / "open_pr_nodes.json"
    nodes_file.write_text("[]")
    calls_file = tmp_path / "gh_calls.log"
    calls_file.touch()
    _install_fake_gh(sculptor_instance_factory_.fake_bin_dir, nodes_file, calls_file)
    jj = f"'{jj_binary.path}'"

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        settle_first_run_offer(page)
        project_id = get_active_project_id(page)
        clear_workspace_setup_command(page, project_id)
        set_use_jj_for_new_workspaces(page, project_id, True)
        task_page = open_new_agent_in_workspace(page, create_jj_workspace(page, project_id, _BOOKMARK))
        chat_panel = task_page.get_chat_panel()

        send_chat_message(
            chat_panel=chat_panel,
            message=multi_step_prompt(
                [write_file_step("notes.md", "first notes\n"), bash_step(f"{jj} describe -m 'Add notes'")]
            ),
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)
        expect(task_page.get_jj_identity_pill()).to_have_attribute("aria-label", f"Copy bookmark {_BOOKMARK}")

        create_button = task_page.get_pr_button_create()
        expect(create_button).to_be_enabled(timeout=60_000)
        create_button.click()

        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4, timeout=60_000)
        create_pr_message = chat_panel.get_messages().nth(2)
        expect(create_pr_message).to_contain_text(f"jj git push -b {_BOOKMARK}")
        expect(create_pr_message).to_contain_text(f"gh pr create --head {_BOOKMARK} --base main")

        send_chat_message(
            chat_panel=chat_panel, message=multi_step_prompt([bash_step(f"{jj} git push -b {_BOOKMARK}")])
        )
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=6, timeout=60_000)
        assert _remote_has_branch(origin_path, _BOOKMARK), f"the push did not land {_BOOKMARK} in {origin_path}"

        nodes_file.write_text(_OPEN_PR_NODES)

        open_button = task_page.get_pr_button_open()
        expect(open_button).to_be_visible(timeout=90_000)
        expect(open_button).to_contain_text("PR #42")
        queries = [line for line in calls_file.read_text().splitlines() if "graphql" in line]
        gh_repos = {line.split(" ", 1)[0] for line in queries}
        assert gh_repos == {f"GH_REPO=github.com/{_NAME_WITH_OWNER}"}, f"gh queried GitHub with {gh_repos}"
