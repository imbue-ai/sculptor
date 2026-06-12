"""Tests for the pre-import bootstrap (``sculptor.cli.main``)."""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

from sculptor.cli.main import _parse_trace_to_arg

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def test_module_top_level_imports_are_stdlib_only() -> None:
    """``cli/main.py`` must not import anything heavy at module top.

    The pty helper dispatch lives at the top of ``main()`` and is supposed
    to short-circuit before importing the backend.  That only works if
    importing the module itself stays cheap.  Pin the invariant so a
    future commit doesn't silently regress it by adding ``from loguru
    import logger`` at the top.
    """
    src = (Path(__file__).parent / "main.py").read_text()
    tree = ast.parse(src)
    forbidden_roots = {"sculptor", "loguru", "pydantic", "grpc", "uvicorn", "typer"}
    offenders: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                root = alias.name.split(".")[0]
                if root in forbidden_roots:
                    offenders.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root in forbidden_roots:
                offenders.append(node.module or "")
    assert not offenders, f"top-level imports must be stdlib only; found: {offenders}"


def test_bootstrap_import_does_not_spawn_threads() -> None:
    """Importing ``sculptor.cli.main`` must not spawn any threads.

    The whole point of the bootstrap is that a helper invocation never
    pays for the backend's thread-spawning imports.  This test runs the
    bare import in a clean subprocess and verifies the active thread
    count stays at 1 -- catching a future regression that pulls in
    something like loguru or sentry at module top.
    """
    script = """
import threading
import sys
from sculptor.cli import main  # noqa: F401
active = threading.active_count()
names = sorted(t.name for t in threading.enumerate())
sys.stdout.write(f'COUNT={active}\\n')
sys.stdout.write(f'NAMES={names}\\n')
sys.exit(0 if active == 1 else 1)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(_repo_root()),
    )
    assert result.returncode == 0, (
        f"Bootstrap import spawned threads. stdout={result.stdout!r}, stderr={result.stderr!r}"
    )


def test_main_with_pty_helper_flag_dispatches_to_helper() -> None:
    """``python -m sculptor.cli.main --pty-helper`` must run the helper
    rather than the backend.

    The helper reads its inherited socketpair fd from
    ``_SCULPTOR_PTY_HELPER_FD``; if that env var is missing the helper
    exits with a known non-zero code (currently 2 -- see
    ``pty_helper._EXIT_HELPER_BAD_ARGS``).  Observing that exit code is
    a positive signal that we reached ``pty_helper.main`` and did NOT
    start uvicorn/the backend.
    """
    result = subprocess.run(
        [sys.executable, "-m", "sculptor.cli.main", "--pty-helper"],
        capture_output=True,
        text=True,
        timeout=15,
        cwd=str(_repo_root()),
        env={"PATH": "/usr/bin:/bin"},
    )
    detail = f"returncode={result.returncode}, stdout={result.stdout!r}, stderr={result.stderr!r}"
    assert result.returncode == 2, f"Expected pty_helper bad-args exit (2). {detail}"
    assert "_SCULPTOR_PTY_HELPER_FD" in result.stderr, (
        f"Expected helper's diagnostic about the missing fd env var. stderr={result.stderr!r}"
    )


def test_parse_trace_to_arg_handles_both_forms(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["sculptor", "--trace-to=/tmp/a.json"])
    assert _parse_trace_to_arg() == "/tmp/a.json"

    monkeypatch.setattr(sys, "argv", ["sculptor", "--trace-to", "/tmp/b.json"])
    assert _parse_trace_to_arg() == "/tmp/b.json"

    monkeypatch.setattr(sys, "argv", ["sculptor", "--port", "8080"])
    assert _parse_trace_to_arg() is None


def test_parse_trace_to_arg_rejects_missing_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--trace-to`` with no following arg or ``--trace-to=`` (empty value)
    must fail loudly rather than silently disabling tracing."""
    monkeypatch.setattr(sys, "argv", ["sculptor", "--trace-to"])
    with pytest.raises(SystemExit) as exc:
        _parse_trace_to_arg()
    assert exc.value.code == 2

    monkeypatch.setattr(sys, "argv", ["sculptor", "--trace-to="])
    with pytest.raises(SystemExit) as exc:
        _parse_trace_to_arg()
    assert exc.value.code == 2


def test_parse_trace_to_arg_strips_flag_from_argv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The flag must be removed from ``sys.argv`` so typer never sees it.

    Typer's grammar is ``[OPTIONS] [PROJECT] COMMAND [ARGS]...``. Anything
    that looks like an unknown flag AFTER the positional project path gets
    mis-parsed as a subcommand and fails backend startup with
    ``No such command '--trace-to=...'``. The bootstrap parses the flag
    early, so the safe fix is to consume it from argv entirely.
    """
    # --trace-to=VALUE form, placed AFTER the positional project path
    monkeypatch.setattr(sys, "argv", ["sculptor", "/some/project", "--trace-to=/tmp/a.json"])
    assert _parse_trace_to_arg() == "/tmp/a.json"
    assert sys.argv == ["sculptor", "/some/project"]

    # --trace-to VALUE form, placed AFTER the positional project path
    monkeypatch.setattr(sys, "argv", ["sculptor", "/some/project", "--trace-to", "/tmp/b.json"])
    assert _parse_trace_to_arg() == "/tmp/b.json"
    assert sys.argv == ["sculptor", "/some/project"]

    # --trace-to=VALUE form, placed BEFORE the positional project path,
    # interleaved with another option
    monkeypatch.setattr(sys, "argv", ["sculptor", "--port", "8080", "--trace-to=/tmp/c.json", "/some/project"])
    assert _parse_trace_to_arg() == "/tmp/c.json"
    assert sys.argv == ["sculptor", "--port", "8080", "/some/project"]

    # --trace-to VALUE form, sandwiched between other options
    monkeypatch.setattr(sys, "argv", ["sculptor", "--trace-to", "/tmp/d.json", "--port", "8080"])
    assert _parse_trace_to_arg() == "/tmp/d.json"
    assert sys.argv == ["sculptor", "--port", "8080"]

    # No flag present: argv unchanged
    monkeypatch.setattr(sys, "argv", ["sculptor", "/some/project", "--port", "8080"])
    assert _parse_trace_to_arg() is None
    assert sys.argv == ["sculptor", "/some/project", "--port", "8080"]
