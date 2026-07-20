"""Re-send a transient state turn (in-progress / waiting / error) to a seeded
workspace's agent, without re-seeding everything.

The in-progress (hang) and error turns don't persist forever, so re-run this
right before a capture to refresh a workspace's state. The waiting-on-question
turn holds its amber state for the manifest's scripted timeout.

Usage (from repo root):
  uv run --project sculptor python marketing/seed/induce_state.py                  # all STATE_TURNS
  uv run --project sculptor python marketing/seed/induce_state.py fix/flaky-reconnect-test
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools" / "sculpt"))

from harness_client import _call, client, ensure_project, list_project_workspaces, send_message
from manifest import STATE_TURNS, all_specs
from repos import ensure_clone
from sculpt.client.api.default import list_workspace_agents


def _find_ws_and_agent(branch: str, c) -> tuple[str, str] | None:
    repo_name = next((s["repo"] for s in all_specs() if s["branch"] == branch), None)
    if repo_name is None:
        return None
    clone = ensure_clone(repo_name)
    if clone is None:
        return None
    pid = ensure_project(clone["path"], c)
    ws_id = next(
        (w["objectId"] for w in list_project_workspaces(pid, c) if w.get("requestedBranchName") == branch),
        None,
    )
    if ws_id is None:
        return None
    resp = _call(c, list_workspace_agents, workspace_id=ws_id)
    agents = json.loads(resp.content) if resp.status_code == 200 and resp.content else []
    agent_id = agents[0]["id"] if isinstance(agents, list) and agents else None
    return (ws_id, agent_id) if agent_id else None


def main() -> None:
    branches = sys.argv[1:] or list(STATE_TURNS)
    c = client()
    for branch in branches:
        prompt = STATE_TURNS.get(branch)
        if prompt is None:
            print(f"  no STATE_TURN for {branch}; skipping")
            continue
        found = _find_ws_and_agent(branch, c)
        if found is None:
            print(f"  workspace/agent for {branch} not found; skipping")
            continue
        ws_id, agent_id = found
        send_message(ws_id, agent_id, prompt, "fake", c)
        print(f"  re-induced state -> {branch}")


if __name__ == "__main__":
    main()
