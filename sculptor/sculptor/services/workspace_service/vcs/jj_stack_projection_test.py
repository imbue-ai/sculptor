from collections.abc import Sequence

from sculptor.services.workspace_service.vcs.jj_data_types import JjStackRevision
from sculptor.services.workspace_service.vcs.jj_stack_projection import project_jj_stack

_FORK_POINT = "f" * 40


def _revision(
    commit_id: str, parents: Sequence[str], bookmarks: Sequence[str] = (), is_described: bool = True
) -> JjStackRevision:
    return JjStackRevision(
        commit_id=commit_id,
        parent_commit_ids=tuple(parents),
        bookmarks=tuple(bookmarks),
        is_described=is_described,
    )


def _linear_stack(*bookmarks_by_revision: Sequence[str]) -> list[JjStackRevision]:
    """Revisions `c0` (the working copy) down to `c<n-1>` (just above the fork point), newest first."""
    count = len(bookmarks_by_revision)
    return [
        _revision(f"c{index}", [f"c{index + 1}" if index + 1 < count else _FORK_POINT], bookmarks)
        for index, bookmarks in enumerate(bookmarks_by_revision)
    ]


def test_a_stack_without_bookmarks_has_no_primary_and_counts_every_described_revision() -> None:
    revisions = [
        _revision("c0", ["c1"], is_described=False),
        _revision("c1", ["c2"]),
        _revision("c2", [_FORK_POINT]),
    ]

    projection = project_jj_stack(revisions, "c0", requested_bookmark="feat", target_bookmark_name="main")

    assert projection.bookmarks == ()
    assert projection.pr_head_candidates == ()
    assert projection.primary_bookmark is None
    assert projection.unbookmarked_revision_count == 2


def test_a_single_bookmark_is_primary_and_counts_the_described_revisions_above_it() -> None:
    revisions = [
        _revision("c0", ["c1"], is_described=False),
        _revision("c1", ["c2"]),
        _revision("c2", ["c3"], bookmarks=["feat"]),
        _revision("c3", [_FORK_POINT]),
    ]

    projection = project_jj_stack(revisions, "c0", requested_bookmark=None, target_bookmark_name="main")

    assert projection.bookmarks == ("feat",)
    assert projection.primary_bookmark == "feat"
    assert projection.unbookmarked_revision_count == 1


def test_a_bookmark_on_the_working_copy_leaves_nothing_unbookmarked() -> None:
    projection = project_jj_stack(_linear_stack(["feat"], []), "c0", None, "main")

    assert projection.primary_bookmark == "feat"
    assert projection.unbookmarked_revision_count == 0


def test_bookmarks_are_ordered_nearest_the_working_copy_first() -> None:
    projection = project_jj_stack(_linear_stack([], ["upper"], [], ["lower"]), "c0", "lower", "main")

    assert projection.bookmarks == ("upper", "lower")
    assert projection.pr_head_candidates == ("upper", "lower")
    assert projection.primary_bookmark == "upper"


def test_a_tie_on_one_revision_prefers_the_requested_name_then_tracked_names_then_alphabetical() -> None:
    revisions = _linear_stack(["zeta", "beta", "alpha", "tracked", "requested"])

    projection = project_jj_stack(
        revisions, "c0", "requested", "main", tracked_bookmark_names=frozenset({"tracked", "zeta"})
    )

    assert projection.bookmarks == ("requested", "tracked", "zeta", "alpha", "beta")


def test_a_tie_without_a_requested_or_tracked_name_is_alphabetical() -> None:
    projection = project_jj_stack(_linear_stack(["b", "a", "c"]), "c0", None, None)

    assert projection.bookmarks == ("a", "b", "c")


def test_the_targets_own_name_is_listed_but_never_primary_or_a_pull_request_head() -> None:
    projection = project_jj_stack(_linear_stack(["main"], ["feat"]), "c0", None, "main")

    assert projection.bookmarks == ("main", "feat")
    assert projection.pr_head_candidates == ("feat",)
    assert projection.primary_bookmark == "feat"
    assert projection.unbookmarked_revision_count == 1


def test_a_stack_whose_only_bookmark_is_the_targets_name_has_no_primary() -> None:
    projection = project_jj_stack(_linear_stack(["main"]), "c0", None, "main")

    assert projection.bookmarks == ("main",)
    assert projection.primary_bookmark is None
    assert projection.unbookmarked_revision_count == 1


def test_distance_through_a_merge_is_the_shortest_path_to_the_working_copy() -> None:
    revisions = [
        _revision("merge", ["short_side", "long_side_1"]),
        _revision("short_side", ["shared"]),
        _revision("long_side_1", ["long_side_2"]),
        _revision("long_side_2", ["long_side_3"]),
        _revision("long_side_3", ["shared"], bookmarks=["deep_on_the_long_side"]),
        _revision("shared", [_FORK_POINT], bookmarks=["shared"]),
    ]

    projection = project_jj_stack(revisions, "merge", None, "main")

    assert projection.bookmarks == ("shared", "deep_on_the_long_side")


def test_only_revisions_reachable_from_the_working_copy_count() -> None:
    revisions = [*_linear_stack([], ["feat"]), _revision("elsewhere", [_FORK_POINT], bookmarks=["unrelated"])]

    projection = project_jj_stack(revisions, "c0", None, "main")

    assert projection.bookmarks == ("feat",)
    assert projection.unbookmarked_revision_count == 1


def test_described_revisions_count_only_when_they_descend_from_the_primary_bookmark() -> None:
    revisions = [
        _revision("merge", ["bookmarked", "side"], is_described=False),
        _revision("bookmarked", [_FORK_POINT], bookmarks=["feat"]),
        _revision("side", [_FORK_POINT]),
    ]

    projection = project_jj_stack(revisions, "merge", None, "main")

    assert projection.primary_bookmark == "feat"
    assert projection.unbookmarked_revision_count == 0


def test_the_newest_described_revision_of_a_linear_stack_is_the_highest_described_one() -> None:
    revisions = [
        _revision("c0", ["c1"], is_described=False),
        _revision("c1", ["c2"]),
        _revision("c2", [_FORK_POINT]),
    ]

    projection = project_jj_stack(revisions, "c0", None, "main")

    assert projection.newest_described_commit_ids == ("c1",)


def test_a_described_working_copy_is_the_newest_described_revision() -> None:
    projection = project_jj_stack(_linear_stack([], []), "c0", None, "main")

    assert projection.newest_described_commit_ids == ("c0",)


def test_a_stack_with_no_described_revision_has_no_newest_described_revision() -> None:
    revisions = [_revision("c0", ["c1"], is_described=False), _revision("c1", [_FORK_POINT], is_described=False)]

    projection = project_jj_stack(revisions, "c0", None, "main")

    assert projection.newest_described_commit_ids == ()


def test_an_undescribed_merge_of_described_sides_has_a_newest_described_revision_on_each_side() -> None:
    revisions = [
        _revision("merge", ["near_side", "far_side_1"], is_described=False),
        _revision("near_side", ["shared"]),
        _revision("far_side_1", ["far_side_2"]),
        _revision("far_side_2", ["shared"]),
        _revision("shared", [_FORK_POINT]),
    ]

    projection = project_jj_stack(revisions, "merge", None, "main")

    assert projection.newest_described_commit_ids == ("far_side_1", "near_side")
