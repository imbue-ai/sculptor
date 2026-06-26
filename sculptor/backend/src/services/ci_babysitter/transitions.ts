// CI babysitter transition classifier (services/ci_babysitter_service/transitions.py).
// A pure function over two consecutive PR/MR status snapshots that names the
// actionable transitions. The first-poll baseline rules below are load-bearing:
// PIPELINE_FAILED must not fire on a null prev (a restart against an already-red
// pipeline shouldn't burn a retry), but MERGE_CONFLICT must (a conflict commonly
// predates the first poll and has no id to re-arm on).

export type Transition =
  | "PIPELINE_FAILED"
  | "MERGE_CONFLICT"
  | "PIPELINE_PASSED"
  | "MR_MERGED"
  | "MR_CLOSED";

export interface PrStatusLike {
  pr_state?: string | null;
  pipeline_status?: string | null;
  pipeline_id?: number | null;
  has_conflicts?: boolean | null;
}

export function classifyTransitions(
  prev: PrStatusLike | null,
  next: PrStatusLike,
): Transition[] {
  const transitions: Transition[] = [];

  // PIPELINE_FAILED MUST NOT fire when prev is null, so a Sculptor restart
  // against an already-red pipeline doesn't burn a retry before any real signal
  // arrives. A still-failing pipeline self-heals: the next push produces a new
  // pipeline_id, which re-arms the edge below.
  if (next.pipeline_status === "failed" && prev !== null) {
    if (
      prev.pipeline_status !== "failed" ||
      prev.pipeline_id !== next.pipeline_id
    ) {
      transitions.push("PIPELINE_FAILED");
    }
  }

  // MERGE_CONFLICT must surface on first observation (SCU-1361), unlike
  // PIPELINE_FAILED. A conflict is commonly already present the first time the
  // MR is observed and has no pipeline_id to re-arm on, so fire on prev null too.
  // The true->true repeat is suppressed here; the coordinator's
  // last_dispatched_merge_conflict is the hard once-per-episode dedup.
  if (next.has_conflicts === true) {
    if (prev === null || prev.has_conflicts !== true) {
      transitions.push("MERGE_CONFLICT");
    }
  }

  if (next.pipeline_status === "passed") {
    if (prev === null || prev.pipeline_status !== "passed") {
      transitions.push("PIPELINE_PASSED");
    }
  }

  if (next.pr_state === "merged") {
    if (prev === null || prev.pr_state !== "merged") {
      transitions.push("MR_MERGED");
    }
  }

  if (next.pr_state === "closed") {
    if (prev === null || prev.pr_state !== "closed") {
      transitions.push("MR_CLOSED");
    }
  }

  return transitions;
}
