"""Low-level, domain-agnostic primitives for cheaply detecting git ref changes.

These are the mechanics behind ``WorkspaceService``'s branch poller, which watches
two facts per live workspace: its current branch (its ``HEAD``) and its repo's
remote-tracking branches (keyed by common git dir, so each repo is scanned once).

Everything here returns plain values (paths, strings, change-signatures) and
forks ``git`` only as a fallback — it has no notion of workspaces, projects, or
the streaming types, so it does not pull the web layer into the services.

The "stat-first" idea: stat the ref files and compare a cheap signature; only
read/fork when it moved. An idle scan touches the filesystem but forks nothing.
"""

import os
from pathlib import Path

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.git_repo_service.default_implementation import LocalReadOnlyGitRepo
from sculptor.services.git_repo_service.error_types import GitRepoError
from sculptor.services.git_repo_service.error_types import GitRepoNotFoundError

# A cheap "did this file change" signature: modification time + size. Compared by
# value, never interpreted — any change in either field forces a re-read.
StatSignature = tuple[int, int]

# Signature for a repo's remote-tracking refs: packed-refs (where git stows refs
# after fetch/gc) plus a walk of loose refs under refs/remotes (count + newest
# mtime). Together these move when a remote branch is added/removed/updated by
# either storage path.
RemoteRefsSignature = tuple[StatSignature | None, int, int]


def stat_signature(path: Path) -> StatSignature | None:
    """Return a change-signature for ``path``, or None if it does not exist."""
    try:
        stat_result = path.stat()
    except OSError:
        return None
    return (stat_result.st_mtime_ns, stat_result.st_size)


def resolve_git_dirs(working_dir: Path) -> tuple[Path, Path] | None:
    """Resolve a working dir to its ``(git_dir, common_dir)`` by reading files, not forking git.

    For a normal checkout both are ``<working_dir>/.git``. For a linked worktree,
    ``.git`` is a file pointing at ``<common>/.git/worktrees/<name>`` (the git_dir,
    which owns this worktree's ``HEAD``); the common dir — which owns ``refs/remotes``
    and ``packed-refs``, shared across all worktrees of the repo — is read from the
    git_dir's ``commondir`` file.

    Returns None if ``working_dir`` is not (or no longer) a git checkout, so a
    caller can skip a vanished directory without ever forking git.
    """
    dot_git = working_dir / ".git"
    if dot_git.is_dir():
        return dot_git, dot_git
    if not dot_git.is_file():
        return None
    try:
        text = dot_git.read_text().strip()
    except OSError:
        return None
    if not text.startswith("gitdir:"):
        return None
    git_dir = Path(text[len("gitdir:") :].strip())
    if not git_dir.is_absolute():
        git_dir = (working_dir / git_dir).resolve()
    commondir_file = git_dir / "commondir"
    common_dir = git_dir
    try:
        if commondir_file.is_file():
            relative_or_absolute = commondir_file.read_text().strip()
            candidate = Path(relative_or_absolute)
            common_dir = candidate if candidate.is_absolute() else (git_dir / candidate).resolve()
    except OSError:
        common_dir = git_dir
    return git_dir, common_dir


def remote_refs_signature(common_dir: Path) -> RemoteRefsSignature:
    """Change-signature for a repo's remote-tracking refs (see ``RemoteRefsSignature``)."""
    packed = stat_signature(common_dir / "packed-refs")
    remotes_dir = common_dir / "refs" / "remotes"
    loose_count = 0
    newest_mtime_ns = 0
    try:
        for dirpath, _dirnames, filenames in os.walk(remotes_dir):
            for filename in filenames:
                loose_count += 1
                signature = stat_signature(Path(dirpath) / filename)
                if signature is not None and signature[0] > newest_mtime_ns:
                    newest_mtime_ns = signature[0]
    except OSError:
        pass
    return (packed, loose_count, newest_mtime_ns)


def read_current_branch(working_dir: Path, git_dir: Path, concurrency_group: ConcurrencyGroup) -> str | None:
    """Read the current branch, parsing ``HEAD`` directly and only forking git when needed.

    The overwhelmingly common case — ``HEAD`` is a symbolic ref to a local branch
    — is satisfied by a single file read. Detached HEAD and other shapes fall back
    to ``git`` so edge cases stay correct. Returns None when there is no current
    branch yet (unborn HEAD) or the repo is transiently unreadable.
    """
    try:
        head_text = (git_dir / "HEAD").read_text().strip()
    except OSError:
        head_text = ""
    symbolic_ref_prefix = "ref: refs/heads/"
    if head_text.startswith(symbolic_ref_prefix):
        return head_text[len(symbolic_ref_prefix) :].strip() or None

    repo = LocalReadOnlyGitRepo(repo_path=working_dir, concurrency_group=concurrency_group, log_command=False)
    try:
        return repo.get_current_git_branch()
    except GitRepoNotFoundError:
        return None
    except GitRepoError:
        return None
