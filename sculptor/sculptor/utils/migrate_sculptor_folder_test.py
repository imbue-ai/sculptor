import importlib.util
import os
import sqlite3
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

import pytest


def _load_migration_script() -> ModuleType:
    """Load the standalone migration script as a module."""
    script_path = Path(__file__).resolve().parents[3] / "scripts" / "migrate_sculptor_folder.py"
    spec = importlib.util.spec_from_file_location("migrate_sculptor_folder", script_path)
    assert spec is not None
    loader = spec.loader
    assert loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["migrate_sculptor_folder"] = module
    loader.exec_module(module)
    return module


_script = _load_migration_script()
migrate = _script.migrate
migrate_in_place = _script.migrate_in_place
_get_paths = _script._get_paths
_backup_database = _script._backup_database
_encode_cwd = _script._encode_cwd
_migrate_claude_sessions = _script._migrate_claude_sessions


def _create_old_layout(old_path: Path) -> None:
    """Create a realistic old-layout directory for testing."""
    old_path.mkdir(parents=True)
    (old_path / "config.toml").write_text("")
    (old_path / ".env").write_text("")
    (old_path / "most_recently_used_workspace.txt").write_text("wks_abc123")
    (old_path / "logs").mkdir()
    (old_path / "logs" / "app.log").write_text("log content")
    (old_path / "uploads").mkdir()
    (old_path / "ssh").mkdir()
    (old_path / "ssh" / "ssh").write_text("ssh script")
    (old_path / "workspaces").mkdir()
    (old_path / "workspaces" / "workspace_abc123").mkdir()
    (old_path / "workspaces" / "workspace_abc123" / "file.txt").write_text("data")


def _create_database(db_path: Path, old_prefix: str) -> None:
    """Create a SQLite database with workspace tables containing old paths."""
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE workspace (id TEXT, environment_id TEXT)")
    cursor.execute("CREATE TABLE workspace_latest (id TEXT, environment_id TEXT)")
    cursor.execute(
        "INSERT INTO workspace VALUES (?, ?)",
        ("ws1", f"{old_prefix}/workspaces/workspace_abc123"),
    )
    cursor.execute(
        "INSERT INTO workspace_latest VALUES (?, ?)",
        ("ws1", f"{old_prefix}/workspaces/workspace_abc123"),
    )
    conn.commit()
    conn.close()


def test_full_standard_migration(tmp_path: Path) -> None:
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"

    _create_old_layout(old_path)
    _create_database(old_path / "database.db", str(old_path))

    migrate(old_path, new_path, dry_run=False)

    assert (new_path / ".format_version").read_text().strip() == "1"
    assert (new_path / "internal" / "database.db").is_file()
    assert (new_path / "internal" / "database.pre_migration_backup.db").is_file()
    assert (new_path / "internal" / "config.toml").is_file()
    assert (new_path / ".env").is_file()
    assert (new_path / "internal" / "logs").is_dir()
    assert (new_path / "internal" / "uploads").is_dir()
    assert (new_path / "internal" / "ssh" / "ssh").is_file()
    assert (new_path / "internal" / "most_recently_used_workspace.txt").is_file()
    assert (new_path / "workspaces" / "workspace_abc123" / "file.txt").is_file()
    assert not old_path.exists()
    assert not (tmp_path / ".sculptor_data.migrating").exists()

    conn = sqlite3.connect(str(new_path / "internal" / "database.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT environment_id FROM workspace WHERE id = 'ws1'")
    row = cursor.fetchone()
    assert row is not None
    assert str(new_path) in row[0]
    assert str(old_path) not in row[0]

    cursor.execute("SELECT environment_id FROM workspace_latest WHERE id = 'ws1'")
    row = cursor.fetchone()
    assert row is not None
    assert str(new_path) in row[0]
    assert str(old_path) not in row[0]
    conn.close()


def test_resume_interrupted_migration(tmp_path: Path) -> None:
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"
    migrating_path = tmp_path / ".sculptor_data.migrating"

    migrating_path.mkdir()
    (migrating_path / "config.toml").write_text("")
    (migrating_path / "logs").mkdir()
    (new_path / "workspaces").mkdir(parents=True)

    migrate(old_path, new_path, dry_run=False)

    assert (new_path / "internal" / "config.toml").is_file()
    assert (new_path / "internal" / "logs").is_dir()
    assert (new_path / ".format_version").read_text().strip() == "1"
    assert not migrating_path.exists()


def test_idempotency(tmp_path: Path) -> None:
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"

    _create_old_layout(old_path)
    migrate(old_path, new_path, dry_run=False)
    migrate(old_path, new_path, dry_run=False)

    assert (new_path / ".format_version").read_text().strip() == "1"
    assert not old_path.exists()


def test_database_path_update(tmp_path: Path) -> None:
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"
    old_path.mkdir()
    _create_database(old_path / "database.db", str(old_path))

    migrate(old_path, new_path, dry_run=False)

    conn = sqlite3.connect(str(new_path / "internal" / "database.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT environment_id FROM workspace WHERE id = 'ws1'")
    assert f"{new_path}/workspaces/workspace_abc123" == cursor.fetchone()[0]
    cursor.execute("SELECT environment_id FROM workspace_latest WHERE id = 'ws1'")
    assert f"{new_path}/workspaces/workspace_abc123" == cursor.fetchone()[0]
    conn.close()


@pytest.mark.skipif(os.getuid() == 0, reason="Root ignores filesystem permissions")
def test_permission_failure_exits_with_error(tmp_path: Path) -> None:
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"
    old_path.mkdir()

    tmp_path.chmod(0o555)
    try:
        with pytest.raises(SystemExit) as exc_info:
            migrate(old_path, new_path, dry_run=False)
        assert exc_info.value.code == 1
    finally:
        tmp_path.chmod(0o755)


def test_dev_flag_uses_dev_paths(tmp_path: Path) -> None:
    with patch.object(_script.Path, "home", return_value=tmp_path):
        old_path, new_path = _get_paths(dev=True)
    assert old_path == tmp_path / ".dev-sculptor_data"
    assert new_path == tmp_path / ".dev-sculptor"


def test_production_paths(tmp_path: Path) -> None:
    with patch.object(_script.Path, "home", return_value=tmp_path):
        old_path, new_path = _get_paths(dev=False)
    assert old_path == tmp_path / ".sculptor_data"
    assert new_path == tmp_path / ".sculptor"


def test_unexpected_state_both_old_and_migrating_exist(tmp_path: Path) -> None:
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"
    migrating_path = tmp_path / ".sculptor_data.migrating"
    old_path.mkdir()
    migrating_path.mkdir()

    with pytest.raises(SystemExit) as exc_info:
        migrate(old_path, new_path, dry_run=False)
    assert exc_info.value.code == 1


def test_backup_database_creates_consistent_copy(tmp_path: Path) -> None:
    db_path = tmp_path / "database.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE test_table (id TEXT, value TEXT)")
    cursor.execute("INSERT INTO test_table VALUES ('a', 'hello')")
    cursor.execute("INSERT INTO test_table VALUES ('b', 'world')")
    conn.commit()
    conn.close()

    backup_path = _backup_database(db_path, dry_run=False)

    assert backup_path is not None
    assert backup_path.exists()

    backup_conn = sqlite3.connect(str(backup_path))
    rows = backup_conn.execute("SELECT id, value FROM test_table ORDER BY id").fetchall()
    backup_conn.close()

    assert rows == [("a", "hello"), ("b", "world")]


def test_backup_database_skips_missing_db(tmp_path: Path) -> None:
    db_path = tmp_path / "nonexistent.db"
    result = _backup_database(db_path, dry_run=False)
    assert result is None


def test_backup_database_dry_run(tmp_path: Path) -> None:
    db_path = tmp_path / "database.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE t (id TEXT)")
    conn.commit()
    conn.close()

    backup_path = _backup_database(db_path, dry_run=True)

    assert backup_path is not None
    assert not backup_path.exists()


# --- In-place migration tests ---


def test_in_place_migration(tmp_path: Path) -> None:
    target = tmp_path / "my_sculptor"
    _create_old_layout(target)
    _create_database(target / "database.db", str(target))

    migrate_in_place(target, dry_run=False)

    # New structure
    assert (target / ".format_version").read_text().strip() == "1"
    assert (target / "internal" / "database.db").is_file()
    assert (target / "internal" / "config.toml").is_file()
    assert (target / ".env").is_file()
    assert (target / "internal" / "logs").is_dir()
    assert (target / "internal" / "uploads").is_dir()
    assert (target / "internal" / "ssh" / "ssh").is_file()
    assert (target / "internal" / "most_recently_used_workspace.txt").is_file()
    # workspaces stays at top level
    assert (target / "workspaces" / "workspace_abc123" / "file.txt").is_file()

    # DB paths should NOT have been modified (folder path unchanged)
    conn = sqlite3.connect(str(target / "internal" / "database.db"))
    cursor = conn.cursor()
    cursor.execute("SELECT environment_id FROM workspace WHERE id = 'ws1'")
    assert f"{target}/workspaces/workspace_abc123" == cursor.fetchone()[0]
    cursor.execute("SELECT environment_id FROM workspace_latest WHERE id = 'ws1'")
    assert f"{target}/workspaces/workspace_abc123" == cursor.fetchone()[0]
    conn.close()


def test_in_place_migration_already_migrated(tmp_path: Path) -> None:
    target = tmp_path / "my_sculptor"
    target.mkdir()
    (target / ".format_version").write_text("1\n")

    migrate_in_place(target, dry_run=False)

    # Should be a no-op
    assert (target / ".format_version").read_text().strip() == "1"
    assert not (target / "internal").exists()


def test_in_place_migration_nonexistent_dir(tmp_path: Path) -> None:
    target = tmp_path / "does_not_exist"

    # Should be a no-op, no error
    migrate_in_place(target, dry_run=False)
    assert not target.exists()


def test_in_place_migration_idempotent(tmp_path: Path) -> None:
    target = tmp_path / "my_sculptor"
    _create_old_layout(target)

    migrate_in_place(target, dry_run=False)
    migrate_in_place(target, dry_run=False)

    assert (target / ".format_version").read_text().strip() == "1"
    assert (target / "internal" / "config.toml").is_file()
    assert (target / "workspaces" / "workspace_abc123" / "file.txt").is_file()


def test_env_collision_during_relocate_migration(tmp_path: Path) -> None:
    """When .env exists at the destination, the existing file is moved to .env.old."""
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"

    _create_old_layout(old_path)
    (old_path / ".env").write_text("OLD_KEY=old_value")

    # Pre-create a .env at the destination
    new_path.mkdir(parents=True)
    (new_path / ".env").write_text("EXISTING_KEY=existing_value")

    migrate(old_path, new_path, dry_run=False)

    assert (new_path / ".env").read_text() == "OLD_KEY=old_value"
    assert (new_path / ".env.old").read_text() == "EXISTING_KEY=existing_value"


# --- Claude session migration tests ---


def test_encode_cwd() -> None:
    assert _encode_cwd("/Users/me/.sculptor_data/workspaces/abc/code") == (
        "-Users-me--sculptor-data-workspaces-abc-code"
    )
    assert _encode_cwd("/simple/path") == "-simple-path"
    assert _encode_cwd("abc123") == "abc123"


def test_migrate_claude_sessions_renames_folders(tmp_path: Path) -> None:
    old_prefix = str(tmp_path / ".sculptor_data")
    new_prefix = str(tmp_path / ".sculptor")

    # Set up a workspace with a code/ dir (clone mode)
    workspaces_dir = tmp_path / ".sculptor" / "workspaces"
    ws = workspaces_dir / "ws1" / "code"
    ws.mkdir(parents=True)

    # Create a session folder at the old encoded path
    claude_projects = tmp_path / ".claude" / "projects"
    old_cwd = str(ws).replace(new_prefix, old_prefix, 1)
    old_session = claude_projects / _encode_cwd(old_cwd)
    old_session.mkdir(parents=True)
    (old_session / "session.jsonl").write_text("session data")

    _migrate_claude_sessions(
        workspaces_dir, old_prefix, new_prefix, dry_run=False, claude_projects_dir=claude_projects
    )

    new_session = claude_projects / _encode_cwd(str(ws))
    assert new_session.is_dir()
    assert (new_session / "session.jsonl").read_text() == "session data"
    assert not old_session.exists()


def test_migrate_claude_sessions_skips_existing_destination(tmp_path: Path) -> None:
    old_prefix = str(tmp_path / ".sculptor_data")
    new_prefix = str(tmp_path / ".sculptor")

    workspaces_dir = tmp_path / ".sculptor" / "workspaces"
    ws = workspaces_dir / "ws1" / "code"
    ws.mkdir(parents=True)

    claude_projects = tmp_path / ".claude" / "projects"
    old_cwd = str(ws).replace(new_prefix, old_prefix, 1)
    old_session = claude_projects / _encode_cwd(old_cwd)
    old_session.mkdir(parents=True)
    (old_session / "session.jsonl").write_text("old session data")

    # Pre-create destination with newer data
    new_session = claude_projects / _encode_cwd(str(ws))
    new_session.mkdir(parents=True)
    (new_session / "session.jsonl").write_text("newer data")

    _migrate_claude_sessions(
        workspaces_dir, old_prefix, new_prefix, dry_run=False, claude_projects_dir=claude_projects
    )

    # Existing destination is preserved, old session left in place
    assert new_session.is_dir()
    assert (new_session / "session.jsonl").read_text() == "newer data"
    assert old_session.is_dir()


def test_migrate_claude_sessions_skips_non_clone_workspaces(tmp_path: Path) -> None:
    """Workspaces without a code/ subdir (in-place mode) should be skipped."""
    old_prefix = str(tmp_path / ".sculptor_data")
    new_prefix = str(tmp_path / ".sculptor")

    workspaces_dir = tmp_path / ".sculptor" / "workspaces"
    # In-place workspace: no code/ subdir
    (workspaces_dir / "ws_inplace").mkdir(parents=True)

    claude_projects = tmp_path / ".claude" / "projects"
    claude_projects.mkdir(parents=True)

    # Should not raise
    _migrate_claude_sessions(
        workspaces_dir, old_prefix, new_prefix, dry_run=False, claude_projects_dir=claude_projects
    )


def test_migrate_claude_sessions_no_claude_dir(tmp_path: Path) -> None:
    """Gracefully handles missing ~/.claude/projects."""
    workspaces_dir = tmp_path / ".sculptor" / "workspaces"
    workspaces_dir.mkdir(parents=True)
    claude_projects = tmp_path / ".claude" / "projects"  # does not exist

    # Should not raise
    _migrate_claude_sessions(workspaces_dir, "old", "new", dry_run=False, claude_projects_dir=claude_projects)


def test_migrate_claude_sessions_dry_run(tmp_path: Path) -> None:
    old_prefix = str(tmp_path / ".sculptor_data")
    new_prefix = str(tmp_path / ".sculptor")

    workspaces_dir = tmp_path / ".sculptor" / "workspaces"
    ws = workspaces_dir / "ws1" / "code"
    ws.mkdir(parents=True)

    claude_projects = tmp_path / ".claude" / "projects"
    old_cwd = str(ws).replace(new_prefix, old_prefix, 1)
    old_session = claude_projects / _encode_cwd(old_cwd)
    old_session.mkdir(parents=True)

    _migrate_claude_sessions(workspaces_dir, old_prefix, new_prefix, dry_run=True, claude_projects_dir=claude_projects)

    # Should not have moved anything
    assert old_session.is_dir()
    new_session = claude_projects / _encode_cwd(str(ws))
    assert not new_session.exists()


def test_full_migration_includes_claude_sessions(tmp_path: Path) -> None:
    """The full migrate() flow should rename Claude session folders."""
    old_path = tmp_path / ".sculptor_data"
    new_path = tmp_path / ".sculptor"

    _create_old_layout(old_path)
    # Add a clone-mode workspace with a code/ subdir
    (old_path / "workspaces" / "workspace_abc123" / "code").mkdir(parents=True)

    # Create a session folder for the old workspace path
    claude_projects = tmp_path / ".claude" / "projects"
    old_cwd = str(old_path / "workspaces" / "workspace_abc123" / "code")
    old_session = claude_projects / _encode_cwd(old_cwd)
    old_session.mkdir(parents=True)
    (old_session / "session.jsonl").write_text("my session")

    migrate(old_path, new_path, dry_run=False, claude_projects_dir=claude_projects)

    new_cwd = str(new_path / "workspaces" / "workspace_abc123" / "code")
    new_session = claude_projects / _encode_cwd(new_cwd)
    assert new_session.is_dir()
    assert (new_session / "session.jsonl").read_text() == "my session"
    assert not old_session.exists()
