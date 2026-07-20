"""Seed the full demo state described in manifest.py into the QA harness.

Idempotent and repeatable: every available repo is re-cloned fresh under the
demo directory (so demo branches never touch the user's real checkouts), the
gh-shim PR fixtures are written, all workspaces are recreated, and all agents
are kicked off together (FakeClaude turns run concurrently in the backend, so
total time is roughly one turn, not the sum).

Run from the repo root (after `python marketing/seed/harness.py`):
  uv run --project sculptor python marketing/seed/seed_all.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import FAKE_ORIGIN_OWNER, GH_FIXTURES_PATH, REPO_ROOT

sys.path.insert(0, str(REPO_ROOT / "tools" / "sculpt"))

from harness_client import (
    _call,
    clean_slate,
    client,
    create_agent,
    create_workspace,
    ensure_project,
    mark_read,
    send_message,
    settled_status,
)
from manifest import PR_FIXTURES, READ_BRANCHES, REPO_NAMES, STATE_TURNS, all_specs
from repos import clone_available_repos
from sculpt.client import Client
from sculpt.client.api.default import list_workspace_agents


def write_pr_fixtures() -> None:
    GH_FIXTURES_PATH.parent.mkdir(parents=True, exist_ok=True)
    GH_FIXTURES_PATH.write_text(json.dumps({"owner": FAKE_ORIGIN_OWNER, **PR_FIXTURES}, indent=2))
    print(f"Wrote PR fixtures for {len(PR_FIXTURES['branches'])} branch(es) -> {GH_FIXTURES_PATH}")


def main() -> None:
    c = client()

    # Clear the backend BEFORE touching the clones on disk: live workspaces
    # hold worktrees inside them, and re-cloning underneath a live workspace
    # leaves the backend's pollers erroring against dead git dirs.
    workspaces_cleared, projects_cleared = clean_slate(c)
    if projects_cleared:
        print(f"Clean slate: removed {workspaces_cleared} workspace(s) across {projects_cleared} project(s).")

    clones = clone_available_repos(REPO_NAMES)
    if not clones:
        raise RuntimeError("no demo repos available to seed")
    write_pr_fixtures()

    specs = [s for s in all_specs() if s["repo"] in clones]
    skipped = [s["name"] for s in all_specs() if s["repo"] not in clones]
    if skipped:
        print(f"Skipping {len(skipped)} workspace(s) for unavailable repos: {', '.join(skipped)}")

    project_ids: dict[str, str] = {}
    for name, clone in clones.items():
        project_ids[name] = ensure_project(clone["path"], c)
        print(f"project {name}: {project_ids[name]}")

    created: list[tuple[str, str, str]] = []  # (name, workspace_id, agent_id)
    by_branch: dict[str, tuple[str, str]] = {}  # branch -> (workspace_id, agent_id)
    for s in specs:
        clone = clones[s["repo"]]
        ws = create_workspace(
            project_id=project_ids[s["repo"]],
            branch_name=s["branch"],
            name=s["name"],
            source_branch=clone["default_branch"],
            target_branch=clone["default_branch"],
            c=c,
        )
        agent = create_agent(workspace_id=ws, prompt=s["prompt"], model_alias="fake", name=s["name"], c=c)
        created.append((s["name"], ws, agent))
        by_branch[s["branch"]] = (ws, agent)
        print(f"  seeded {s['branch']:<30} {s['name']}")

    print(f"\nKicked off {len(created)} workspaces; waiting for agents to settle...")
    _wait_all(created, c)

    # Vary the sidebar: mark a subset read so not every row looks unread.
    marked = 0
    for branch in READ_BRANCHES:
        if branch in by_branch:
            ws, agent = by_branch[branch]
            mark_read(ws, agent, c)
            marked += 1
    print(f"Marked {marked} workspace(s) read.")

    # Flip a few workspaces into transient agent states (in-progress / waiting /
    # error) via a follow-up turn, so the sidebar shows the full range of states.
    for branch, prompt in STATE_TURNS.items():
        if branch in by_branch:
            ws, agent = by_branch[branch]
            send_message(ws, agent, prompt, "fake", c)
            print(f"  state turn -> {branch}")


def _wait_all(created: list[tuple[str, str, str]], c: Client, timeout_s: int = 120) -> None:
    deadline = time.time() + timeout_s
    pending = {ws: (name, agent) for name, ws, agent in created}
    while pending and time.time() < deadline:
        for ws in list(pending):
            name, agent = pending[ws]
            resp = _call(c, list_workspace_agents, workspace_id=ws)
            agents = json.loads(resp.content) if resp.status_code == 200 and resp.content else []
            status = None
            for a in agents if isinstance(agents, list) else []:
                if a.get("id") == agent:
                    status = settled_status(a)
            if status is not None:
                print(f"  done: {name} [{status}]")
                pending.pop(ws)
        if pending:
            time.sleep(3)
    if pending:
        print(f"  still running after {timeout_s}s: {[n for n, _ in pending.values()]}")


if __name__ == "__main__":
    main()
