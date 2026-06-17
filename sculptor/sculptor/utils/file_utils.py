import os
import shutil
import stat
from collections.abc import Callable
from collections.abc import Sequence
from functools import partial
from pathlib import Path

from loguru import logger

IgnoreFunction = Callable[[Path | str, Sequence[str]], set[str]]


def _ignore_sockets(src: Path | str, names: Sequence[str]) -> set[str]:
    """Return the names that are Unix domain sockets, as an ignore function for shutil.copytree."""
    src_path = Path(src)
    ignored_names: set[str] = set()
    for name in names:
        path = src_path / name
        try:
            # lstat avoids following symlinks.
            file_stat = os.lstat(path)
        except OSError as e:
            # The file may be gone before we check it; ignore it so the copy can proceed.
            logger.debug("Could not stat {}: {}", path, e)
            ignored_names.add(name)
            continue
        if stat.S_ISSOCK(file_stat.st_mode):
            logger.debug("Ignoring socket: {}", path)
            ignored_names.add(name)
    return ignored_names


def _combined_ignore(custom_ignore: IgnoreFunction | None, src: Path | str, names: Sequence[str]) -> set[str]:
    custom_ignore_set = custom_ignore(src, names) if custom_ignore else set()
    return custom_ignore_set | _ignore_sockets(src, names)


def copy_dir(
    src: Path | str,
    dest: Path | str,
    dirs_exist_ok: bool = False,
    ignore: IgnoreFunction | None = None,
) -> None:
    """Copy a directory from src to dest, skipping Unix domain sockets. Meant to replace shutil.copytree."""
    shutil.copytree(src, dest, dirs_exist_ok=dirs_exist_ok, ignore=partial(_combined_ignore, ignore))
