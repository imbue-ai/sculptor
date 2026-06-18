from pathlib import Path

from loguru import logger

from sculptor.utils import build as build_utils

_FORMAT_VERSION = "1"
_FORMAT_VERSION_FILENAME = ".format_version"


def _bootstrap_sculptor_folder(sculptor_path: Path) -> None:
    """Ensure the sculptor folder has the expected structure and version marker."""
    logger.info("Bootstrapping Sculptor folder at {}", sculptor_path)
    (sculptor_path / "internal").mkdir(parents=True, exist_ok=True)
    (sculptor_path / "workspaces").mkdir(parents=True, exist_ok=True)
    (sculptor_path / _FORMAT_VERSION_FILENAME).write_text(f"{_FORMAT_VERSION}\n")


def ensure_sculptor_folder_ready() -> None:
    """Ensure the Sculptor data folder is in the expected format.

    If the format version marker is missing, bootstraps the folder structure
    and writes the marker.  This handles both fresh installs and cases where
    the folder was created without the marker (e.g. dev/test environments).
    """
    sculptor_path = build_utils.get_sculptor_folder()

    if (sculptor_path / _FORMAT_VERSION_FILENAME).is_file():
        return

    _bootstrap_sculptor_folder(sculptor_path)
