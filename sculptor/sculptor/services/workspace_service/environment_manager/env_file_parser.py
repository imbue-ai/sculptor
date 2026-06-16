import os
import shutil
import threading
from pathlib import Path

from sculptor.utils.build import get_sculptor_folder


def atomic_copy_env_file(source: Path, dest: Path) -> None:
    """Replace ``dest`` with a copy of ``source`` atomically.

    ``shutil.copy2`` opens ``dest`` with ``'wb'``, which truncates it to zero
    bytes before any data is written. Under offload's parallel test execution
    several endpoints (``/diff``, ``/files``, ``/skills``) hit
    ``resume_environment`` concurrently, each re-copying the project
    ``.sculptor/.env`` into the workspace clone. A reader running at the same
    time (``create_terminal_for_environment`` calling ``load_project_env_vars``)
    can land in that truncate window and parse an empty file — surfacing as
    SCU-731's "terminal didn't see SCTEST_TERMINAL_VAR" flake.

    Writing to a sibling temp file and then ``os.replace``-ing it onto ``dest``
    keeps readers on the previous, fully-written copy until the rename swaps in
    the new contents in a single atomic step.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dest = dest.with_name(f"{dest.name}.sculptor_tmp_{os.getpid()}_{threading.get_ident()}")
    try:
        shutil.copy2(source, tmp_dest)
        os.replace(tmp_dest, dest)
    finally:
        # Cleans up after a mid-copy failure; ``os.replace`` already consumed
        # the temp on the success path, so ``missing_ok`` keeps both branches
        # quiet.
        tmp_dest.unlink(missing_ok=True)


def parse_env_file(path: Path) -> dict[str, str]:
    """Parse a ``.env`` file into a mapping of variable names to values.

    Supports ``export`` prefixes, single/double quoted values, and inline
    comments. Returns an empty mapping if the file does not exist.
    """
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("export "):
            stripped = stripped[len("export ") :]

        if "=" not in stripped:
            continue

        eq_idx = stripped.index("=")
        name = stripped[:eq_idx].strip()
        raw_value = stripped[eq_idx + 1 :]

        if not name or " " in name or "\t" in name:
            continue

        value = _extract_value(raw_value)
        result[name] = value

    return result


def _extract_value(raw_value: str) -> str:
    if raw_value.startswith('"'):
        close_idx = raw_value.find('"', 1)
        if close_idx == -1:
            return raw_value[1:]
        return raw_value[1:close_idx]

    if raw_value.startswith("'"):
        close_idx = raw_value.find("'", 1)
        if close_idx == -1:
            return raw_value[1:]
        return raw_value[1:close_idx]

    space_hash_idx = raw_value.find(" #")
    if space_hash_idx != -1:
        raw_value = raw_value[:space_hash_idx]

    return raw_value.strip()


def load_project_env_vars(working_directory: Path, sculptor_folder: Path | None = None) -> dict[str, str]:
    """Load env vars from global (~/.sculptor/.env) and project (.sculptor/.env).

    Project-level vars take precedence over global ones.
    """
    resolved_folder = sculptor_folder if sculptor_folder is not None else get_sculptor_folder()
    global_path = resolved_folder / ".env"
    project_path = working_directory / ".sculptor" / ".env"
    env_vars = parse_env_file(global_path)
    env_vars.update(parse_env_file(project_path))
    return env_vars
