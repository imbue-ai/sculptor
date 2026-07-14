"""Fresh demo clones under the demo directory.

Each seed run re-clones every available repo from its local source into
<demo dir>/repos/<name>, so demo branches and worktrees accumulate in the
throwaway clone instead of the user's real checkout, and every run starts from
an identical state. Local clones hardlink objects, so this is cheap even for
large repos.

Every clone's `origin` is rewritten to a github.com URL: the backend's PR
polling only runs against github-shaped origins, and the gh shim
(marketing/gh_shim/gh) answers for that owner/repo — nothing ever contacts
GitHub.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from config import REPOS_DIR, fake_origin_url, repo_clone_source


def _git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True, check=check)


def _checkout_default_branch(target: Path) -> str:
    """Put the clone on its repo's main-line branch and return its name.

    Cloning a local checkout lands on whatever branch that checkout has out,
    which for a working repo is usually a feature branch. Demo workspaces
    branch off (and target) the main line, and the backend can only use LOCAL
    branches of the clone — the rewritten origin URL is fake, so nothing can be
    fetched later. Materialize main/master from the clone's remote-tracking
    refs while they still point somewhere real.
    """
    for candidate in ("main", "master"):
        if _git(target, "rev-parse", "--verify", "--quiet", f"origin/{candidate}", check=False).returncode == 0:
            _git(target, "checkout", "-q", "-B", candidate, f"origin/{candidate}")
            return candidate
    return _git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()


def fresh_clone(name: str, source: Path) -> dict:
    """Clone `source` to a pristine <repos>/<name> and return its metadata."""
    target = REPOS_DIR / name
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "clone", "--quiet", str(source), str(target)],
        capture_output=True,
        text=True,
        check=True,
    )
    default_branch = _checkout_default_branch(target)
    _git(target, "remote", "set-url", "origin", fake_origin_url(name))
    # A neutral committer identity so nothing the backend commits in this clone
    # (or its worktrees) carries the user's real name into a screenshot.
    _git(target, "config", "user.name", "Sculptor Demo")
    _git(target, "config", "user.email", "demo@imbue.com")
    return {"name": name, "path": str(target), "default_branch": default_branch}


def ensure_clone(name: str) -> dict | None:
    """Return the clone's metadata, cloning only if it doesn't exist yet.

    Partial re-seeds (seed_hero, induce_state) use this instead of fresh_clone:
    other seeded workspaces hold worktrees inside the existing clone, and
    re-cloning underneath them would strand every one of them.
    """
    target = REPOS_DIR / name
    if target.is_dir():
        default_branch = _git(target, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        return {"name": name, "path": str(target), "default_branch": default_branch}
    source = repo_clone_source(name)
    return fresh_clone(name, source) if source else None


def clone_available_repos(names: list[str]) -> dict[str, dict]:
    """Fresh-clone every repo in `names` that has a resolvable source.

    Returns {name: {name, path, default_branch}} for the repos that exist;
    missing ones are reported and skipped so the seed degrades gracefully.
    """
    clones: dict[str, dict] = {}
    for name in names:
        source = repo_clone_source(name)
        if source is None:
            print(f"repo {name}: no clone source (set SCULPTOR_DEMO_REPO_{name.upper()}) — skipping")
            continue
        clones[name] = fresh_clone(name, source)
        print(f"repo {name}: cloned {source} -> {clones[name]['path']} (branch {clones[name]['default_branch']})")
    return clones
