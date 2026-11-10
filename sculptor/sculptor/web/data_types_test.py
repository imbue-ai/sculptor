"""Unit tests for sculptor.web.data_types."""

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.state.messages import LLMModel
from sculptor.web.data_types import CreateWorkspaceRequestV2
from sculptor.web.data_types import SendMessageRequest
from sculptor.web.data_types import StartTaskRequest


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
