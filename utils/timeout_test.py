import time
from unittest.mock import Mock
from unittest.mock import patch

from sculptor.utils.timeout import ProductComponent
from sculptor.utils.timeout import SculptorPosthogEvent
from sculptor.utils.timeout import log_runtime
from sculptor.utils.timeout import log_runtime_decorator
from sculptor.utils.timeout import timeout_monitor


def test_timeout_monitor_calls_on_timeout() -> None:
    on_timeout = Mock()

    with timeout_monitor(1, on_timeout):
        time.sleep(2)

    on_timeout.assert_called_once_with(1)


def test_timeout_monitor_no_timeout() -> None:
    on_timeout = Mock()

    with timeout_monitor(1, on_timeout):
        time.sleep(0.5)

    on_timeout.assert_not_called()


@patch("sculptor.utils.timeout.emit_posthog_event")
def test_log_runtime_decorator_emits_posthog_event(mock_emit: Mock) -> None:
    """Test that the runtime decorator emits PostHog events with timing data."""

    @log_runtime_decorator("test_function")
    def example_test_func() -> str:
        time.sleep(0.1)  # Small delay to test timing
        return "success"

    result = example_test_func()

    # Verify the function still works
    assert result == "success"

    # Verify PostHog event was emitted
    mock_emit.assert_called_once()

    # Check the event details
    call_args = mock_emit.call_args
    event_model = call_args[0][0]  # First positional argument

    assert event_model.name.value == "runtime_measurement"
    assert event_model.component.value == "cross_component"
    assert event_model.payload.function_name == "test_function"
    assert event_model.payload.duration_seconds > 0.05  # Should be > 0.05s due to sleep


@patch("sculptor.utils.timeout.emit_posthog_event")
def test_log_runtime_decorator_uses_function_name_when_no_label(mock_emit: Mock) -> None:
    """Test that the runtime decorator uses function name when no label is provided."""

    @log_runtime_decorator()
    def my_test_function() -> str:
        return "success"

    result = my_test_function()

    # Verify the function still works
    assert result == "success"

    # Verify PostHog event was emitted with function name
    mock_emit.assert_called_once()
    call_args = mock_emit.call_args
    event_model = call_args[0][0]

    assert event_model.payload.function_name == "my_test_function"


@patch("sculptor.utils.timeout.emit_posthog_event", side_effect=Exception("PostHog error"))
def test_log_runtime_decorator_handles_posthog_errors(mock_emit: Mock) -> None:
    """Test that PostHog errors don't break the decorated function."""

    # import pytest

    # import sculptor.utils.timeout

    # with pytest.raises(Exception):
    #     sculptor.utils.timeout.emit_posthog_event(None)

    @log_runtime_decorator("test_function")
    def example_test_func() -> str:
        return "success"

    # This should not raise an exception even though PostHog fails
    result = example_test_func()

    # Verify the function still works despite PostHog failure
    assert result == "success"

    # Verify PostHog was attempted
    mock_emit.assert_called_once()


@patch("sculptor.utils.timeout.emit_posthog_event")
def test_log_runtime_context_manager_emits_posthog_event(mock_emit: Mock) -> None:
    """Test that the runtime context manager emits PostHog events with timing data."""

    with log_runtime("test_context"):
        time.sleep(0.01)  # Small delay to test timing

    # Verify PostHog event was emitted
    mock_emit.assert_called_once()

    # Check the event details
    call_args = mock_emit.call_args
    event_model = call_args[0][0]  # First positional argument

    assert event_model.name.value == SculptorPosthogEvent.RUNTIME_MEASUREMENT.value
    assert event_model.component.value == ProductComponent.CROSS_COMPONENT.value
    assert event_model.payload.function_name == "test_context"
    assert event_model.payload.duration_seconds > 0.005  # Should be > 0.01s due to sleep
