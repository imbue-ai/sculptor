from syrupy import SnapshotAssertion

from sculptor.database.models import AgentTaskStateV2
from sculptor.primitives.ids import AssistantMessageID
from sculptor.primitives.ids import WorkspaceID
from sculptor.state.chat_state import TextBlock
from sculptor.state.messages import ChatInputUserMessage
from sculptor.state.messages import LLMModel
from sculptor.state.messages import ModelCatalogState
from sculptor.state.messages import ModelOption
from sculptor.state.messages import NOT_FETCHED_YET
from sculptor.state.messages import ResponseBlockAgentMessage


def test_create_messages(snapshot: SnapshotAssertion) -> None:
    _messages = [
        ResponseBlockAgentMessage(
            role="user",
            assistant_message_id=AssistantMessageID("some_id"),
            content=(TextBlock(text="some text"),),
        ),
        ChatInputUserMessage(
            text="some text",
            model_name=LLMModel.CLAUDE_4_OPUS,
        ),
    ]


def test_not_fetched_yet_is_the_interned_catalog_singleton() -> None:
    # A StrEnum member is the singleton: the alias IS the member, and a value
    # lookup (what pydantic does on parse) returns that same object — so read
    # sites can rely on `is`, no validator and no `None` overload required.
    assert NOT_FETCHED_YET is ModelCatalogState.NOT_FETCHED_YET
    assert ModelCatalogState("not_fetched_yet") is NOT_FETCHED_YET


def test_catalog_sentinel_survives_task_state_serialization_by_identity() -> None:
    # The DB path is model_dump -> JSON -> model_validate. NOT_FETCHED_YET must
    # come back as the SAME member (not a str, not None), so the switcher's
    # "still loading" gate holds after a reload / backend restart.
    fresh = AgentTaskStateV2(workspace_id=WorkspaceID())
    assert fresh.available_models is NOT_FETCHED_YET
    from_dict = AgentTaskStateV2.model_validate(fresh.model_dump())
    assert from_dict.available_models is NOT_FETCHED_YET
    from_json = AgentTaskStateV2.model_validate_json(fresh.model_dump_json())
    assert from_json.available_models is NOT_FETCHED_YET


def test_legacy_empty_catalog_deserializes_as_fetched_empty() -> None:
    # Rows written before the sentinel existed store available_models as a bare
    # []; those must read as fetched-empty (the no-auth CTA case), NOT as the new
    # not-fetched default. This is why no migration shim is needed — but only as
    # long as the field keeps serializing explicitly (no exclude_defaults).
    legacy = AgentTaskStateV2.model_validate(
        {"object_type": "AgentTaskStateV2", "workspace_id": str(WorkspaceID()), "available_models": []}
    )
    assert legacy.available_models == []
    assert not isinstance(legacy.available_models, ModelCatalogState)

    opus = ModelOption(provider="anthropic", model_id="claude-opus-4-8", display_name="Opus")
    fetched = AgentTaskStateV2.model_validate_json(
        AgentTaskStateV2(workspace_id=WorkspaceID(), available_models=[opus]).model_dump_json()
    )
    assert fetched.available_models == [opus]
