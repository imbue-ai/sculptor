from sculptor.database.models import TaskID
from sculptor.foundation.pydantic_serialization import MutableModel
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.web.data_types import PrStatusInfo


class CIBabysitterState(MutableModel):
    workspace_id: WorkspaceID
    project_id: ProjectID
    paused: bool = False
    retry_count: int = 0
    babysitter_task_id: TaskID | None = None
    retired: bool = False
    prev_status: PrStatusInfo | None = None
    # Idempotency: the pipeline_id we last dispatched a PIPELINE_FAILED
    # prompt for. A new pipeline (different id) re-arms the dispatch.
    last_dispatched_pipeline_failed_id: int | None = None
    # Idempotency: True once we've dispatched a MERGE_CONFLICT prompt
    # for the current conflict. Reset to False the moment we observe
    # has_conflicts=False (conflict resolved). A subsequent re-conflict
    # then re-arms the dispatch.
    last_dispatched_merge_conflict: bool = False
    # A one-off, runtime reason the most recent terminal drive couldn't
    # deliver (e.g. the program wasn't at its prompt). Set/cleared by the
    # terminal-drive worker; cleared again once the CI cycle resolves.
    transient_disabled_reason: str | None = None
    # Overlapping-drive guard: True while a terminal-drive worker is writing
    # this workspace's PTY, so a second near-simultaneous failure coalesces
    # instead of starting a racing worker.
    terminal_drive_in_progress: bool = False
