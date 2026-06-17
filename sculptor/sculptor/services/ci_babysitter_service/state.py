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
