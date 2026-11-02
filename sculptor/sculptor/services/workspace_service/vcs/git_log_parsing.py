"""Pure parsers for `git log` output."""

from collections.abc import Callable
from collections.abc import Sequence
from typing import Literal
from typing import TypeVar

COMMIT_SEPARATOR_PREFIX = "COMMIT_SEP:"

CommitFileStatus = Literal["M", "A", "D", "R"]

_ParsedFileData = TypeVar("_ParsedFileData")


def expand_numstat_rename_path(path: str) -> str:
    """Expand git's compact rename notation into the new path.

    `git log --numstat -M` uses compact notation for renames:

    >>> expand_numstat_rename_path("{old => new}/file.py")
    'new/file.py'
    >>> expand_numstat_rename_path("prefix/{old => new}/file.py")
    'prefix/new/file.py'
    >>> expand_numstat_rename_path("old.py => new.py")
    'new.py'
    >>> expand_numstat_rename_path("{old => }/file.py")
    'file.py'
    """
    brace_start = path.find("{")
    if brace_start != -1:
        brace_end = path.find("}", brace_start)
        arrow = path.find(" => ", brace_start)
        if brace_end != -1 and arrow != -1 and arrow < brace_end:
            prefix = path[:brace_start]
            new_part = path[arrow + 4 : brace_end]
            suffix = path[brace_end + 1 :]
            return (prefix + new_part + suffix).lstrip("/")

    arrow = path.find(" => ")
    if arrow != -1:
        return path[arrow + 4 :]

    return path


def parse_numstat_lines(lines: Sequence[str]) -> dict[str, tuple[int, int]]:
    """Parse `--numstat` lines into `{path: (additions, deletions)}`; binary files count as zero."""
    result: dict[str, tuple[int, int]] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        additions = 0 if parts[0] == "-" else int(parts[0])
        deletions = 0 if parts[1] == "-" else int(parts[1])
        path = parts[3] if len(parts) == 4 else parts[2]
        if "=>" in path:
            path = expand_numstat_rename_path(path)
        result[path] = (additions, deletions)
    return result


def parse_name_status_lines(lines: Sequence[str]) -> dict[str, tuple[CommitFileStatus, str | None]]:
    """Parse `--name-status` lines into `{path: (status, old path for renames)}`.

    Statuses other than added, deleted and renamed (a type change, say) count as modified.
    """
    result: dict[str, tuple[CommitFileStatus, str | None]] = {}
    for line in lines:
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith("R"):
            if len(parts) >= 3:
                result[parts[2]] = ("R", parts[1])
        elif status.startswith("A"):
            result[parts[1]] = ("A", None)
        elif status.startswith("D"):
            result[parts[1]] = ("D", None)
        else:
            result[parts[1]] = ("M", None)
    return result


def parse_file_data_by_commit(
    log_output: str, parser: Callable[[Sequence[str]], _ParsedFileData]
) -> dict[str, _ParsedFileData]:
    """Split `git log --format=COMMIT_SEP:%H <file flag>` output per commit and parse each commit's lines."""
    result: dict[str, _ParsedFileData] = {}
    current_hash: str | None = None
    current_lines: list[str] = []
    for line in log_output.split("\n"):
        if line.startswith(COMMIT_SEPARATOR_PREFIX):
            if current_hash is not None:
                result[current_hash] = parser(current_lines)
            current_hash = line[len(COMMIT_SEPARATOR_PREFIX) :]
            current_lines = []
        elif line.strip():
            current_lines.append(line)
    if current_hash is not None:
        result[current_hash] = parser(current_lines)
    return result
