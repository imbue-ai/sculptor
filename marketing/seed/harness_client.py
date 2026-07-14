"""Client access to the QA-harness Sculptor backend, via the generated
`sculpt` API client.

The backend port comes from the file the harness launcher writes — never from
the ambient SCULPT_API_PORT, which inside a Sculptor workspace points at the
user's real backend (seeding there would pollute their live instance).
HARNESS_BACKEND_PORT is an explicit escape hatch for other setups.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

from config import BACKEND_PORT_FILE, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools" / "sculpt"))

from sculpt.auth import MODEL_MAPPING, get_authenticated_client  # noqa: E402
from sculpt.client.api.default import (  # noqa: E402
    create_workspace_agent,
    create_workspace_v2,
    delete_workspace,
    list_workspace_agents,
    list_workspaces,
    mark_workspace_agent_read,
    send_workspace_agent_messages,
)
from sculpt.client.models.create_agent_request import CreateAgentRequest  # noqa: E402
from sculpt.client.models.create_workspace_request_v2 import CreateWorkspaceRequestV2  # noqa: E402
from sculpt.client.models.send_message_request import SendMessageRequest  # noqa: E402
from sculpt.client.models.workspace_initialization_strategy import WorkspaceInitializationStrategy  # noqa: E402
from sculpt.client.types import UNSET  # noqa: E402
from sculpt.resolve import resolve_project  # noqa: E402


def backend_port() -> str:
    explicit = os.environ.get("HARNESS_BACKEND_PORT")
    if explicit:
        return explicit
    if not BACKEND_PORT_FILE.exists():
        raise RuntimeError(
            f"No harness backend port at {BACKEND_PORT_FILE} — start it first:\n"
            "  uv run --project sculptor python marketing/seed/harness.py"
        )
    return BACKEND_PORT_FILE.read_text().strip()


def client():
    # Strip all ambient SCULPT_* context so nothing downstream re-targets the
    # user's real instance; we talk only to the harness backend.
    for ambient in ("SCULPT_PROJECT_ID", "SCULPT_WORKSPACE_ID", "SCULPT_AGENT_ID", "SCULPT_API_PORT"):
        os.environ.pop(ambient, None)
    return get_authenticated_client(f"http://localhost:{backend_port()}")


def _call(c, endpoint, **kwargs):
    """Issue an endpoint's sync_detailed call and return the response."""
    return endpoint.sync_detailed(client=c, **kwargs)


def _ok(resp, what: str) -> dict:
    if resp.status_code != 200:
        raise RuntimeError(f"{what} -> {resp.status_code}: {resp.content[:600]}")
    return json.loads(resp.content) if resp.content else {}


def ensure_project(repo_path: str, c) -> str:
    """Register the repo with the backend (idempotent) and return its project id."""
    return resolve_project(repo=repo_path, client=c)


def list_project_workspaces(project_id: str, c) -> list[dict]:
    resp = _call(c, list_workspaces, project_id=project_id)
    body = json.loads(resp.content) if resp.status_code == 200 and resp.content else []
    return body if isinstance(body, list) else []


def delete_all_workspaces(project_id: str, c) -> int:
    """Remove every workspace in a project — a clean slate before a full re-seed
    (handles workspaces left behind when a manifest branch is renamed)."""
    removed = 0
    for ws in list_project_workspaces(project_id, c):
        _call(c, delete_workspace, workspace_id=ws["objectId"])
        removed += 1
    return removed


def delete_workspaces_by_branch(project_id: str, branch_name: str, c) -> int:
    """Remove any existing workspaces on `branch_name` so a re-seed starts clean."""
    removed = 0
    for ws in list_project_workspaces(project_id, c):
        if ws.get("requestedBranchName") == branch_name:
            _call(c, delete_workspace, workspace_id=ws["objectId"])
            removed += 1
    return removed


def free_branch(repo_path: str, branch_name: str) -> None:
    """Delete a leftover git branch so `create_workspace` can re-create it.

    Deleting a workspace record does not delete the git branch it left behind
    in the repo, so a re-seed on the same branch 409s. Prune stale worktrees,
    force-remove any live worktree still on the branch, then delete the branch.
    All steps are best-effort (a fresh branch simply won't exist yet).
    """

    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", repo_path, *args], capture_output=True, text=True, check=False)

    git("worktree", "prune")
    listing = git("worktree", "list", "--porcelain").stdout
    current_path = None
    for line in listing.splitlines():
        if line.startswith("worktree "):
            current_path = line[len("worktree ") :]
        elif line.startswith("branch ") and line.endswith(f"/{branch_name}") and current_path:
            git("worktree", "remove", "--force", current_path)
    git("branch", "-D", branch_name)


def create_workspace(
    *, project_id: str, branch_name: str, name: str, source_branch: str = "main", target_branch: str = "main", c
) -> str:
    req = CreateWorkspaceRequestV2(
        project_id=project_id,
        initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
        source_branch=source_branch,
        description=name,
        requested_branch_name=branch_name,
        target_branch=target_branch,
    )
    body = _ok(_call(c, create_workspace_v2, body=req), f"create_workspace({branch_name})")
    return body["objectId"]


def create_agent(*, workspace_id: str, prompt: str, model_alias: str, name: str, c) -> str:
    req = CreateAgentRequest(
        prompt=prompt,
        model=MODEL_MAPPING[model_alias],
        interface="API",
        files=[],
        name=name,
        sent_via="sculpt",
        agent_type=UNSET,
    )
    body = _ok(_call(c, create_workspace_agent, workspace_id=workspace_id, body=req), f"create_agent({name})")
    return body["id"]


def mark_read(workspace_id: str, agent_id: str, c) -> None:
    """Clear a workspace's unread indicator so the sidebar shows a read state."""
    _call(c, mark_workspace_agent_read, workspace_id=workspace_id, agent_id=agent_id)


def send_message(workspace_id: str, agent_id: str, text: str, model_alias: str, c) -> None:
    """Send a follow-up turn to an existing agent (e.g. a state-inducing directive)."""
    req = SendMessageRequest(message=text, model=MODEL_MAPPING[model_alias], files=[], sent_via="sculpt")
    _ok(_call(c, send_workspace_agent_messages, workspace_id=workspace_id, agent_id=agent_id, body=req), "send_message")


def wait_until_ready(workspace_id: str, agent_id: str, c, timeout_s: int = 120) -> str:
    """Poll the workspace's agents until `agent_id` leaves a running state."""
    deadline = time.time() + timeout_s
    last = "?"
    while time.time() < deadline:
        resp = _call(c, list_workspace_agents, workspace_id=workspace_id)
        agents = json.loads(resp.content) if resp.status_code == 200 and resp.content else []
        for a in agents if isinstance(agents, list) else []:
            if a.get("id") == agent_id:
                last = a.get("taskStatus") or a.get("status") or "?"
        if last in ("READY", "ERROR", "DONE", "COMPLETED"):
            return last
        time.sleep(2)
    return last
