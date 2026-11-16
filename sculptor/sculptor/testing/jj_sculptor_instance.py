"""Helpers for browser tests that run a Sculptor instance against a jj colocation.

A test points the backend at the pinned jj with `use_jj_binary` and colocates the
factory's base repository before it spawns the instance, then creates jj
workspaces through `POST /api/v1/workspaces`, as `sculpt workspace create
--strategy jj` does. The `jj_isolated_env` fixture gives the test process, and so
the backend and its agents, an empty jj user config and a test identity.
"""

import json
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Literal

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.services.user_config.user_config import load_config
from sculptor.services.user_config.user_config import save_config
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import add_bare_origin
from sculptor.testing.jj_repos import colocate_with_jj
from sculptor.testing.jj_repos import run_jj
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_workspace_without_agent
from sculptor.testing.playwright_utils import request_with_retry
from sculptor.testing.playwright_utils import resolve_backend_api_url
from sculptor.testing.sculptor_instance import SculptorInstanceFactory

JJ_TEST_TARGET_BOOKMARK = "main@origin"


def update_user_config(factory: SculptorInstanceFactory, **fields: object) -> None:
    """Set user config fields for the instances the factory spawns next."""
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    config = load_config(config_path)
    save_config(config.model_copy(update=fields), config_path)


def use_jj_binary(factory: SculptorInstanceFactory, jj_binary: JjBinary) -> None:
    """Point the backend at the pinned jj as a CUSTOM path, before it starts."""
    config_path = factory._delegate.sculptor_folder / "internal" / "config.toml"
    dependency_paths = load_config(config_path).dependency_paths.model_copy(update={"jj": str(jj_binary.path)})
    update_user_config(factory, dependency_paths=dependency_paths)


def colocate_base_repo_with_origin(
    factory: SculptorInstanceFactory,
    jj_binary: JjBinary,
    origin_path: Path,
    other_remote_branches: Sequence[str] = (),
) -> Path:
    """Put the factory's base repository on `main`, push it to a bare `origin`, and colocate it with jj.

    A jj workspace's default target is then `main@origin`, as in a real clone. Each of
    `other_remote_branches` is pushed to `origin` at `main` too, so it is a remote
    bookmark the repository already knows when jj colocates. Returns the repository's path.
    """
    repo = factory.base_repo
    repo.create_reset_and_checkout_branch("main")
    add_bare_origin(repo.base_path, origin_path)
    for branch in other_remote_branches:
        repo.repo.run_git(("push", "origin", f"HEAD:{branch}"))
    colocate_with_jj(jj_binary, repo.base_path)
    return repo.base_path


def get_active_project_id(page: Page) -> str:
    base_url = resolve_backend_api_url(page)
    response = request_with_retry(page.request.get, f"{base_url}/api/v1/projects/active")
    assert response.ok, f"list active projects failed: {response.status} {response.text()}"
    return response.json()[0]["objectId"]


def set_use_jj_for_new_workspaces(page: Page, project_id: str, is_enabled: bool) -> None:
    base_url = resolve_backend_api_url(page)
    response = request_with_retry(
        page.request.put,
        f"{base_url}/api/v1/projects/{project_id}/use_jj_for_new_workspaces",
        data={"useJjForNewWorkspaces": is_enabled},
    )
    assert response.ok, f"setting use-jj to {is_enabled} failed: {response.status} {response.text()}"


def clear_workspace_setup_command(page: Page, project_id: str) -> None:
    """Run no setup command in new workspaces, so none fetches from the repository's origin."""
    base_url = resolve_backend_api_url(page)
    response = request_with_retry(
        page.request.put,
        f"{base_url}/api/v1/projects/{project_id}/workspace_setup_command",
        data={"workspaceSetupCommand": ""},
    )
    assert response.ok, f"clearing the setup command failed: {response.status} {response.text()}"


def create_jj_workspace(page: Page, project_id: str, bookmark: str) -> str:
    """Create a jj workspace whose requested bookmark is `bookmark`, and return its id."""
    base_url = resolve_backend_api_url(page)
    response = request_with_retry(
        page.request.post,
        f"{base_url}/api/v1/workspaces",
        data={
            "projectId": project_id,
            "initializationStrategy": "JJ_WORKSPACE",
            "requestedBranchName": bookmark,
            "description": bookmark,
        },
    )
    assert response.ok, f"create jj workspace failed: {response.status} {response.text()}"
    return response.json()["objectId"]


def open_new_agent_in_workspace(
    page: Page, workspace_id: str, agent_type: Literal["claude", "pi"] = "claude"
) -> PlaywrightTaskPage:
    """Create an agent in the workspace and open its chat, on FakeClaude for a Claude agent.

    A pi agent runs whatever `pi` is first on the backend's PATH, such as FakePi.
    """
    base_url = resolve_backend_api_url(page)
    response = request_with_retry(
        page.request.post, f"{base_url}/api/v1/workspaces/{workspace_id}/agents", data={"agentType": agent_type}
    )
    assert response.ok, f"create agent failed: {response.status} {response.text()}"
    navigate_to_workspace_without_agent(page, workspace_id)
    task_page = PlaywrightTaskPage(page=page)
    chat_panel = task_page.get_chat_panel()
    expect(chat_panel).to_be_visible(timeout=60_000)
    if agent_type == "claude":
        select_model_by_name(chat_panel=chat_panel, model_name=FAKE_CLAUDE_MODEL_NAME)
    return task_page


def open_jj_workspace_agent(page: Page, bookmark: str) -> tuple[PlaywrightTaskPage, str]:
    """Turn jj on for the active repository, create a jj workspace and its first agent, and open the agent's chat.

    Returns the agent's page and the workspace's id.
    """
    project_id = get_active_project_id(page)
    set_use_jj_for_new_workspaces(page, project_id, True)
    workspace_id = create_jj_workspace(page, project_id, bookmark)
    return open_new_agent_in_workspace(page, workspace_id), workspace_id


def multi_step_prompt(steps: Sequence[Mapping[str, object]]) -> str:
    """A FakeClaude prompt that runs `steps` in order."""
    return f"fake_claude:multi_step `{json.dumps({'steps': list(steps)})}`"


def bash_step(command: str) -> dict[str, object]:
    return {"command": "bash", "args": {"command": command}}


def write_file_step(file_path: str, content: str) -> dict[str, object]:
    return {"command": "write_file", "args": {"file_path": file_path, "content": content}}


def find_jj_workspace_root(jj_binary: JjBinary, repo_path: Path, workspace_id: str) -> Path:
    """The checkout of the jj workspace Sculptor named after `workspace_id`, as the repository lists it."""
    listing = run_jj(
        jj_binary,
        ("--ignore-working-copy", "workspace", "list", "-T", 'name ++ "\\t" ++ root ++ "\\n"'),
        cwd=repo_path,
    )
    roots_by_name = dict(line.split("\t", 1) for line in listing.splitlines())
    assert workspace_id in roots_by_name, f"jj lists no workspace {workspace_id}: {listing}"
    return Path(roots_by_name[workspace_id])


def list_jj_workspace_names(jj_binary: JjBinary, repo_path: Path) -> list[str]:
    listing = run_jj(jj_binary, ("--ignore-working-copy", "workspace", "list", "-T", 'name ++ "\\n"'), cwd=repo_path)
    return listing.splitlines()


def list_local_bookmarks(jj_binary: JjBinary, repo_path: Path) -> list[str]:
    listing = run_jj(
        jj_binary, ("--ignore-working-copy", "bookmark", "list", "-T", 'if(!remote, name ++ "\\n")'), cwd=repo_path
    )
    return listing.splitlines()
