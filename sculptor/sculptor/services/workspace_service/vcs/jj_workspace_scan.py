"""Read every jj workspace of one repository in two commands, then project each workspace's identity from that read.

Both reads ignore the working copy, so they add no operation, take no lock and
work in a stale workspace. The revision read covers the union of every
workspace's stack, each measured from its own target, and records which
targets each revision descends to, so one workspace's stack is cut out of the
union without asking jj again.
"""

import json
from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmark
from sculptor.services.workspace_service.vcs.jj_data_types import JjHeadIdentity
from sculptor.services.workspace_service.vcs.jj_data_types import JjStackRevision
from sculptor.services.workspace_service.vcs.jj_repo_queries import list_bookmarks
from sculptor.services.workspace_service.vcs.jj_revsets import JjRevset
from sculptor.services.workspace_service.vcs.jj_revsets import is_full_commit_id
from sculptor.services.workspace_service.vcs.jj_revsets import parse_bookmark_symbol
from sculptor.services.workspace_service.vcs.jj_revsets import working_copy_revset
from sculptor.services.workspace_service.vcs.jj_stack_projection import project_jj_stack

# Far more revisions than any workspace's stack holds; it bounds a stack measured from no target.
_MAX_STACK_REVISIONS_PER_WORKSPACE = 500


class JjScannedRevision(FrozenModel):
    """One revision on the stack of at least one scanned workspace."""

    commit_id: str
    change_id: str
    change_id_prefix: str = Field(description="The shortest prefix that identifies the change uniquely")
    parent_commit_ids: tuple[str, ...]
    working_copy_names: tuple[str, ...] = Field(description="The workspaces whose working copy this revision is")
    bookmarks: tuple[str, ...] = Field(description="The local bookmarks on this revision; conflicted ones excluded")
    description: str
    is_empty: bool
    has_conflict: bool
    is_divergent: bool
    is_immutable: bool
    target_commit_ids_reached: frozenset[str] = Field(
        description="The scanned targets this revision is, or is an ancestor of"
    )

    @property
    def description_first_line(self) -> str:
        return self.description.split("\n", 1)[0]


class JjRepositoryScan(FrozenModel):
    """What two reads of a repository say about the workspaces they were asked about."""

    bookmarks: tuple[JjBookmark, ...] = Field(description="Every local bookmark and every bookmark on a real remote")
    revisions: tuple[JjScannedRevision, ...] = Field(description="The union of the scanned workspaces' stacks")
    target_commit_id_by_workspace: dict[str, str | None] = Field(
        description="The commit each scanned workspace's target names; None when it names none"
    )


def scan_jj_workspaces(
    jj: JjCli, repo_dir: Path, target_ref_by_workspace: Mapping[str, str | None]
) -> JjRepositoryScan:
    """Read every bookmark, then the stack of each named workspace, in `repo_dir`, any workspace root of the repository.

    A workspace the repository does not record, and a target that names no
    commit, are tolerated: the first has no revision in the scan, the second
    leaves its workspace's stack measured from its mutable ancestors.
    """
    bookmarks = tuple(list_bookmarks(jj, repo_dir))
    target_commit_id_by_workspace = {
        workspace_name: resolve_target_commit_id(target_ref, bookmarks)
        for workspace_name, target_ref in target_ref_by_workspace.items()
    }
    target_commit_ids = sorted({commit_id for commit_id in target_commit_id_by_workspace.values() if commit_id})
    result = jj.run(
        [
            "log",
            "--no-graph",
            "--limit",
            str(_MAX_STACK_REVISIONS_PER_WORKSPACE * len(target_ref_by_workspace)),
            "-r",
            _stacks_revset(target_commit_id_by_workspace),
            "-T",
            _scanned_revision_template(target_commit_ids),
        ],
        repo_dir,
        snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
    )
    revisions = tuple(
        _parse_scanned_revision(json.loads(line), target_commit_ids) for line in result.stdout.splitlines()
    )
    return JjRepositoryScan(
        bookmarks=bookmarks, revisions=revisions, target_commit_id_by_workspace=target_commit_id_by_workspace
    )


def resolve_target_commit_id(target_ref: str | None, bookmarks: Sequence[JjBookmark]) -> str | None:
    """The commit `target_ref`, a bookmark symbol or a full commit id, names; None when it is unset, malformed, absent or conflicted."""
    if target_ref is None:
        return None
    if is_full_commit_id(target_ref):
        return target_ref
    try:
        symbol = parse_bookmark_symbol(target_ref)
    except InvalidRevisionError:
        return None
    for bookmark in bookmarks:
        if bookmark.name == symbol.name and bookmark.remote == symbol.remote:
            return bookmark.commit_id
    return None


def project_jj_workspace_identity(
    scan: JjRepositoryScan, workspace_name: str, target_ref: str | None, requested_bookmark: str | None
) -> JjHeadIdentity | None:
    """The scanned workspace's working copy and the bookmarks on its stack; None when the scan has no working copy for it."""
    working_copy = next(
        (revision for revision in scan.revisions if workspace_name in revision.working_copy_names), None
    )
    if working_copy is None:
        return None
    target_commit_id = scan.target_commit_id_by_workspace.get(workspace_name)
    stack = [
        _to_stack_revision(revision)
        for revision in scan.revisions
        if revision.commit_id == working_copy.commit_id or _is_above_target(revision, target_commit_id)
    ]
    tracked_bookmark_names = {
        bookmark.name for bookmark in scan.bookmarks if bookmark.remote is not None and bookmark.is_tracked
    }
    projection = project_jj_stack(
        stack, working_copy.commit_id, requested_bookmark, _target_bookmark_name(target_ref), tracked_bookmark_names
    )
    return JjHeadIdentity(
        working_copy_change_id=working_copy.change_id,
        working_copy_change_id_prefix=working_copy.change_id_prefix,
        description_first_line=working_copy.description_first_line,
        is_working_copy_empty=working_copy.is_empty,
        bookmarks=projection.bookmarks,
        primary_bookmark=projection.primary_bookmark,
        unbookmarked_revision_count=projection.unbookmarked_revision_count,
        has_conflict=working_copy.has_conflict,
        is_divergent=working_copy.is_divergent,
    )


def name_pull_request_base(target_ref: str) -> str:
    """The branch a pull request into `target_ref` names as its base: the bookmark's name, so `main` for `main@origin`."""
    return _target_bookmark_name(target_ref) or target_ref


def _is_above_target(revision: JjScannedRevision, target_commit_id: str | None) -> bool:
    """Whether a revision of the scan belongs on a stack measured from `target_commit_id`; from its mutable ancestors without one."""
    if target_commit_id is None:
        return not revision.is_immutable
    return target_commit_id not in revision.target_commit_ids_reached


def _to_stack_revision(revision: JjScannedRevision) -> JjStackRevision:
    return JjStackRevision(
        commit_id=revision.commit_id,
        parent_commit_ids=revision.parent_commit_ids,
        bookmarks=revision.bookmarks,
        is_described=revision.description != "",
    )


def _target_bookmark_name(target_ref: str | None) -> str | None:
    """The bookmark name in a target symbol, such as `main` for `main@origin`."""
    if target_ref is None:
        return None
    try:
        return parse_bookmark_symbol(target_ref).name
    except InvalidRevisionError:
        return None


def _stacks_revset(target_commit_id_by_workspace: Mapping[str, str | None]) -> JjRevset:
    """Each workspace's working copy and its ancestors not reachable from its target; without one, its mutable ancestors."""
    stacks: list[str] = []
    for workspace_name, target_commit_id in target_commit_id_by_workspace.items():
        working_copy = f"present({working_copy_revset(workspace_name)})"
        if target_commit_id is None:
            stacks.append(f"(::{working_copy} & mutable()) | {working_copy}")
        else:
            stacks.append(f"(::{working_copy} ~ ::present({target_commit_id})) | {working_copy}")
    return JjRevset(" | ".join(f"({stack})" for stack in stacks))


def _scanned_revision_template(target_commit_ids: Sequence[str]) -> str:
    """One JSON array per line: the commit; the shortest unique change id prefix; the workspaces whose working
    copy it is; its unconflicted local bookmarks; the empty, conflict, divergent and immutable flags; then, for
    each of `target_commit_ids`, whether the commit is that target or one of its ancestors.
    """
    reached_flags = ' ++ "," ++ '.join(
        f'json(self.contained_in("::present({commit_id})"))' for commit_id in target_commit_ids
    )
    return (
        '"[" ++ json(self) ++ "," ++ json(change_id.shortest().prefix())'
        + ' ++ ",[" ++ working_copies.map(|w| json(w.name())).join(",") ++ "]"'
        + ' ++ ",[" ++ local_bookmarks.filter(|b| !b.conflict()).map(|b| json(b.name())).join(",") ++ "]"'
        + ' ++ "," ++ json(empty) ++ "," ++ json(conflict) ++ "," ++ json(divergent) ++ "," ++ json(immutable)'
        + (f' ++ ",[" ++ {reached_flags} ++ "]]\\n"' if reached_flags else ' ++ ",[]]\\n"')
    )


def _parse_scanned_revision(row: Sequence[Any], target_commit_ids: Sequence[str]) -> JjScannedRevision:
    (
        commit,
        change_id_prefix,
        working_copy_names,
        bookmarks,
        is_empty,
        has_conflict,
        is_divergent,
        is_immutable,
        reached,
    ) = row
    return JjScannedRevision(
        commit_id=commit["commit_id"],
        change_id=commit["change_id"],
        change_id_prefix=change_id_prefix,
        parent_commit_ids=tuple(commit["parents"]),
        working_copy_names=tuple(working_copy_names),
        bookmarks=tuple(bookmarks),
        description=commit["description"],
        is_empty=is_empty,
        has_conflict=has_conflict,
        is_divergent=is_divergent,
        is_immutable=is_immutable,
        target_commit_ids_reached=frozenset(
            commit_id for commit_id, is_reached in zip(target_commit_ids, reached, strict=True) if is_reached
        ),
    )
