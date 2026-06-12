"""Unit tests for sculptor.web.data_types."""

import pytest
from pydantic import ValidationError

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.web.data_types import CreateWorkspaceRequestV2


def test_create_workspace_request_defaults_harness_to_claude() -> None:
    request = CreateWorkspaceRequestV2(
        project_id="proj-1",
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
    )
    assert request.harness == HarnessName.CLAUDE


def test_create_workspace_request_accepts_pi_harness() -> None:
    request = CreateWorkspaceRequestV2.model_validate(
        {
            "project_id": "proj-1",
            "initialization_strategy": WorkspaceInitializationStrategy.IN_PLACE.value,
            "harness": "pi",
        }
    )
    assert request.harness == HarnessName.PI


def test_create_workspace_request_rejects_unknown_harness() -> None:
    with pytest.raises(ValidationError):
        CreateWorkspaceRequestV2.model_validate(
            {
                "project_id": "proj-1",
                "initialization_strategy": WorkspaceInitializationStrategy.IN_PLACE.value,
                "harness": "definitely-not-a-real-harness",
            }
        )
