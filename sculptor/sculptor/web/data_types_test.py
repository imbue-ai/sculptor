"""Unit tests for sculptor.web.data_types."""

import pytest
from pydantic import ValidationError

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import WorkspaceID
from sculptor.state.messages import LLMModel
from sculptor.web.data_types import CreateWorkspaceRequestV2
from sculptor.web.data_types import JjColocationState
from sculptor.web.data_types import ProjectJjState
from sculptor.web.data_types import SendMessageRequest
from sculptor.web.data_types import StartTaskRequest
from sculptor.web.data_types import WorkspaceJjStateInfo


def test_create_workspace_request_has_no_harness_field() -> None:
    # Agent type is per-agent; the workspace carries no harness.
    request = CreateWorkspaceRequestV2(
        project_id="proj-1",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )
    assert "harness" not in type(request).model_fields


def test_start_task_request_defaults_agent_type_to_none() -> None:
    # None means "resolve the user's most-recently-used harness" server-side
    # (defaulting to Claude); it is no longer hardcoded to Claude on the model.
    request = StartTaskRequest(prompt="hello", model=LLMModel.CLAUDE_4_SONNET)
    assert request.agent_type is None


def test_a_request_naming_a_200k_variant_creates_records_with_its_1m_sibling() -> None:
    # A stale client (local storage, a saved setting) can still send a retired 200K value.
    assert SendMessageRequest(message="hi", model=LLMModel.CLAUDE_5_OPUS_200K).model == LLMModel.CLAUDE_5_OPUS
    assert StartTaskRequest(prompt="hi", model=LLMModel.CLAUDE_4_OPUS_200K).model == LLMModel.CLAUDE_4_OPUS


def _make_workspace_jj_state(bookmarks: tuple[str, ...], primary_bookmark: str | None) -> WorkspaceJjStateInfo:
    return WorkspaceJjStateInfo(
        workspace_id=WorkspaceID(),
        working_copy_change_id="kxqpmzvy" * 4,
        working_copy_change_id_prefix_length=2,
        working_copy_description="",
        is_working_copy_empty=True,
        bookmarks=bookmarks,
        primary_bookmark=primary_bookmark,
        unbookmarked_revision_count=0,
        has_conflict=False,
        is_divergent=False,
        is_working_copy_stale=False,
    )


def test_a_workspace_jj_state_has_no_primary_bookmark_when_it_has_no_bookmarks() -> None:
    assert _make_workspace_jj_state(bookmarks=(), primary_bookmark=None).primary_bookmark is None
    with pytest.raises(ValidationError):
        _make_workspace_jj_state(bookmarks=(), primary_bookmark="feature")


def test_a_workspace_jj_state_takes_its_primary_bookmark_from_its_bookmarks() -> None:
    state = _make_workspace_jj_state(bookmarks=("feature", "base"), primary_bookmark="base")
    assert state.primary_bookmark == "base"
    with pytest.raises(ValidationError):
        _make_workspace_jj_state(bookmarks=("feature",), primary_bookmark="other")


@pytest.mark.parametrize("colocation", [state for state in JjColocationState if state != JjColocationState.FAILED])
def test_a_project_jj_state_carries_no_error_unless_colocation_failed(colocation: JjColocationState) -> None:
    project_id = ProjectID()
    state = ProjectJjState(
        project_id=project_id, colocation=colocation, colocation_error=None, creates_jj_workspaces=False
    )
    assert state.colocation_error is None
    with pytest.raises(ValidationError):
        ProjectJjState(
            project_id=project_id, colocation=colocation, colocation_error="boom", creates_jj_workspaces=False
        )


def test_a_failed_colocation_carries_its_error() -> None:
    project_id = ProjectID()
    state = ProjectJjState(
        project_id=project_id,
        colocation=JjColocationState.FAILED,
        colocation_error="jj git init failed",
        creates_jj_workspaces=False,
    )
    assert state.colocation_error == "jj git init failed"
    with pytest.raises(ValidationError):
        ProjectJjState(
            project_id=project_id,
            colocation=JjColocationState.FAILED,
            colocation_error=None,
            creates_jj_workspaces=False,
        )
