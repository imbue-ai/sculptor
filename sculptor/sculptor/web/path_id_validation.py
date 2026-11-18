"""Turn the ids in a route's path into typed ids, answering 422 for a malformed one."""

import typeid.errors
from fastapi import HTTPException

from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.primitives.ids import TypeIDPrefixMismatchError
from sculptor.primitives.ids import WorkspaceID


def validate_project_id(project_id: str) -> ProjectID:
    """Validate and return a ProjectID, raising HTTPException if invalid."""
    try:
        return ProjectID(project_id)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["path", "project_id"],
                    "msg": f"Invalid project ID format: {project_id}",
                    "type": "value_error",
                }
            ],
        ) from e


def validate_task_id(task_id: str) -> TaskID:
    """Validate and return a TaskID, raising HTTPException if invalid."""
    try:
        return TaskID(task_id)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=[{"loc": ["path", "task_id"], "msg": f"Invalid task ID format: {task_id}", "type": "value_error"}],
        ) from e


def validate_workspace_id(workspace_id: str) -> WorkspaceID:
    """Validate and return a WorkspaceID, raising HTTPException if invalid."""
    try:
        return WorkspaceID(workspace_id)
    except (typeid.errors.TypeIDException, TypeIDPrefixMismatchError, ValueError) as e:
        raise HTTPException(
            status_code=422,
            detail=[
                {
                    "loc": ["path", "workspace_id"],
                    "msg": f"Invalid workspace ID format: {workspace_id}",
                    "type": "value_error",
                }
            ],
        ) from e
