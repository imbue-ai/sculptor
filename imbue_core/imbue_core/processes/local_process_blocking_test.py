import io
import os
import tempfile
import threading
import time
from pathlib import Path
from threading import Event

import pytest
from loguru import logger

from imbue_core.event_utils import CompoundEvent
from imbue_core.processes.local_process import run_blocking
from imbue_core.subprocess_utils import ProcessError
from imbue_core.subprocess_utils import ProcessSetupError
from imbue_core.subprocess_utils import ProcessTimeoutError


def test_run_blocking_simple_command() -> None:
    """Test running a simple echo command."""
    result = run_blocking(["echo", "hello world"], timeout=5.0)

    assert result.returncode == 0
    assert result.stdout.strip() == "hello world"
    assert result.stderr == ""
    assert result.command == ("echo", "hello world")
    assert isinstance(result.is_output_already_logged, bool)  # Just check it's a bool


def test_run_blocking_with_stderr() -> None:
    """Test command that writes to stderr."""
    # Use a command that writes to stderr
    result = run_blocking(["sh", "-c", "echo 'error message' >&2"], timeout=5.0, is_checked=False)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr.strip() == "error message"


def test_run_blocking_non_zero_exit_checked() -> None:
    """Test that non-zero exit code raises ProcessError when is_checked=True."""
    with pytest.raises(ProcessError) as exc_info:
        run_blocking(["false"], timeout=5.0, is_checked=True)

    assert exc_info.value.returncode == 1
    assert exc_info.value.command == ("false",)


def test_run_blocking_non_zero_exit_unchecked() -> None:
    """Test that non-zero exit code returns normally when is_checked=False."""
    result = run_blocking(["false"], timeout=5.0, is_checked=False)

    assert result.returncode == 1
    assert result.command == ("false",)


def test_run_blocking_with_cwd() -> None:
    """Test running command in a specific working directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create a test file in the temp directory
        test_file = tmpdir_path / "test.txt"
        test_file.write_text("test content")

        # Run ls in the temp directory
        result = run_blocking(["ls"], timeout=5.0, cwd=tmpdir_path)

        assert result.returncode == 0
        assert "test.txt" in result.stdout


def test_run_blocking_timeout() -> None:
    """Test that command actually times out when exceeding timeout."""
    # Use a real command that will take longer than the timeout
    start_time = time.time()
    with pytest.raises(ProcessTimeoutError):
        # This sleep command will take 10 seconds but we only give it 0.5 seconds
        run_blocking(["sleep", "10"], timeout=0.5)

    elapsed_time = time.time() - start_time
    # Verify it actually timed out quickly (within 2 seconds to account for overhead)
    assert elapsed_time < 2.0


def test_run_blocking_with_shutdown_event() -> None:
    """Test using shutdown event to interrupt a long-running command."""
    shutdown_event = Event()

    def set_shutdown_event() -> None:
        """Set the shutdown event after a short delay."""
        time.sleep(0.5)
        shutdown_event.set()

    # Start a thread that will set the shutdown event
    shutdown_thread = threading.Thread(target=set_shutdown_event)
    shutdown_thread.start()

    start_time = time.time()
    try:
        # Run a command that would normally take 10 seconds
        run_blocking(
            ["sleep", "10"],
            timeout=15.0,  # Long timeout to ensure shutdown event is what stops it
            shutdown_event=shutdown_event,
            shutdown_timeout_sec=2.0,
            is_checked=False,
        )
        elapsed_time = time.time() - start_time

        # The command should have been interrupted within ~2.5 seconds (0.5s delay + 2s shutdown timeout)
        assert elapsed_time < 3.0
    finally:
        shutdown_thread.join()


def test_run_blocking_with_compound_event() -> None:
    """Test using CompoundEvent as shutdown event."""
    event1 = Event()
    event2 = Event()
    compound_event = CompoundEvent([event1, event2])

    def set_event2() -> None:
        """Set the second event after a short delay."""
        time.sleep(0.5)
        event2.set()

    # Start a thread that will set one of the compound events
    event_thread = threading.Thread(target=set_event2)
    event_thread.start()

    start_time = time.time()
    try:
        # Run a command that would normally take 10 seconds
        run_blocking(
            ["sleep", "10"],
            timeout=15.0,
            # RemoteRunningProcess lets shutdown_event be a ReadOnlyEvent, including CompoundEvent, but RunningProcess only allows MutableEvent
            # pyrefly: ignore [bad-argument-type]
            shutdown_event=compound_event,
            shutdown_timeout_sec=2.0,
            is_checked=False,
        )
        elapsed_time = time.time() - start_time

        # The command should have been interrupted
        assert elapsed_time < 3.0
    finally:
        event_thread.join()


def trace_on_line_callback(line: str, _: bool):
    """Helper function to instrument the call to trace with loguru.

    Unused argument "_" is for is_stdout
    """
    logger.trace("> " + line)


def test_run_blocking_output_callback() -> None:
    """Test that output is properly logged via the callback."""
    # Capture log output at TRACE level
    log_capture = io.StringIO()
    handler_id = logger.add(log_capture, level="TRACE", format="{message}")

    try:
        # Run a command that produces multiple lines of output
        result = run_blocking(
            ["sh", "-c", "echo 'line1'; echo 'line2' >&2; echo 'line3'"],
            timeout=5.0,
            is_output_traced=True,
            trace_on_line_callback=trace_on_line_callback,
        )

        # Get the captured log output
        log_output = log_capture.getvalue()

        # Verify that output lines were logged with "> " prefix
        assert "> line1" in log_output
        assert "> line2" in log_output
        assert "> line3" in log_output

        # Also verify the command completed successfully
        assert result.returncode == 0
        assert "line1" in result.stdout
        assert "line3" in result.stdout
        assert "line2" in result.stderr
    finally:
        logger.remove(handler_id)


def test_run_blocking_trace_log_context() -> None:
    """Test that trace log context affects logging output."""
    # Capture log output with structured logging
    log_capture = io.StringIO()
    handler_id = logger.add(
        log_capture,
        level="TRACE",
        format="{extra} - {message}",
        filter=lambda record: "request_id" in record["extra"],
    )

    trace_context = {"request_id": "test-123", "user": "test_user"}

    try:
        # Run command with trace context
        result = run_blocking(
            ["echo", "test with context"],
            timeout=5.0,
            trace_log_context=trace_context,
            is_output_traced=True,
            trace_on_line_callback=trace_on_line_callback,
        )

        # The command should have succeeded
        assert result.returncode == 0
        assert result.stdout.strip() == "test with context"

        # Get the captured log output
        log_output = log_capture.getvalue()

        # Verify that the trace context was included in the logs
        # The format should show the extra context and message
        assert "test-123" in log_output
        assert "test_user" in log_output
    finally:
        logger.remove(handler_id)


def test_run_blocking_output_traced_flag() -> None:
    """Test that is_output_traced parameter controls whether output is logged."""
    # Test with tracing disabled
    log_capture_disabled = io.StringIO()
    handler_id_disabled = logger.add(log_capture_disabled, level="TRACE", format="{message}")

    try:
        result = run_blocking(
            ["echo", "traced output disabled"],
            timeout=5.0,
            is_output_traced=False,
            trace_on_line_callback=trace_on_line_callback,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "traced output disabled"

        log_output_disabled = log_capture_disabled.getvalue()
        assert "traced output disabled" not in log_output_disabled
    finally:
        logger.remove(handler_id_disabled)

    # Test with tracing enabled (default)
    log_capture_enabled = io.StringIO()
    handler_id_enabled = logger.add(log_capture_enabled, level="TRACE", format="{message}")

    try:
        result = run_blocking(
            ["echo", "traced output enabled"],
            timeout=5.0,
            is_output_traced=True,
            trace_on_line_callback=trace_on_line_callback,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "traced output enabled"

        # When is_output_traced=True, output should be logged
        log_output_enabled = log_capture_enabled.getvalue()
        assert "traced output enabled" in log_output_enabled
    finally:
        logger.remove(handler_id_enabled)


def test_run_blocking_multiline_output() -> None:
    """Test command with multiline output."""
    result = run_blocking(["sh", "-c", "echo 'line1'; echo 'line2'; echo 'line3'"], timeout=5.0)

    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 3
    assert lines[0] == "line1"
    assert lines[1] == "line2"
    assert lines[2] == "line3"


def test_run_blocking_empty_output() -> None:
    """Test command with no output."""
    result = run_blocking(["true"], timeout=5.0)

    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_run_blocking_with_arguments() -> None:
    """Test command with multiple arguments."""
    result = run_blocking(["echo", "-n", "no", "newline"], timeout=5.0)

    assert result.returncode == 0
    assert result.stdout == "no newline"  # -n flag prevents newline


def test_run_blocking_command_not_found() -> None:
    """Test running a non-existent command."""
    with pytest.raises(ProcessSetupError) as exc_info:
        run_blocking(["nonexistent_command_12345"], timeout=5.0)

    # The error should mention the command couldn't be found
    error_msg = str(exc_info.value)
    assert "nonexistent_command_12345" in error_msg


def test_run_blocking_large_output() -> None:
    """Test handling of large output that exceeds kernel pipe buffer."""
    # Generate ~100KB of output to exceed typical pipe buffers (16KB macOS, 64KB Linux)
    # Each line is ~50 bytes, so 2000 lines = ~100KB
    result = run_blocking(
        [
            "sh",
            "-c",
            'for i in $(seq 1 2000); do echo "Line $i - This is a longer line to increase the total output size"; done',
        ],
        timeout=10.0,
        is_output_traced=False,
    )

    assert result.returncode == 0
    lines = result.stdout.strip().split("\n")
    assert len(lines) == 2000
    assert lines[0] == "Line 1 - This is a longer line to increase the total output size"
    assert lines[1999] == "Line 2000 - This is a longer line to increase the total output size"


def test_run_blocking_mixed_stdout_stderr() -> None:
    """Test command that interleaves stdout and stderr."""
    result = run_blocking(
        ["sh", "-c", "echo 'stdout1'; echo 'stderr1' >&2; echo 'stdout2'; echo 'stderr2' >&2"], timeout=5.0
    )

    assert result.returncode == 0
    assert "stdout1" in result.stdout
    assert "stdout2" in result.stdout
    assert "stderr1" in result.stderr
    assert "stderr2" in result.stderr


def test_run_blocking_env_variables() -> None:
    """Test that environment variables are accessible."""
    # Set a custom env variable and verify the command can read it
    old_value = os.environ.get("TEST_RUN_BLOCKING_VAR")
    try:
        os.environ["TEST_RUN_BLOCKING_VAR"] = "test_value_123"
        result = run_blocking(["sh", "-c", "echo $TEST_RUN_BLOCKING_VAR"], timeout=5.0)
        assert result.returncode == 0
        assert result.stdout.strip() == "test_value_123"
    finally:
        if old_value is None:
            os.environ.pop("TEST_RUN_BLOCKING_VAR", None)
        else:
            os.environ["TEST_RUN_BLOCKING_VAR"] = old_value
