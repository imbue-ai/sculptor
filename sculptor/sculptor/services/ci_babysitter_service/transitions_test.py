from typing import Literal

from sculptor.primitives.ids import WorkspaceID
from sculptor.services.ci_babysitter_service.transitions import Transition
from sculptor.services.ci_babysitter_service.transitions import classify_transitions
from sculptor.web.derived import PrStatusInfo

WORKSPACE_ID = WorkspaceID()


def _make_status(
    pr_state: Literal["none", "open", "merged", "closed"] = "open",
    pipeline_status: Literal["running", "passed", "failed"] | None = None,
    pipeline_id: int | None = None,
    has_conflicts: bool | None = None,
) -> PrStatusInfo:
    return PrStatusInfo(
        workspace_id=WORKSPACE_ID,
        pr_state=pr_state,
        pipeline_status=pipeline_status,
        pipeline_id=pipeline_id,
        has_conflicts=has_conflicts,
    )


def test_pipeline_failed_does_not_fire_from_none_prev() -> None:
    # First-poll baseline: a failed pipeline observed on the very first
    # poll for a workspace is the baseline, not a transition. This avoids
    # burning a retry on Sculptor restart against an already-red PR.
    new = _make_status(pipeline_status="failed", pipeline_id=1)
    assert classify_transitions(None, new) == []


def test_pipeline_failed_no_duplicate_on_same_pipeline() -> None:
    prev = _make_status(pipeline_status="failed", pipeline_id=1)
    new = _make_status(pipeline_status="failed", pipeline_id=1)
    assert classify_transitions(prev, new) == []


def test_pipeline_failed_fires_on_new_pipeline_id() -> None:
    prev = _make_status(pipeline_status="failed", pipeline_id=1)
    new = _make_status(pipeline_status="failed", pipeline_id=2)
    assert classify_transitions(prev, new) == [Transition.PIPELINE_FAILED]


def test_pipeline_failed_from_running() -> None:
    prev = _make_status(pipeline_status="running")
    new = _make_status(pipeline_status="failed", pipeline_id=2)
    assert classify_transitions(prev, new) == [Transition.PIPELINE_FAILED]


def test_pipeline_failed_to_running_is_silent() -> None:
    prev = _make_status(pipeline_status="failed", pipeline_id=1)
    new = _make_status(pipeline_status="running")
    assert classify_transitions(prev, new) == []


def test_pipeline_passed_from_none() -> None:
    new = _make_status(pipeline_status="passed")
    assert classify_transitions(None, new) == [Transition.PIPELINE_PASSED]


def test_pipeline_passed_from_failed() -> None:
    prev = _make_status(pipeline_status="failed", pipeline_id=1)
    new = _make_status(pipeline_status="passed")
    assert classify_transitions(prev, new) == [Transition.PIPELINE_PASSED]


def test_pipeline_passed_no_duplicate() -> None:
    prev = _make_status(pipeline_status="passed")
    new = _make_status(pipeline_status="passed")
    assert classify_transitions(prev, new) == []


def test_merge_conflict_fires_from_none_prev() -> None:
    # SCU-1361: a merge conflict already present on the very first poll
    # (prev is None) MUST surface. A branch cut from a stale main conflicts
    # within seconds, so by the first poll has_conflicts is already True; and
    # the coordinator's prev_status is in-memory, so any restart against an
    # already-conflicted PR re-enters here with prev is None too. Unlike
    # PIPELINE_FAILED (which re-arms on a new pipeline_id), the conflict edge
    # never re-arms in-process once prev.has_conflicts is True, so suppressing
    # it on the first poll means it is never surfaced at all. Level-trigger it
    # instead; the coordinator's per-conflict dispatch dedup prevents spam.
    new = _make_status(has_conflicts=True)
    assert classify_transitions(None, new) == [Transition.MERGE_CONFLICT]


def test_merge_conflict_from_unknown_prev() -> None:
    prev = _make_status(has_conflicts=None)
    new = _make_status(has_conflicts=True)
    assert classify_transitions(prev, new) == [Transition.MERGE_CONFLICT]


def test_merge_conflict_no_duplicate() -> None:
    prev = _make_status(has_conflicts=True)
    new = _make_status(has_conflicts=True)
    assert classify_transitions(prev, new) == []


def test_merge_conflict_resolved_is_silent() -> None:
    prev = _make_status(has_conflicts=True)
    new = _make_status(has_conflicts=False)
    assert classify_transitions(prev, new) == []


def test_merge_conflict_appears_from_false() -> None:
    prev = _make_status(has_conflicts=False)
    new = _make_status(has_conflicts=True)
    assert classify_transitions(prev, new) == [Transition.MERGE_CONFLICT]


def test_simultaneous_pipeline_failed_and_merge_conflict() -> None:
    # First-poll baseline suppresses both PIPELINE_FAILED and MERGE_CONFLICT.
    # They must fire on the next non-baseline diff: here, a new failed
    # pipeline id arriving with conflicts still present.
    baseline = _make_status(pipeline_status="passed", pipeline_id=1, has_conflicts=False)
    new = _make_status(pipeline_status="failed", pipeline_id=2, has_conflicts=True)
    assert classify_transitions(baseline, new) == [Transition.PIPELINE_FAILED, Transition.MERGE_CONFLICT]


def test_mr_merged() -> None:
    prev = _make_status(pr_state="open")
    new = _make_status(pr_state="merged")
    assert classify_transitions(prev, new) == [Transition.MR_MERGED]


def test_mr_closed() -> None:
    prev = _make_status(pr_state="open")
    new = _make_status(pr_state="closed")
    assert classify_transitions(prev, new) == [Transition.MR_CLOSED]


def test_mr_merged_no_duplicate() -> None:
    prev = _make_status(pr_state="merged")
    new = _make_status(pr_state="merged")
    assert classify_transitions(prev, new) == []
