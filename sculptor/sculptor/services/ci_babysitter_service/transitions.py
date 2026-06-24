from enum import StrEnum

from sculptor.web.data_types import PrStatusInfo


class Transition(StrEnum):
    PIPELINE_FAILED = "PIPELINE_FAILED"
    MERGE_CONFLICT = "MERGE_CONFLICT"
    PIPELINE_PASSED = "PIPELINE_PASSED"
    MR_MERGED = "MR_MERGED"
    MR_CLOSED = "MR_CLOSED"


def classify_transitions(prev: PrStatusInfo | None, new: PrStatusInfo) -> list[Transition]:
    transitions: list[Transition] = []

    # First-poll baseline (architecture: "Risks and Mitigations"):
    # PIPELINE_FAILED MUST NOT fire when prev is None, so a Sculptor restart
    # against an already-red pipeline doesn't burn a retry before any real
    # signal arrives. A still-failing pipeline self-heals: the next push
    # produces a new pipeline_id, which re-arms the edge below.
    if new.pipeline_status == "failed" and prev is not None:
        if prev.pipeline_status != "failed" or prev.pipeline_id != new.pipeline_id:
            transitions.append(Transition.PIPELINE_FAILED)

    # MERGE_CONFLICT must surface on first observation (SCU-1361), unlike
    # PIPELINE_FAILED. A conflict is commonly already present the first time we
    # observe the PR -- a branch cut from a stale main conflicts within seconds,
    # well before the ~30s first poll -- and the coordinator's prev_status is
    # in-memory, so a restart re-enters with prev is None against the same
    # conflict. A failed pipeline self-heals because the next push yields a new
    # pipeline_id that re-arms its edge; a conflict has no such id, so once
    # prev.has_conflicts is True the old "prev is not None" edge never re-armed
    # in-process and the prompt was never sent. So fire on prev is None too. We
    # still suppress the true->true repeat here (don't emit every poll); the
    # coordinator's last_dispatched_merge_conflict is the hard dedup that fires
    # exactly once per conflict episode and re-arms when has_conflicts is False.
    if new.has_conflicts is True:
        if prev is None or prev.has_conflicts is not True:
            transitions.append(Transition.MERGE_CONFLICT)

    if new.pipeline_status == "passed":
        if prev is None or prev.pipeline_status != "passed":
            transitions.append(Transition.PIPELINE_PASSED)

    if new.pr_state == "merged":
        if prev is None or prev.pr_state != "merged":
            transitions.append(Transition.MR_MERGED)

    if new.pr_state == "closed":
        if prev is None or prev.pr_state != "closed":
            transitions.append(Transition.MR_CLOSED)

    return transitions
