import tempfile
import threading
import time
from pathlib import Path
from threading import Event
from typing import Callable
from typing import TypeVar

import pytest

from imbue_core.processes.local_process import run_streaming
from imbue_core.subprocess_utils import ProcessError

OutputCaputurerOutT = TypeVar("OutputCaputurerOutT", bound=tuple[str, bool] | int)
OutputCapturer = Callable[[], tuple[Callable[[str, bool], None], list[OutputCaputurerOutT]]]


# Pytest fixtures for callback creation
@pytest.fixture
def output_capturer() -> OutputCapturer:
    """Fixture that returns a function to create output capture callbacks."""

    def _create_callback() -> tuple[Callable[[str, bool], None], list[tuple[str, bool]]]:
        captured_output: list[tuple[str, bool]] = []

        def on_output(line: str, is_stdout: bool) -> None:
            captured_output.append((line, is_stdout))

        return on_output, captured_output

    return _create_callback


TimestampCapturer = Callable[[float], tuple[Callable[[str, bool], None], list[tuple[str, float]]]]


@pytest.fixture
def timestamp_capturer() -> TimestampCapturer:
    """Fixture that returns a function to create timestamp capture callbacks."""

    def _create_callback(start_time: float) -> tuple[Callable[[str, bool], None], list[tuple[str, float]]]:
        captured_output: list[tuple[str, float]] = []

        def on_output(line: str, is_stdout: bool) -> None:
            elapsed = time.time() - start_time
            captured_output.append((line, elapsed))

        return on_output, captured_output

    return _create_callback


@pytest.fixture
def failing_callback() -> OutputCapturer:
    """Fixture that returns a function to create failing callbacks.

    This will fail on the second line of logging.
    """

    def _create_callback() -> tuple[Callable[[str, bool], None], list[int]]:
        call_count = [0]

        def on_output(line: str, is_stdout: bool) -> None:
            call_count[0] += 1
            if call_count[0] == 2:
                raise ValueError("Test exception in callback")

        return on_output, call_count

    return _create_callback


# Test functions for run_streaming
def test_run_streaming_simple_output(output_capturer: OutputCapturer) -> None:
    """Test streaming a simple echo command."""
    on_output, captured_output = output_capturer()

    result = run_streaming(["echo", "hello world"], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 1
    line, is_stdout = captured_output[0]
    assert line == "hello world\n"
    assert is_stdout


def test_run_streaming_multiline_output(output_capturer: OutputCapturer) -> None:
    """Test streaming multiple lines of output."""
    on_output, captured_output = output_capturer()

    result = run_streaming(["sh", "-c", "echo 'line1'; echo 'line2'; echo 'line3'"], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 3
    assert captured_output[0][0] == "line1\n"
    assert captured_output[1][0] == "line2\n"
    assert captured_output[2][0] == "line3\n"
    assert all(is_stdout for _, is_stdout in captured_output)


def test_run_streaming_mixed_stdout_stderr(output_capturer: OutputCapturer) -> None:
    """Test streaming both stdout and stderr."""
    on_output, captured_output = output_capturer()

    result = run_streaming(["sh", "-c", "echo 'stdout line'; echo 'stderr line' >&2"], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 2

    # Find stdout and stderr lines
    stdout_lines = [line for line, is_stdout in captured_output if is_stdout]
    stderr_lines = [line for line, is_stdout in captured_output if not is_stdout]

    assert len(stdout_lines) == 1
    assert len(stderr_lines) == 1
    assert stdout_lines[0] == "stdout line\n"
    assert stderr_lines[0] == "stderr line\n"


def test_run_streaming_no_trailing_newline(output_capturer: OutputCapturer) -> None:
    """Test that output without trailing newline is passed to callback.

    The callback is called for all lines (including those ending without a newline).
    """
    on_output, captured_output = output_capturer()

    # echo -n outputs without trailing newline
    result = run_streaming(["echo", "-n", "no newline"], on_output)

    assert result.returncode == 0
    # No callback should be triggered since there's no complete line
    assert len(captured_output) == 1
    # But the output should still be in the result
    assert result.stdout == "no newline"


def test_run_streaming_empty_lines(output_capturer: OutputCapturer) -> None:
    """Test handling of empty lines."""
    on_output, captured_output = output_capturer()

    result = run_streaming(["sh", "-c", "echo 'line1'; echo ''; echo 'line3'"], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 3
    assert captured_output[0][0] == "line1\n"
    assert captured_output[1][0] == "\n"  # Empty line still has newline
    assert captured_output[2][0] == "line3\n"


def test_run_streaming_real_time_output(timestamp_capturer: TimestampCapturer) -> None:
    """Test that output is streamed in real-time, not buffered."""
    start_time = time.time()
    on_output, captured_output = timestamp_capturer(start_time)

    # Command that outputs lines with delays
    result = run_streaming(["sh", "-c", "echo 'immediate'; sleep 0.5; echo 'delayed'"], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 2

    # First line should come immediately
    assert captured_output[0][1] < 0.1
    # Second line should come after ~0.5 seconds
    assert captured_output[1][1] > 0.4


def test_run_streaming_callback_order(output_capturer: OutputCapturer) -> None:
    """Test that callbacks are called in the correct order."""
    on_output, captured_output = output_capturer()

    # Generate numbered lines to verify order
    result = run_streaming(["sh", "-c", 'for i in 1 2 3 4 5; do echo "Line $i"; done'], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 5
    for i in range(5):
        line, is_stdout = captured_output[i]
        assert line == f"Line {i + 1}\n"
        assert is_stdout


def test_run_streaming_large_lines(output_capturer: OutputCapturer) -> None:
    """Test handling of very long lines that exceed the internal buffer size."""
    on_output, captured_output = output_capturer()

    # Generate a line longer than _READ_SIZE (1MB = 1048576 bytes) using shell commands
    # Use ~1.2MB to ensure we exceed the buffer and test multi-read scenarios
    line_size = 1_250_000
    # Use printf to generate a large string then echo to add newline for complete line
    result = run_streaming(["sh", "-c", f"printf '%*s' {line_size} ''; echo"], on_output)

    assert result.returncode == 0
    assert len(captured_output) == 1
    # The output should be exactly line_size ' ' characters + 1 newline
    assert len(captured_output[0][0]) == line_size + 1  # +1 for the newline that echo adds
    assert captured_output[0][0].startswith(" " * 100)  # Check it starts with whitespaces
    assert captured_output[0][0].endswith("\n")  # Check it ends with newline
    assert captured_output[0][1] is True


def test_run_streaming_callback_exception(failing_callback: OutputCapturer) -> None:
    """Test behavior when callback raises an exception."""
    on_output, call_count = failing_callback()

    with pytest.raises(Exception):
        run_streaming(["sh", "-c", "echo 'line1'; echo 'line2'; echo 'line3'"], on_output)


def test_run_streaming_with_timeout(output_capturer: OutputCapturer) -> None:
    """Test streaming with timeout."""
    on_output, captured_output = output_capturer()

    # Command that will timeout
    with pytest.raises(ProcessError):
        run_streaming(["sh", "-c", "echo 'before sleep'; sleep 10; echo 'after sleep'"], on_output, timeout=0.5)

    # Should have captured output before timeout
    assert len(captured_output) >= 1
    assert captured_output[0][0] == "before sleep\n"
    # Should not have captured output after timeout
    assert not any("after sleep" in line for line, _ in captured_output)


def test_run_streaming_with_shutdown_event(output_capturer: OutputCapturer) -> None:
    """Test streaming with shutdown event interruption."""
    on_output, captured_output = output_capturer()
    shutdown_event = Event()

    def _set_shutdown() -> None:
        time.sleep(0.5)
        shutdown_event.set()

    # Start thread to trigger shutdown
    shutdown_thread = threading.Thread(target=_set_shutdown)
    shutdown_thread.start()

    try:
        # Command that outputs lines slowly
        result = run_streaming(
            ["sh", "-c", 'for i in 1 2 3 4 5; do echo "Line $i"; sleep 0.3; done'],
            on_output,
            shutdown_event=shutdown_event,
            shutdown_timeout_sec=1.0,
            is_checked=False,
        )

        # Should have captured some but not all lines
        assert len(captured_output) >= 2
        assert captured_output[0][0] == "Line 1\n"
        assert captured_output[1][0] == "Line 2\n"
        assert len(captured_output) < 5
        assert result.returncode != 0
    finally:
        shutdown_thread.join()


def test_run_streaming_non_zero_exit(output_capturer: OutputCapturer) -> None:
    """Test streaming with non-zero exit code."""
    on_output, captured_output = output_capturer()

    # Command that outputs then fails
    with pytest.raises(ProcessError) as exc_info:
        run_streaming(["sh", "-c", "echo 'before failure'; exit 42"], on_output, is_checked=True)

    assert exc_info.value.returncode == 42
    assert len(captured_output) == 1
    assert captured_output[0][0] == "before failure\n"


def test_run_streaming_unchecked_non_zero_exit(output_capturer: OutputCapturer) -> None:
    """Test streaming with non-zero exit code when unchecked."""
    on_output, captured_output = output_capturer()

    result = run_streaming(["sh", "-c", "echo 'output'; exit 42"], on_output, is_checked=False)

    assert result.returncode == 42
    assert len(captured_output) == 1
    assert captured_output[0][0] == "output\n"


def test_run_streaming_with_cwd(output_capturer: OutputCapturer) -> None:
    """Test streaming with custom working directory."""
    on_output, captured_output = output_capturer()

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)

        # Create test files
        (tmpdir_path / "test1.txt").touch()
        (tmpdir_path / "test2.txt").touch()

        result = run_streaming(["ls"], on_output, cwd=tmpdir_path)

        assert result.returncode == 0
        assert len(captured_output) == 2
        captured_lines = [line.strip() for line, _ in captured_output]
        assert "test1.txt" in captured_lines
        assert "test2.txt" in captured_lines


def test_run_streaming_partial_lines(output_capturer: OutputCapturer) -> None:
    """Test handling of output that doesn't end with newline in the middle."""
    on_output, captured_output = output_capturer()

    # This command outputs a partial line followed by a complete line
    result = run_streaming(["sh", "-c", "printf 'partial'; sleep 0.1; echo ' complete'"], on_output)

    assert result.returncode == 0
    # Only the complete line (after echo) triggers the callback
    assert len(captured_output) == 1
    line, is_stdout = captured_output[0]
    assert line == "partial complete\n"
    assert is_stdout
    # The full output is captured in the result
    assert result.stdout == "partial complete\n"
