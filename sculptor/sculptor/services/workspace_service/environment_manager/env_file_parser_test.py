import threading
from pathlib import Path
from typing import Callable

import pytest

from sculptor.services.workspace_service.environment_manager.env_file_parser import atomic_copy_env_file
from sculptor.services.workspace_service.environment_manager.env_file_parser import load_project_env_vars
from sculptor.services.workspace_service.environment_manager.env_file_parser import parse_env_file


@pytest.fixture()
def env_file(tmp_path: Path) -> Callable[[str], Path]:
    """Create a .env file with the given content in a temp directory."""

    def _create(content: str) -> Path:
        path = tmp_path / ".env"
        path.write_text(content)
        return path

    return _create


def test_simple_var(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("VAR=VALUE\n")) == {"VAR": "VALUE"}


def test_export_prefix(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("export VAR=VALUE\n")) == {"VAR": "VALUE"}


def test_export_prefix_trailing_space(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("export VAR=VALUE  \n")) == {"VAR": "VALUE"}


def test_double_quoted_value(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file('VAR="quoted value"\n')) == {"VAR": "quoted value"}


def test_single_quoted_value(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("VAR='single quoted'\n")) == {"VAR": "single quoted"}


def test_full_line_comment(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("# full-line comment\n")) == {}


def test_inline_comment_unquoted(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("VAR=value # inline comment\n")) == {"VAR": "value"}


def test_inline_comment_double_quoted(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file('VAR="quoted" # comment\n')) == {"VAR": "quoted"}


def test_no_name(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("=VALUE\n")) == {}


def test_space_in_name(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("FOO BAR=VALUE\n")) == {}


def test_no_interpolation(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("VAR=$OTHER\n")) == {"VAR": "$OTHER"}


def test_nonexistent_file() -> None:
    assert parse_env_file(Path("/nonexistent/path/.env")) == {}


def test_empty_file(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("")) == {}


def test_multiple_vars(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("FOO=bar\nBAZ=qux\n")) == {"FOO": "bar", "BAZ": "qux"}


def test_duplicate_keys_last_wins(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("VAR=first\nVAR=second\n")) == {"VAR": "second"}


def test_hash_inside_double_quoted_value(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file('FOO="bar#baz"\n')) == {"FOO": "bar#baz"}


def test_uppercase_export_not_stripped(env_file: Callable[[str], Path]) -> None:
    assert parse_env_file(env_file("EXPORT VAR=VALUE\n")) == {}


def test_load_project_env_vars(tmp_path: Path) -> None:
    global_dir = tmp_path / "global_sculptor"
    global_dir.mkdir()
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    sculptor_dir = project_dir / ".sculptor"
    sculptor_dir.mkdir()
    (sculptor_dir / ".env").write_text("MY_VAR=hello\n")
    assert load_project_env_vars(project_dir, sculptor_folder=global_dir) == {"MY_VAR": "hello"}


def test_load_project_env_vars_missing_file(tmp_path: Path) -> None:
    global_dir = tmp_path / "global_sculptor"
    global_dir.mkdir()
    assert load_project_env_vars(tmp_path, sculptor_folder=global_dir) == {}


def test_load_global_env_vars(tmp_path: Path) -> None:
    global_dir = tmp_path / "global_sculptor"
    global_dir.mkdir()
    (global_dir / ".env").write_text("GLOBAL_VAR=from_global\n")
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    assert load_project_env_vars(project_dir, sculptor_folder=global_dir) == {"GLOBAL_VAR": "from_global"}


def test_project_env_vars_override_global(tmp_path: Path) -> None:
    global_dir = tmp_path / "global_sculptor"
    global_dir.mkdir()
    (global_dir / ".env").write_text("SHARED=global_value\nGLOBAL_ONLY=g\n")
    project_dir = tmp_path / "project"
    sculptor_dir = project_dir / ".sculptor"
    sculptor_dir.mkdir(parents=True)
    (sculptor_dir / ".env").write_text("SHARED=project_value\nPROJECT_ONLY=p\n")
    result = load_project_env_vars(project_dir, sculptor_folder=global_dir)
    assert result == {"SHARED": "project_value", "GLOBAL_ONLY": "g", "PROJECT_ONLY": "p"}


def test_atomic_copy_env_file_creates_destination(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    source.write_text("VAR=value\n")
    dest = tmp_path / "subdir" / ".env"
    atomic_copy_env_file(source, dest)
    assert dest.read_text() == "VAR=value\n"


def test_atomic_copy_env_file_overwrites_existing(tmp_path: Path) -> None:
    source = tmp_path / "source.env"
    source.write_text("NEW=new\n")
    dest = tmp_path / ".env"
    dest.write_text("OLD=old\n")
    atomic_copy_env_file(source, dest)
    assert dest.read_text() == "NEW=new\n"


def test_atomic_copy_env_file_concurrent_reads_never_see_partial(tmp_path: Path) -> None:
    """Regression test for SCU-731.

    A non-atomic ``shutil.copy2(source, dest)`` truncates ``dest`` before
    writing, so a concurrent reader can land in the truncate window and parse
    an empty file. Hammer concurrent copies and reads in parallel and assert
    every read sees the fully-written contents.
    """
    source = tmp_path / "source.env"
    source.write_text("RACE_VAR=expected\n")
    dest = tmp_path / "dest" / ".env"
    atomic_copy_env_file(source, dest)

    stop = threading.Event()
    failures: list[dict[str, str]] = []

    def writer() -> None:
        while not stop.is_set():
            atomic_copy_env_file(source, dest)

    def reader() -> None:
        while not stop.is_set():
            parsed = parse_env_file(dest)
            if parsed != {"RACE_VAR": "expected"}:
                failures.append(parsed)
                return

    threads = [threading.Thread(target=writer) for _ in range(4)]
    threads += [threading.Thread(target=reader) for _ in range(4)]
    for t in threads:
        t.start()
    # Long enough to land thousands of read/write interleavings on a typical
    # machine — non-atomic shutil.copy2 fails this within milliseconds.
    threading.Event().wait(0.5)
    stop.set()
    for t in threads:
        t.join()

    assert not failures, f"Reader observed truncated/partial env file: {failures[0]!r}"
