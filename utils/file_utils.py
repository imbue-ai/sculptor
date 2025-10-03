import os
import shutil
import stat
from pathlib import Path
from typing import Callable


def _ignore_sockets(src, names):
    """
    An ignore function for shutil.copytree that returns a set of
    all Unix domain socket files in the 'names' list.
    """
    src_path = Path(src)
    ignored_names = set()
    for name in names:
        # Get the full path to check the file type
        path = src_path / name
        try:
            # Use lstat to avoid following symlinks
            file_stat = os.lstat(path)
            # Check if the file is a socket
            if stat.S_ISSOCK(file_stat.st_mode):
                print(f"Ignoring socket: {path}")
                ignored_names.add(name)
        except OSError as e:
            # Handle cases where the file might be gone before we check it
            print(f"Could not stat {path}: {e}")
            ignored_names.add(name)

    return ignored_names


def copy_dir(src: Path | str, dest: Path | str, dirs_exist_ok: bool = False, ignore: Callable | None = None) -> None:
    """Copy a directory from src to dest. Meant to replace shutil.copytree"""

    def combined_ignore(src, names):
        custom_ignore_set = set()
        if ignore:
            custom_ignore_set = ignore(src, names)
        socket_ignore_set = _ignore_sockets(src, names)
        return custom_ignore_set | socket_ignore_set

    shutil.copytree(src, dest, dirs_exist_ok=dirs_exist_ok, ignore=combined_ignore)
