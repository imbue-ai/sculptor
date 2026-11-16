"""Repository-level jj operations: colocation, bookmarks, trunk, commits, remotes and workspaces.

Reads pass `IGNORE_WORKING_COPY`, so they take no working-copy lock, add no
operation and never snapshot anyone's edits.
"""

import json
import re
from pathlib import Path
from typing import Any
from typing import Mapping
from typing import Sequence

from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmark
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmarkSymbol
from sculptor.services.workspace_service.vcs.jj_data_types import JjWorkspaceEntry
from sculptor.services.workspace_service.vcs.jj_revsets import JjRevset
from sculptor.services.workspace_service.vcs.jj_revsets import any_remote_bookmark_revset
from sculptor.services.workspace_service.vcs.jj_revsets import exact_string_pattern
from sculptor.services.workspace_service.vcs.jj_revsets import format_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import local_bookmark_revset

COLOCATION_INIT_TIMEOUT_SECONDS = 600.0

# jj mirrors the colocated git repository's own branches as bookmarks on this remote.
_GIT_TRACKING_REMOTE = "git"
_JSON_LINES_BOOKMARK_TEMPLATE = 'json(self) ++ "\\n"'
# The first line says whether the commit is the root commit; each later line is one of its remote bookmarks.
_ROOT_AND_REMOTE_BOOKMARKS_TEMPLATE = 'json(root) ++ "\\n" ++ remote_bookmarks.map(|b| json(b) ++ "\\n").join("")'
_TRUNK_FALLBACK_BOOKMARK_NAMES = ("main", "master")
# The `name` keyword prints jj's quoted display form for names that need quoting; `json(name)` is the raw name.
_WORKSPACE_LIST_TEMPLATE = 'json(name) ++ "\\t" ++ json(root) ++ "\\n"'
_WORKSPACE_CONFIG_ID_FILE = Path(".jj") / "workspace-config-id"
# `jj git remote list` appends this when a remote's push URL differs from its fetch URL.
_PUSH_URL_SUFFIX = re.compile(r" \(push: .*\)$")


def is_jj_colocated(jj: JjCli, repo_path: Path) -> bool:
    """Whether `repo_path` holds a jj repository colocated with its own `.git`."""
    if not (repo_path / ".jj" / "repo").is_dir() or not (repo_path / ".git").exists():
        return False
    result = jj.run(["git", "root"], repo_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY, is_checked=False)
    if result.returncode != 0:
        return False
    return Path(result.stdout.strip()).resolve() == (repo_path / ".git").resolve()


def init_colocated(jj: JjCli, repo_path: Path, *, timeout: float = COLOCATION_INIT_TIMEOUT_SECONDS) -> None:
    """Make the git repository at `repo_path` a colocated jj repository.

    Its checked-out git branch stays checked out, and no remote bookmark is
    tracked. Importing a large repository takes a while, hence the long timeout.
    """
    jj.run_outside_repository(["git", "init", "--colocate", str(repo_path)], repo_path, timeout=timeout)


def list_bookmarks(jj: JjCli, repo_dir: Path) -> list[JjBookmark]:
    """Every local bookmark and every bookmark on a real remote; conflicted ones are included and marked."""
    result = jj.run(
        ["bookmark", "list", "--all-remotes", "-T", _JSON_LINES_BOOKMARK_TEMPLATE],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )
    bookmarks = [_parse_bookmark(json.loads(line)) for line in result.stdout.splitlines()]
    return [bookmark for bookmark in bookmarks if bookmark.remote != _GIT_TRACKING_REMOTE]


def resolve_trunk_symbol(jj: JjCli, repo_dir: Path) -> str | None:
    """The bookmark symbol for the repository's trunk, such as `main@origin`.

    The first remote bookmark on `trunk()`; when `trunk()` is the root commit
    (no remote has a trunk), local `main`, then `master`. None otherwise,
    including when a user's `trunk()` alias names no commit.
    """
    result = jj.run(
        ["log", "--no-graph", "--limit", "1", "-r", "trunk()", "-T", _ROOT_AND_REMOTE_BOOKMARKS_TEMPLATE],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )
    lines = result.stdout.splitlines()
    if not lines:
        return None
    is_root_line, *bookmark_lines = lines
    if json.loads(is_root_line):
        return _find_local_trunk_fallback(jj, repo_dir)
    for line in bookmark_lines:
        bookmark = _parse_bookmark(json.loads(line))
        if bookmark.remote != _GIT_TRACKING_REMOTE:
            return format_bookmark_symbol(JjBookmarkSymbol(name=bookmark.name, remote=bookmark.remote))
    return None


def resolve_commit_id(jj: JjCli, repo_dir: Path, revset: JjRevset) -> str | None:
    """The id of the one commit `revset` names; None when it names none, several, or a commit that does not exist."""
    result = jj.run(
        ["log", "--no-graph", "--limit", "2", "-r", f"present({revset})", "-T", 'commit_id ++ "\\n"'],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )
    commit_ids = result.stdout.split()
    if len(commit_ids) != 1:
        return None
    return commit_ids[0]


def does_bookmark_exist(jj: JjCli, repo_dir: Path, name: str) -> bool:
    """Whether a bookmark called `name` exists locally or on any remote."""
    revset = f"{local_bookmark_revset(name)} | {any_remote_bookmark_revset(name)}"
    result = jj.run(
        ["log", "--no-graph", "--limit", "1", "-r", revset, "-T", '"found"'],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )
    return result.stdout != ""


def read_remotes(jj: JjCli, repo_dir: Path) -> dict[str, str]:
    """Each remote's fetch URL, by remote name."""
    result = jj.run(["git", "remote", "list"], repo_dir, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)
    remotes: dict[str, str] = {}
    for line in result.stdout.splitlines():
        name, _, urls = line.partition(" ")
        remotes[name] = _PUSH_URL_SUFFIX.sub("", urls)
    return remotes


def forget_bookmarks(jj: JjCli, repo_dir: Path, names: Sequence[str]) -> None:
    """Forget each named local bookmark together with its remote-tracking bookmarks.

    The branches on the remotes are left alone, and a later fetch lists them
    again as untracked remote bookmarks. `jj bookmark delete` would instead
    schedule their deletion on the next push.
    """
    if not names:
        return
    jj.run(
        ["bookmark", "forget", "--include-remotes", *(exact_string_pattern(name) for name in names)],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )


def list_workspaces(jj: JjCli, repo_dir: Path) -> list[JjWorkspaceEntry]:
    """Every workspace the repository records, including ones whose directory has been deleted."""
    result = jj.run(
        ["workspace", "list", "-T", _WORKSPACE_LIST_TEMPLATE], repo_dir, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY
    )
    entries: list[JjWorkspaceEntry] = []
    for line in result.stdout.splitlines():
        name, root = line.split("\t")
        entries.append(JjWorkspaceEntry(name=json.loads(name), root=Path(json.loads(root))))
    return entries


def add_workspace(jj: JjCli, repo_path: Path, *, name: str, base_revset: JjRevset, destination: Path) -> None:
    """Create a jj-only workspace (`.jj` and no `.git`) at `destination`, its working copy a new child of `base_revset`.

    Runs in the main repository and snapshots its working copy, because
    `jj workspace add` refuses `--ignore-working-copy`. `destination`'s parent
    must exist. A taken name or a non-empty destination raises
    `VcsCommandExitError`.
    """
    jj.run(
        [
            "workspace",
            "add",
            "--no-colocate",
            "--name",
            name,
            "-r",
            base_revset,
            "--sparse-patterns",
            "full",
            str(destination),
        ],
        repo_path,
        snapshot=JjSnapshotPolicy.SNAPSHOT,
    )


def forget_workspace(jj: JjCli, repo_path: Path, name: str) -> None:
    """Stop the repository tracking the workspace `name`; its directory and its workspace config are left alone.

    Succeeds when the directory is already gone and when no workspace has that name.
    """
    jj.run(["workspace", "forget", name], repo_path, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)


def set_workspace_config(jj: JjCli, workspace_root: Path, key: str, value: str) -> None:
    """Set `key` in the workspace's own jj config, read by every jj process in that workspace and no other.

    Creates no operation. The file lives under the user's jj config directory,
    and `jj workspace forget` leaves it behind.
    """
    jj.run(["config", "set", "--workspace", key, value], workspace_root, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)


def read_workspace_config_path(jj: JjCli, workspace_root: Path) -> Path | None:
    """The workspace's own config file, or None when the workspace has never had one.

    `jj config path --workspace` creates the config directory as a side effect,
    so it runs only when `.jj/workspace-config-id` shows the directory exists.
    """
    if not (workspace_root / _WORKSPACE_CONFIG_ID_FILE).exists():
        return None
    result = jj.run(["config", "path", "--workspace"], workspace_root, snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY)
    return Path(result.stdout.strip())


def update_stale(jj: JjCli, workspace_root: Path) -> None:
    """Bring a stale workspace's working copy up to date with the repository."""
    jj.run(["workspace", "update-stale"], workspace_root, snapshot=JjSnapshotPolicy.SNAPSHOT)


def _find_local_trunk_fallback(jj: JjCli, repo_dir: Path) -> str | None:
    for name in _TRUNK_FALLBACK_BOOKMARK_NAMES:
        if resolve_commit_id(jj, repo_dir, local_bookmark_revset(name)) is not None:
            return name
    return None


def _parse_bookmark(row: Mapping[str, Any]) -> JjBookmark:
    """A `json(self)` bookmark row: local rows hold `name` and `target`; remote rows add `remote`,
    and `tracking_target` when a local bookmark tracks them."""
    return JjBookmark(
        name=row["name"],
        remote=row.get("remote"),
        target_commit_ids=tuple(row["target"]),
        is_tracked="tracking_target" in row,
    )
