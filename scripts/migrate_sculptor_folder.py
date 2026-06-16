"""Standalone migration script for Sculptor data directory.

Migrates from the old layout (~/.sculptor_data) to the new layout (~/.sculptor)
with internal/, workspaces/, and .format_version structure.

Two modes:
  Relocate: moves data from old path to new path (default, or --dev)
  In-place: restructures a folder at --path without changing its location

Usage:
    python scripts/migrate_sculptor_folder.py              # Production relocate
    python scripts/migrate_sculptor_folder.py --dev        # Dev relocate
    python scripts/migrate_sculptor_folder.py --path DIR   # In-place restructure
    python scripts/migrate_sculptor_folder.py --dry-run    # Preview changes
"""

import argparse
import re
import shutil
import sqlite3
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Migrate Sculptor data directory from old layout to new layout.",
    )
    parser.add_argument(
        "--dev",
        action="store_true",
        help="Migrate dev directory (~/.dev-sculptor_data -> ~/.dev-sculptor) instead of production",
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=None,
        help="Migrate a folder in-place (restructure without relocating). Mutually exclusive with --dev.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be done without making changes",
    )
    return parser.parse_args()


def _get_paths(dev: bool) -> tuple[Path, Path]:
    """Return (old_path, new_path) for the migration."""
    if dev:
        return (Path.home() / ".dev-sculptor_data", Path.home() / ".dev-sculptor")
    else:
        return (Path.home() / ".sculptor_data", Path.home() / ".sculptor")


def _backup_database(db_path: Path, dry_run: bool) -> Path | None:
    """Create a sqlite-native backup of the database before modifying it.

    Uses sqlite3.Connection.backup() which safely handles WAL mode — no need to
    worry about copying .wal or .shm files.
    """
    if not db_path.exists():
        return None

    backup_path = db_path.parent / "database.pre_migration_backup.db"
    if dry_run:
        print(f"  Would backup database to {backup_path}")
        return backup_path

    print(f"  Backing up database to {backup_path}...")
    source = sqlite3.connect(str(db_path))
    try:
        dest = sqlite3.connect(str(backup_path))
        try:
            source.backup(dest)
        finally:
            dest.close()
    finally:
        source.close()
    return backup_path


def _update_database_paths(db_path: Path, old_prefix: str, new_prefix: str, dry_run: bool) -> None:
    """Update environment_id paths in workspace tables."""
    if not db_path.exists():
        print(f"  Database not found at {db_path}, skipping path updates.")
        return

    if dry_run:
        print(f"  Would update database paths in {db_path}:")
        print(f"    REPLACE '{old_prefix}' -> '{new_prefix}' in workspace.environment_id")
        print(f"    REPLACE '{old_prefix}' -> '{new_prefix}' in workspace_latest.environment_id")
        return

    print(f"  Updating database paths in {db_path}...")
    conn = sqlite3.connect(str(db_path))
    try:
        cursor = conn.cursor()

        cursor.execute(
            "UPDATE workspace_latest SET environment_id = REPLACE(environment_id, ?, ?) WHERE environment_id LIKE ?",
            (old_prefix, new_prefix, old_prefix + "%"),
        )
        print(f"    workspace_latest: {cursor.rowcount} rows updated")

        cursor.execute(
            "UPDATE workspace SET environment_id = REPLACE(environment_id, ?, ?) WHERE environment_id LIKE ?",
            (old_prefix, new_prefix, old_prefix + "%"),
        )
        print(f"    workspace: {cursor.rowcount} rows updated")

        conn.commit()
    finally:
        conn.close()


def _move_entry(src: Path, dst: Path, dry_run: bool) -> None:
    """Move src to dst via atomic rename. Exits if dst already exists."""
    if dst.exists():
        print(
            f"Error: destination already exists: {dst}\n"
            + "This may indicate a partially completed migration. "
            + "Please inspect and resolve manually, then re-run.",
            file=sys.stderr,
        )
        sys.exit(1)
    if dry_run:
        print(f"  Would move {src} -> {dst}")
    else:
        print(f"  Moving {src.name}")
        src.rename(dst)


def _encode_cwd(path: str) -> str:
    """Encode a path the way Claude Code does for session folder names.

    Every non-alphanumeric character (except ``-``) is replaced with ``-``.
    Hyphens are preserved as-is.

    This matches the canonical implementation in
    ``sculptor/agents/default/claude_code_sdk/harness.py::compute_claude_jsonl_directory``.
    """
    return re.sub(r"[^a-zA-Z0-9-]", "-", path)


def _migrate_claude_sessions(
    workspaces_dir: Path,
    old_prefix: str,
    new_prefix: str,
    dry_run: bool,
    claude_projects_dir: Path | None = None,
) -> None:
    """Rename Claude Code session folders so sessions can be resumed after migration.

    Claude stores sessions in ``~/.claude/projects/<encoded-cwd>/*.jsonl`` where
    ``<encoded-cwd>`` is the absolute working directory with every non-alphanumeric
    character (except ``-``) replaced by ``-``.

    When we move the sculptor data directory the working directory of every clone-mode
    workspace changes, so we need to rename the corresponding session folder.
    """
    claude_projects = claude_projects_dir or Path.home() / ".claude" / "projects"
    if not claude_projects.is_dir():
        print("  No ~/.claude/projects directory found, skipping session migration.")
        return

    if not workspaces_dir.is_dir():
        print("  No workspaces directory found, skipping session migration.")
        return

    migrated = 0
    for workspace in sorted(workspaces_dir.iterdir()):
        if not workspace.is_dir():
            continue
        # Clone-mode workspaces have a code/ subdirectory that is the actual cwd.
        code_dir = workspace / "code"
        if not code_dir.is_dir():
            continue

        old_cwd = str(code_dir).replace(new_prefix, old_prefix, 1)
        new_cwd = str(code_dir)
        old_encoded = _encode_cwd(old_cwd)
        new_encoded = _encode_cwd(new_cwd)

        old_session_dir = claude_projects / old_encoded
        new_session_dir = claude_projects / new_encoded

        if not old_session_dir.is_dir():
            continue

        if new_session_dir.exists():
            if dry_run:
                print(f"  Would skip {old_session_dir.name} (destination already exists)")
            else:
                print(f"  Skipping {old_session_dir.name} (destination already exists)")
            continue

        if dry_run:
            print(f"  Would rename session folder:\n    {old_session_dir.name}\n    -> {new_session_dir.name}")
        else:
            old_session_dir.rename(new_session_dir)
            migrated += 1

    if not dry_run:
        print(f"  Migrated {migrated} Claude session folder(s).")


_SKIP_NAMES = {"internal", "workspaces", ".format_version", ".env"}


_TOP_LEVEL_FILES = {".env"}


def migrate_in_place(target: Path, dry_run: bool) -> None:
    """Restructure a folder from the flat layout to the new layout in-place.

    Moves all top-level items (except workspaces/) into internal/ and writes
    the .format_version marker.  No directory rename or DB path update is needed
    because the folder's location doesn't change.
    """
    if not target.is_dir():
        print(f"No directory found at {target}, nothing to migrate.")
        return

    if (target / ".format_version").is_file():
        print("Already in new format, nothing to do.")
        return

    # Step 1: Create internal/
    internal = target / "internal"
    if dry_run:
        print(f"Would create {internal}")
    else:
        print(f"Step 1: Creating {internal}")
        internal.mkdir(exist_ok=True)

    # Step 2: Move everything except workspaces/, internal/, .format_version into internal/
    if dry_run:
        print("Would move files to internal/:")
    else:
        print("Step 2: Moving files to internal/...")

    for child in sorted(target.iterdir()):
        if child.name in _SKIP_NAMES:
            continue
        _move_entry(child, internal / child.name, dry_run)

    # No DB backup or path update needed -- the folder path hasn't changed,
    # so workspace environment_id values are still correct.

    # Step 3: Write .format_version
    format_version_path = target / ".format_version"
    if dry_run:
        print(f"Would write {format_version_path}")
    else:
        print(f"Step 3: Writing {format_version_path}")
        format_version_path.write_text("1\n")

    print("In-place migration complete!")


def migrate(
    old_path: Path,
    new_path: Path,
    dry_run: bool,
    claude_projects_dir: Path | None = None,
) -> None:
    """Run the migration from old_path to new_path."""
    migrating_path = old_path.parent / (old_path.name + ".migrating")

    # Pre-flight checks
    format_version_exists = (new_path / ".format_version").is_file()
    old_exists = old_path.is_dir()
    migrating_exists = migrating_path.is_dir()

    if format_version_exists and not old_exists and not migrating_exists:
        print("Migration already complete, nothing to do.")
        return

    if not old_exists and not migrating_exists:
        print(f"No old directory found at {old_path}, nothing to migrate.")
        return

    if old_exists and migrating_exists:
        print(
            f"Error: Both {old_path} and {migrating_path} exist. This is an unexpected state. Please remove one and re-run.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Step 1: Rename to .migrating
    if old_exists:
        if dry_run:
            print(f"Would rename {old_path} -> {migrating_path}")
        else:
            print(f"Step 1: Renaming {old_path} -> {migrating_path}")
            try:
                old_path.rename(migrating_path)
            except (PermissionError, OSError) as e:
                print(f"Error: Failed to rename {old_path}: {e}", file=sys.stderr)
                sys.exit(1)
    else:
        print(f"Step 1: Resuming interrupted migration from {migrating_path}")

    # Step 2: Create target structure
    if dry_run:
        print(f"Would create {new_path / 'internal'}")
    else:
        print(f"Step 2: Creating {new_path / 'internal'}")
        (new_path / "internal").mkdir(parents=True, exist_ok=True)

    # Step 3: Move workspaces/
    src_workspaces = migrating_path / "workspaces"
    dst_workspaces = new_path / "workspaces"
    if src_workspaces.is_dir() and not dst_workspaces.exists():
        if dry_run:
            print(f"Would move {src_workspaces} -> {dst_workspaces}")
        else:
            print(f"Step 3: Moving workspaces/ -> {dst_workspaces}")
            src_workspaces.rename(dst_workspaces)
    elif dst_workspaces.exists():
        print("Step 3: workspaces/ already at target, skipping.")
    else:
        print("Step 3: No workspaces/ directory found, skipping.")

    # Step 4: Move remaining items to internal/ (except top-level files like .env)
    if not dry_run:
        print("Step 4: Moving remaining files to internal/...")
    else:
        print("Would move remaining files to internal/:")

    for child in sorted(migrating_path.iterdir()):
        if child.name in _TOP_LEVEL_FILES:
            dst = new_path / child.name
            if dst.exists():
                old_dst = new_path / (child.name + ".old")
                if dry_run:
                    print(f"  Would move existing {dst} -> {old_dst}")
                else:
                    print(f"  Moving existing {dst.name} -> {old_dst.name}")
                    dst.rename(old_dst)
            _move_entry(child, dst, dry_run)
        else:
            _move_entry(child, new_path / "internal" / child.name, dry_run)

    # Step 5: Backup database before modification
    db_path = new_path / "internal" / "database.db"
    if dry_run:
        print("Step 5: Database backup:")
    else:
        print("Step 5: Backing up database...")
    _backup_database(db_path, dry_run)

    # Step 6: Update database paths
    old_prefix = str(old_path)
    new_prefix = str(new_path)
    if dry_run:
        print("Step 6: Database path updates:")
    else:
        print("Step 6: Updating database paths...")
    _update_database_paths(db_path, old_prefix, new_prefix, dry_run)

    # Step 7: Migrate Claude Code session folders
    if dry_run:
        print("Step 7: Claude session folder migration:")
    else:
        print("Step 7: Migrating Claude session folders...")
    _migrate_claude_sessions(dst_workspaces, old_prefix, new_prefix, dry_run, claude_projects_dir)

    # Step 8: Write .format_version
    format_version_path = new_path / ".format_version"
    if dry_run:
        print(f"Would write {format_version_path}")
    else:
        print(f"Step 8: Writing {format_version_path}")
        format_version_path.write_text("1\n")

    # Step 9: Cleanup
    if dry_run:
        print(f"Would remove {migrating_path}")
    else:
        print(f"Step 9: Cleaning up {migrating_path}")
        try:
            shutil.rmtree(migrating_path)
        except OSError as e:
            print(f"  Warning: Could not fully remove {migrating_path}: {e}")

    print("Migration complete!")


def main() -> None:
    args = _parse_args()

    if args.path is not None:
        if args.dev:
            print("Error: --path and --dev are mutually exclusive.", file=sys.stderr)
            sys.exit(1)
        target = args.path.resolve()
        print("Sculptor data directory in-place migration")
        print(f"  Path: {target}")
        if args.dry_run:
            print("  (dry run — no changes will be made)")
        print()
        migrate_in_place(target, args.dry_run)
    else:
        old_path, new_path = _get_paths(args.dev)
        variant = "dev" if args.dev else "production"
        print(f"Sculptor data directory migration ({variant})")
        print(f"  Old: {old_path}")
        print(f"  New: {new_path}")
        if args.dry_run:
            print("  (dry run — no changes will be made)")
        print()
        migrate(old_path, new_path, args.dry_run)


if __name__ == "__main__":
    main()
