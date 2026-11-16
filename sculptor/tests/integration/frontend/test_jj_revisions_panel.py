"""Integration coverage for a jj workspace's Revisions and Changes panels.

The jj tests spawn their own instance, so the `.jj` that colocating the base
repository leaves behind is not seen by another test. jj is given to the backend
as a CUSTOM path to the pinned binary, and the `jj_isolated_env` fixture gives the
test process, and so the backend and its agents, an empty jj user config and a
test identity. The agent runs jj by its absolute path, so the test does not
depend on jj being on the agent's PATH.

A jj workspace is created through `POST /api/v1/workspaces`, as `sculpt
workspace create --strategy jj` does, and its first agent through the agents
route; the agent is then driven from its chat like any other.
"""

import json
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.changes_panel import get_changes_panel_in
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.commits_panel import get_commits_panel_in
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace_without_agent
from sculptor.testing.playwright_utils import request_with_retry
from sculptor.testing.playwright_utils import resolve_backend_api_url
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_BOOKMARK = "jj-revisions"


def _use_jj_binary(factory: SculptorInstanceFactory, jj_binary: JjBinary) -> None:
    """Point the backend at the pinned jj as a CUSTOM path, before it starts."""
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    dependency_paths = config.dependency_paths.model_copy(update={"jj": str(jj_binary.path)})
    save_config(config.model_copy(update={"dependency_paths": dependency_paths}), config_path)


def _limit_new_jj_files_to_mib(factory: SculptorInstanceFactory, mib: int) -> None:
    """Set Sculptor's limit on the new files jj snapshots, which it writes into each jj workspace's config."""
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    save_config(config.model_copy(update={"jj_snapshot_max_new_file_size_mib": mib}), config_path)


def _write_small_and_oversized_files_prompt() -> str:
    """Add a small file and a new file of 2 MiB."""
    steps = [
        {"command": "write_file", "args": {"file_path": "small.md", "content": "small\n"}},
        {"command": "bash", "args": {"command": "head -c 2097152 /dev/zero > big.bin"}},
    ]
    return f"fake_claude:multi_step `{json.dumps({'steps': steps})}`"


def _describe_then_new_prompt(jj_path: Path) -> str:
    """Describe a change that adds `notes.md`, start a new one, and edit `scratch.md` in it."""
    steps = [
        {"command": "write_file", "args": {"file_path": "notes.md", "content": "first notes\n"}},
        {"command": "bash", "args": {"command": f"'{jj_path}' describe -m 'Add notes'"}},
        {"command": "bash", "args": {"command": f"'{jj_path}' new"}},
        {"command": "write_file", "args": {"file_path": "scratch.md", "content": "scratch\n"}},
    ]
    return f"fake_claude:multi_step `{json.dumps({'steps': steps})}`"


def _open_jj_workspace_agent(page: Page) -> PlaywrightTaskPage:
    """Create a jj workspace and its first agent through the API, and open the agent's chat."""
    base_url = resolve_backend_api_url(page)
    projects_response = request_with_retry(page.request.get, f"{base_url}/api/v1/projects/active")
    assert projects_response.ok, f"list active projects failed: {projects_response.status} {projects_response.text()}"
    project_id = projects_response.json()[0]["objectId"]

    use_jj_response = request_with_retry(
        page.request.put,
        f"{base_url}/api/v1/projects/{project_id}/use_jj_for_new_workspaces",
        data={"useJjForNewWorkspaces": True},
    )
    assert use_jj_response.ok, f"turning jj on failed: {use_jj_response.status} {use_jj_response.text()}"

    workspace_response = request_with_retry(
        page.request.post,
        f"{base_url}/api/v1/workspaces",
        data={
            "projectId": project_id,
            "initializationStrategy": "JJ_WORKSPACE",
            "requestedBranchName": _BOOKMARK,
            "description": "jj revisions",
        },
    )
    assert workspace_response.ok, (
        f"create jj workspace failed: {workspace_response.status} {workspace_response.text()}"
    )
    workspace_id = workspace_response.json()["objectId"]

    agent_response = request_with_retry(
        page.request.post, f"{base_url}/api/v1/workspaces/{workspace_id}/agents", data={"agentType": "claude"}
    )
    assert agent_response.ok, f"create agent failed: {agent_response.status} {agent_response.text()}"

    navigate_to_workspace_without_agent(page, workspace_id)
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible(timeout=60_000)
    select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    return task_page


@user_story("to see a jj workspace's revisions and discard working-copy changes in its own words")
def test_jj_workspace_lists_revisions_and_discards_the_working_copy(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv
) -> None:
    _use_jj_binary(sculptor_instance_factory_, jj_binary)
    colocate_with_jj(jj_binary, sculptor_instance_factory_.base_repo.base_path)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        task_page = _open_jj_workspace_agent(page)
        chat_panel = task_page.get_chat_panel()
        send_chat_message(chat_panel=chat_panel, message=_describe_then_new_prompt(jj_binary.path))
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

        left_section = PlaywrightWorkspaceSection(page, "left")
        revisions_panel = get_commits_panel_in(open_panel(page, "commits", sub_section="left"), page)
        expect(left_section.get_panel_tab("commits")).to_contain_text("Revisions")

        # The new working copy holds scratch.md; below it, the described change holds notes.md.
        revisions = revisions_panel.get_revision_entries()
        expect(revisions).to_have_count(2)
        working_copy, described = revisions.nth(0), revisions.nth(1)
        expect(working_copy).to_contain_text("(no description set)")
        expect(working_copy).to_contain_text("working copy")
        expect(described).to_contain_text("Add notes")
        expect(revisions_panel.get_revisions_fork_point()).to_contain_text("fork point (")

        revisions_panel.get_revision_summary(described).click()
        notes_row = revisions_panel.get_tree_rows(described).filter(has_text="notes.md")
        expect(notes_row).to_be_visible()
        notes_row.click()
        viewer = revisions_panel.get_diff_viewer()
        viewer.assert_diff_shows("notes.md")
        expect(viewer).to_contain_text("first notes")

        changes_panel = get_changes_panel_in(open_panel(page, "changes", sub_section="left"), page)
        working_copy_scope = changes_panel.get_scope_uncommitted()
        expect(working_copy_scope).to_contain_text("Working copy")
        working_copy_scope.click()
        expect(working_copy_scope).to_have_attribute("data-state", "on")

        tree_rows = changes_panel.get_changes_tree().get_tree_rows()
        expect(tree_rows).to_have_count(1)
        scratch_row = tree_rows.filter(has_text="scratch.md")
        scratch_row.hover()
        changes_panel.get_discard_button(scratch_row).click()
        dialog = changes_panel.get_discard_dialog()
        expect(dialog).to_contain_text("recoverable from the jj operation log")
        changes_panel.get_discard_dialog_confirm().click()

        expect(dialog).to_be_hidden()
        expect(tree_rows).to_have_count(0)


@user_story("to be told which new files jj left out of my workspace, and where to raise the limit")
def test_changes_panel_lists_new_files_jj_left_out(
    sculptor_instance_factory_: SculptorInstanceFactory, jj_binary: JjBinary, jj_isolated_env: JjIsolatedEnv
) -> None:
    _use_jj_binary(sculptor_instance_factory_, jj_binary)
    _limit_new_jj_files_to_mib(sculptor_instance_factory_, 1)
    colocate_with_jj(jj_binary, sculptor_instance_factory_.base_repo.base_path)

    with sculptor_instance_factory_.spawn_instance() as instance:
        page = instance.page
        task_page = _open_jj_workspace_agent(page)
        chat_panel = task_page.get_chat_panel()
        send_chat_message(chat_panel=chat_panel, message=_write_small_and_oversized_files_prompt())
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=60_000)

        changes_panel = get_changes_panel_in(open_panel(page, "changes", sub_section="left"), page)
        tree_rows = changes_panel.get_changes_tree().get_tree_rows()

        for scope in (changes_panel.get_scope_uncommitted(), changes_panel.get_scope_all()):
            scope.click()
            expect(scope).to_have_attribute("data-state", "on")
            # The oversized file is listed apart from the changed files, which hold only small.md.
            expect(tree_rows).to_have_count(1)
            expect(tree_rows.first).to_contain_text("small.md")
            banner = changes_panel.get_jj_left_out_files_banner()
            expect(banner).to_contain_text("Jujutsu settings")
            left_out_files = changes_panel.get_jj_left_out_files()
            expect(left_out_files).to_have_count(1)
            expect(left_out_files.first).to_contain_text("big.bin")
            expect(left_out_files.first).to_contain_text("2097152 bytes")


@user_story("to keep the git words for a git workspace's history and changes")
def test_git_workspace_keeps_its_commits_and_uncommitted_labels(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page)

    left_section = PlaywrightWorkspaceSection(page, "left")
    commits_panel = get_commits_panel_in(open_panel(page, "commits", sub_section="left"), page)
    expect(left_section.get_panel_tab("commits")).to_contain_text("Commits")
    expect(commits_panel.get_terminus()).to_be_visible()
    expect(commits_panel.get_revision_entries()).to_have_count(0)

    changes_panel = get_changes_panel_in(open_panel(page, "changes", sub_section="left"), page)
    expect(changes_panel.get_scope_uncommitted()).to_contain_text("Uncommitted")
