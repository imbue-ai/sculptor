"""Test telemetry event emission for all user message types."""

import typing
from unittest.mock import Mock
from unittest.mock import patch

import pytest

from imbue_core.agents.data_types.ids import TaskID
from imbue_core.ids import AssistantMessageID
from sculptor.agents.claude_code_sdk.agent import AGENT_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP
from sculptor.agents.claude_code_sdk.agent import USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP
from sculptor.agents.claude_code_sdk.agent import _emit_posthog_event_for_agent_message
from sculptor.agents.claude_code_sdk.agent import _emit_posthog_event_for_user_message
from sculptor.agents.claude_code_sdk.agent import _get_user_message_union_types
from sculptor.interfaces.agents.v1.agent import ChatInputUserMessage
from sculptor.interfaces.agents.v1.agent import LocalSyncSetupAndEnabledMessage
from sculptor.interfaces.agents.v1.agent import ParsedAgentMessageType
from sculptor.interfaces.agents.v1.agent import UserMessageUnion


def _get_user_message_types() -> list[type]:
    """Extract all concrete types from UserMessageUnion."""
    union_args = typing.get_args(UserMessageUnion)
    actual_types = []

    for arg in union_args:
        # Handle Annotated types (e.g., Annotated[ChatInputUserMessage, Tag("ChatInputUserMessage")])
        if hasattr(typing, "get_origin") and typing.get_origin(arg) is typing.Annotated:
            actual_types.append(typing.get_args(arg)[0])
        else:
            actual_types.append(arg)

    return actual_types


def _get_parsed_agent_message_types() -> list[type]:
    """Extract all concrete types from ParsedAgentMessageType."""
    union_args = typing.get_args(ParsedAgentMessageType)
    return list(union_args)


def _create_message_instance(
    message_class: type[ParsedAgentMessageType | UserMessageUnion],
) -> ParsedAgentMessageType | UserMessageUnion:
    """Create a minimal valid instance of a user or agent message class."""
    # Get required fields from the class
    if hasattr(message_class, "model_fields"):
        # For Pydantic v2
        fields = message_class.model_fields
    else:
        # For Pydantic v1
        fields = message_class.__fields__

    kwargs: dict[str, typing.Any] = {}

    # Handle common required fields
    for field_name, field_info in fields.items():
        # Skip if field has a default value
        if hasattr(field_info, "default") and field_info.default is not ...:
            continue
        if hasattr(field_info, "default_factory") and field_info.default_factory is not None:
            continue

        # Add minimal values for required fields based on field name
        if field_name == "text":
            kwargs["text"] = "test message"
        elif field_name == "path":
            kwargs["path"] = "/test/file.txt"
        elif field_name == "commit_message":
            kwargs["commit_message"] = "test commit"
        elif field_name == "is_included_in_context":
            kwargs["is_included_in_context"] = True
        elif field_name == "parent_id":
            kwargs["parent_id"] = TaskID()
        elif field_name == "target_message_id":
            kwargs["target_message_id"] = "msg_123"
        elif field_name == "session_id":
            kwargs["session_id"] = "test_session_123"
        elif field_name == "message_id":
            kwargs["message_id"] = AssistantMessageID()
        elif field_name == "content_blocks":
            # For ParsedToolResultMessage
            kwargs["content_blocks"] = []
        elif field_name == "result":
            # For ParsedStreamEndMessage
            kwargs["result"] = "test result"

    return message_class(**kwargs)


def test_all_user_message_types_can_emit_telemetry() -> None:
    """Test that all UserMessageUnion types can be passed to _emit_posthog_event_for_user_message without assertion errors.

    This test automatically discovers all types in UserMessageUnion, so adding new types to the union
    will automatically cause this test to fail if they're not properly handled in the telemetry mapping.
    """
    task_id = TaskID()
    user_message_types = _get_user_message_types()

    # Ensure we found some types
    assert len(user_message_types) > 0, "No user message types found in UserMessageUnion"

    # Mock the emit_posthog_event function to avoid actual emission
    with patch("sculptor.agents.claude_code_sdk.agent.emit_posthog_event") as mock_emit:
        call_counts_per_type = {}
        other_errors = []

        for message_class in user_message_types:
            try:
                message_instance = _create_message_instance(message_class)
                initial_call_count = mock_emit.call_count

                # This should not raise any exceptions
                _emit_posthog_event_for_user_message(task_id, typing.cast(UserMessageUnion, message_instance))

                # Check if emit_posthog_event was called for this message type
                calls_made = mock_emit.call_count - initial_call_count
                call_counts_per_type[message_class.__name__] = calls_made

            except Exception as e:
                # Create a minimal instance to get the object_type for better error reporting
                try:
                    temp_instance = _create_message_instance(message_class)
                    object_type = getattr(temp_instance, "object_type", message_class.__name__)
                except:
                    object_type = message_class.__name__

                other_errors.append(f"{object_type}: {e}")

        # Check which message types didn't result in emit_posthog_event calls (missing from mapping)
        missing_types = [msg_type for msg_type, calls in call_counts_per_type.items() if calls == 0]

        # Report all issues at once
        if missing_types:
            pytest.fail(
                f"The following message types are missing from USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP: {missing_types}"
            )

        if other_errors:
            pytest.fail(f"Unexpected errors: {other_errors}")

    # Verify that emit_posthog_event was called for each successful message type
    expected_calls = len(user_message_types) - len(missing_types)
    assert mock_emit.call_count == expected_calls, (
        f"Expected {expected_calls} calls to emit_posthog_event, but got {mock_emit.call_count}"
    )


def test_all_agent_message_types_can_emit_telemetry() -> None:
    """Test that all ParsedAgentMessageType types can be passed to _emit_posthog_event_for_agent_message without assertion errors.

    This test automatically discovers all types in ParsedAgentMessageType, so adding new types to the union
    will automatically cause this test to fail if they're not properly handled in the telemetry mapping.
    """
    task_id = TaskID()
    agent_message_types = _get_parsed_agent_message_types()

    # Ensure we found some types
    assert len(agent_message_types) > 0, "No agent message types found in ParsedAgentMessageType"

    # Mock the emit_posthog_event function to avoid actual emission
    with patch("sculptor.agents.claude_code_sdk.agent.emit_posthog_event") as mock_emit:
        call_counts_per_type = {}
        other_errors = []

        for message_class in agent_message_types:
            try:
                message_instance = _create_message_instance(message_class)
                initial_call_count = mock_emit.call_count

                # This should not raise any exceptions
                _emit_posthog_event_for_agent_message(task_id, typing.cast(ParsedAgentMessageType, message_instance))

                # Check if emit_posthog_event was called for this message type
                calls_made = mock_emit.call_count - initial_call_count
                call_counts_per_type[message_class.__name__] = calls_made

            except Exception as e:
                # Create a minimal instance to get the object_type for better error reporting
                try:
                    temp_instance = _create_message_instance(message_class)
                    object_type = getattr(temp_instance, "object_type", message_class.__name__)
                except:
                    object_type = message_class.__name__

                other_errors.append(f"{object_type}: {e}")

        # Check which message types didn't result in emit_posthog_event calls (missing from mapping)
        missing_types = [msg_type for msg_type, calls in call_counts_per_type.items() if calls == 0]

        # Report all issues at once
        if missing_types:
            pytest.fail(
                f"The following message types are missing from AGENT_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP: {missing_types}"
            )

        if other_errors:
            pytest.fail(f"Unexpected errors: {other_errors}")

    # Verify that emit_posthog_event was called for each successful message type
    expected_calls = len(agent_message_types) - len(missing_types)
    assert mock_emit.call_count == expected_calls, (
        f"Expected {expected_calls} calls to emit_posthog_event, but got {mock_emit.call_count}"
    )


def test_user_message_type_discovery() -> None:
    """Test that our user message type discovery mechanism works correctly."""
    user_message_types = _get_user_message_types()

    # Basic sanity checks
    assert len(user_message_types) >= 8, f"Expected at least 8 user message types, found {len(user_message_types)}"

    # Check that we get actual classes, not strings or other types
    for msg_type in user_message_types:
        assert isinstance(msg_type, type), f"Expected a class, got {type(msg_type)}: {msg_type}"

    # Check that all discovered types have object_type field (they should inherit from UserMessage)
    for msg_type in user_message_types:
        try:
            instance = _create_message_instance(msg_type)
            assert hasattr(instance, "object_type"), f"{msg_type.__name__} missing object_type field"
        except Exception as e:
            pytest.fail(f"Could not create instance of {msg_type.__name__}: {e}")


def test_agent_message_type_discovery() -> None:
    """Test that our agent message type discovery mechanism works correctly."""
    agent_message_types = _get_parsed_agent_message_types()

    # Basic sanity checks
    assert len(agent_message_types) >= 4, f"Expected at least 4 agent message types, found {len(agent_message_types)}"

    # Check that we get actual classes, not strings or other types
    for msg_type in agent_message_types:
        assert isinstance(msg_type, type), f"Expected a class, got {type(msg_type)}: {msg_type}"

    # Check that all discovered types have object_type field (they should inherit from ParsedAgentMessage)
    for msg_type in agent_message_types:
        try:
            instance = _create_message_instance(msg_type)
            assert hasattr(instance, "object_type"), f"{msg_type.__name__} missing object_type field"
        except Exception as e:
            pytest.fail(f"Could not create instance of {msg_type.__name__}: {e}")


def test_missing_user_message_type_logs_error_and_skips_emission() -> None:
    """Test that when a user message type is missing from the mapping, it logs an error and doesn't call emit_posthog_event."""
    task_id = TaskID()

    # Create a mock message with a non-existent object_type
    message = Mock()
    message.object_type = "NonExistentUserMessage"

    with patch("sculptor.agents.claude_code_sdk.agent.emit_posthog_event") as mock_emit:
        with patch("sculptor.agents.claude_code_sdk.agent.logger") as mock_logger:
            # This should log an error and not call emit_posthog_event
            _emit_posthog_event_for_user_message(task_id, message)

            # Verify that logger.error was called
            mock_logger.error.assert_called_once()
            error_call_args = mock_logger.error.call_args[0]
            assert "NonExistentUserMessage" in error_call_args[1]
            assert "USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP" in error_call_args[0]

            # Verify that emit_posthog_event was NOT called
            mock_emit.assert_not_called()


def test_missing_agent_message_type_logs_error_and_skips_emission() -> None:
    """Test that when an agent message type is missing from the mapping, it logs an error and doesn't call emit_posthog_event."""
    task_id = TaskID()

    # Create a mock message with a non-existent object_type
    message = Mock()
    message.object_type = "NonExistentAgentMessage"

    with patch("sculptor.agents.claude_code_sdk.agent.emit_posthog_event") as mock_emit:
        with patch("sculptor.agents.claude_code_sdk.agent.logger") as mock_logger:
            # This should log an error and not call emit_posthog_event
            _emit_posthog_event_for_agent_message(task_id, message)

            # Verify that logger.error was called
            mock_logger.error.assert_called_once()
            error_call_args = mock_logger.error.call_args[0]
            assert "NonExistentAgentMessage" in error_call_args[1]
            assert "AGENT_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP" in error_call_args[0]

            # Verify that emit_posthog_event was NOT called
            mock_emit.assert_not_called()


def test_static_verification_all_user_message_types_have_mappings() -> None:
    """Static verification that all UserMessageUnion types have corresponding PostHog event mappings."""
    user_message_types = _get_user_message_types()

    missing_mappings = []
    for message_class in user_message_types:
        try:
            # Create an instance to get the object_type
            instance = _create_message_instance(message_class)
            object_type = instance.object_type

            if object_type not in USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP:
                missing_mappings.append(object_type)
        except Exception as e:
            pytest.fail(f"Could not create instance of {message_class.__name__}: {e}")

    if missing_mappings:
        pytest.fail(
            f"The following UserMessage types are missing from USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP: {missing_mappings}. "
            + "Please add the corresponding PostHog event constants to SculptorPosthogEvent and update the mapping."
        )


def test_static_verification_all_agent_message_types_have_mappings() -> None:
    """Static verification that all ParsedAgentMessageType types have corresponding PostHog event mappings."""
    agent_message_types = _get_parsed_agent_message_types()

    missing_mappings = []
    for message_class in agent_message_types:
        try:
            # Create an instance to get the object_type
            instance = _create_message_instance(message_class)
            object_type = instance.object_type

            if object_type not in AGENT_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP:
                missing_mappings.append(object_type)
        except Exception as e:
            pytest.fail(f"Could not create instance of {message_class.__name__}: {e}")

    if missing_mappings:
        pytest.fail(
            f"The following ParsedAgentMessage types are missing from AGENT_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP: {missing_mappings}. "
            + "Please add the corresponding PostHog event constants to SculptorPosthogEvent and update the mapping."
        )


def test_push_message_defensive_posthog_emission() -> None:
    """Test that push_message only emits PostHog events for UserMessageUnion types, not other message types.

    This test verifies that the defensive check in push_message prevents PostHog emission for
    non-UserMessageUnion types that are passed with pyre-ignore comments (like StartLocalSyncRunnerMessage).
    """

    # Test that UserMessageUnion types DO emit PostHog events
    user_message = Mock()
    user_message.object_type = "ChatInputUserMessage"

    assert user_message.object_type in USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP, (
        "Test setup error: ChatInputUserMessage should be in the mapping"
    )

    # Test that non-UserMessageUnion types do NOT emit PostHog events
    non_user_message = Mock()
    non_user_message.object_type = "StartLocalSyncRunnerMessage"

    assert non_user_message.object_type not in USER_MESSAGE_TYPE_TO_POSTHOG_EVENT_MAP, (
        "Test setup error: StartLocalSyncRunnerMessage should NOT be in the mapping"
    )

    # Get the actual UserMessageUnion types for isinstance() checks
    user_union_types = _get_user_message_union_types()

    # Test that UserMessageUnion types pass the isinstance check
    real_user_message = ChatInputUserMessage(text="test")
    assert isinstance(real_user_message, user_union_types), (
        "ChatInputUserMessage should pass isinstance() check against UserMessageUnion types"
    )

    # Test that non-UserMessageUnion types fail the isinstance check
    real_sync_message = LocalSyncSetupAndEnabledMessage()
    assert not isinstance(real_sync_message, user_union_types), (
        "StartLocalSyncRunnerMessage should NOT pass isinstance() check against UserMessageUnion types"
    )

    print("✅ Type-based defensive check works: isinstance() correctly distinguishes UserMessageUnion types")
