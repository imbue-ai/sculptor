"""Which bookmarks name a jj workspace's work, derived from its stack alone.

A workspace's stack is the revisions between its target and its working copy.
jj workspaces carry 0, 1 or many bookmarks, so Sculptor ranks them: nearest
the working copy first; on one revision, the requested name, then names that
track a remote, then alphabetical. The primary bookmark is the first that is not
the target's own name.
"""

from collections import deque
from collections.abc import Mapping
from collections.abc import Sequence
from collections.abc import Set as AbstractSet

from sculptor.services.workspace_service.vcs.jj_data_types import JjStackProjection
from sculptor.services.workspace_service.vcs.jj_data_types import JjStackRevision


def project_jj_stack(
    revisions: Sequence[JjStackRevision],
    working_copy_commit_id: str,
    requested_bookmark: str | None,
    target_bookmark_name: str | None,
    tracked_bookmark_names: AbstractSet[str] = frozenset(),
) -> JjStackProjection:
    """Rank the bookmarks on the stack ending at `working_copy_commit_id`.

    `revisions` are the stack's revisions; any not reachable from the working
    copy through their parents are ignored. `tracked_bookmark_names` are the
    local bookmarks that track a remote bookmark.
    """
    revision_by_commit_id = {revision.commit_id: revision for revision in revisions}
    distance_by_commit_id = _distances_from(working_copy_commit_id, revision_by_commit_id)
    ranked = sorted(
        (distance, bookmark != requested_bookmark, bookmark not in tracked_bookmark_names, bookmark, commit_id)
        for commit_id, distance in distance_by_commit_id.items()
        for bookmark in revision_by_commit_id[commit_id].bookmarks
    )
    commit_id_by_candidate = {
        bookmark: commit_id for *_, bookmark, commit_id in ranked if bookmark != target_bookmark_name
    }
    primary_commit_id = next(iter(commit_id_by_candidate.values()), None)
    return JjStackProjection(
        bookmarks=tuple(bookmark for *_, bookmark, _ in ranked),
        pr_head_candidates=tuple(commit_id_by_candidate),
        unbookmarked_revision_count=_count_described_revisions_above(
            primary_commit_id, distance_by_commit_id.keys(), revision_by_commit_id
        ),
        newest_described_commit_ids=_find_newest_described_revisions(distance_by_commit_id, revision_by_commit_id),
    )


def _distances_from(start_commit_id: str, revision_by_commit_id: Mapping[str, JjStackRevision]) -> dict[str, int]:
    """The fewest parent steps from `start_commit_id` to each revision reachable from it."""
    if start_commit_id not in revision_by_commit_id:
        return {}
    distance_by_commit_id = {start_commit_id: 0}
    queue = deque([start_commit_id])
    while queue:
        commit_id = queue.popleft()
        for parent_commit_id in revision_by_commit_id[commit_id].parent_commit_ids:
            if parent_commit_id in distance_by_commit_id or parent_commit_id not in revision_by_commit_id:
                continue
            distance_by_commit_id[parent_commit_id] = distance_by_commit_id[commit_id] + 1
            queue.append(parent_commit_id)
    return distance_by_commit_id


def _count_described_revisions_above(
    primary_commit_id: str | None,
    reachable_commit_ids: AbstractSet[str],
    revision_by_commit_id: Mapping[str, JjStackRevision],
) -> int:
    """Described reachable revisions that descend from `primary_commit_id`; all of them when it is None."""
    if primary_commit_id is None:
        counted_commit_ids = reachable_commit_ids
    else:
        counted_commit_ids = _descendants_of(primary_commit_id, reachable_commit_ids, revision_by_commit_id)
    return sum(1 for commit_id in counted_commit_ids if revision_by_commit_id[commit_id].is_described)


def _find_newest_described_revisions(
    distance_by_commit_id: Mapping[str, int], revision_by_commit_id: Mapping[str, JjStackRevision]
) -> tuple[str, ...]:
    """The described reachable revisions that no other described one descends from, nearest the working copy first."""
    reachable_commit_ids = distance_by_commit_id.keys()
    described_commit_ids = {
        commit_id for commit_id in reachable_commit_ids if revision_by_commit_id[commit_id].is_described
    }
    newest = [
        commit_id
        for commit_id in described_commit_ids
        if not described_commit_ids & _descendants_of(commit_id, reachable_commit_ids, revision_by_commit_id)
    ]
    return tuple(sorted(newest, key=lambda commit_id: (distance_by_commit_id[commit_id], commit_id)))


def _descendants_of(
    ancestor_commit_id: str,
    reachable_commit_ids: AbstractSet[str],
    revision_by_commit_id: Mapping[str, JjStackRevision],
) -> set[str]:
    """The reachable revisions that have `ancestor_commit_id` as a proper ancestor."""
    children_by_commit_id: dict[str, list[str]] = {}
    for commit_id in reachable_commit_ids:
        for parent_commit_id in revision_by_commit_id[commit_id].parent_commit_ids:
            children_by_commit_id.setdefault(parent_commit_id, []).append(commit_id)
    descendants: set[str] = set()
    queue = deque(children_by_commit_id.get(ancestor_commit_id, []))
    while queue:
        commit_id = queue.popleft()
        if commit_id in descendants:
            continue
        descendants.add(commit_id)
        queue.extend(children_by_commit_id.get(commit_id, []))
    return descendants
