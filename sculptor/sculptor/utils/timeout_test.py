import time
from unittest.mock import Mock
from unittest.mock import patch

from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.utils.timeout import TIMING_LOG_THRESHOLD_SECONDS
from sculptor.utils.timeout import format_timing_log
from sculptor.utils.timeout import log_runtime
from sculptor.utils.timeout import timeout_monitor


def test_timeout_monitor_calls_on_timeout(test_root_concurrency_group: ConcurrencyGroup) -> None:
    on_timeout = Mock()

    with timeout_monitor(test_root_concurrency_group, 1, on_timeout):
        time.sleep(2)

    on_timeout.assert_called_once_with(1)


def test_timeout_monitor_no_timeout(test_root_concurrency_group: ConcurrencyGroup) -> None:
    on_timeout = Mock()

    with timeout_monitor(test_root_concurrency_group, 1, on_timeout):
        time.sleep(0.5)

    on_timeout.assert_not_called()


@patch("sculptor.utils.timeout.logger")
def test_log_runtime_logs_when_duration_exceeds_threshold(mock_logger: Mock) -> None:
    """Test that log_runtime emits a debug log when duration exceeds TIMING_LOG_THRESHOLD_SECONDS."""
    # Sleep longer than the threshold to ensure the log is emitted
    sleep_time = TIMING_LOG_THRESHOLD_SECONDS + 0.01

    with log_runtime("slow_operation"):
        time.sleep(sleep_time)

    # Verify debug log was called with the timing log message
    mock_logger.debug.assert_called()
    log_message = mock_logger.debug.call_args[0][0]
    assert "TIMING_LOG" in log_message
    assert "function=slow_operation" in log_message
    assert "duration_s=" in log_message
    assert "status=success" in log_message


@patch("sculptor.utils.timeout.logger")
def test_log_runtime_does_not_log_when_duration_below_threshold(mock_logger: Mock) -> None:
    """Test that log_runtime does NOT emit a debug log when duration is below TIMING_LOG_THRESHOLD_SECONDS."""
    # Don't sleep at all - the operation should be well under the threshold
    with log_runtime("fast_operation"):
        pass  # Near-instant operation

    # Verify debug log was NOT called (no timing log should be emitted)
    mock_logger.debug.assert_not_called()


def test_format_timing_log_happy_path() -> None:
    """Test that format_timing_log returns the expected string for a successful operation."""
    message = format_timing_log("test_function", 0.123456)

    assert message == "TIMING_LOG, function=test_function, duration_s=00.123456, status=success"
