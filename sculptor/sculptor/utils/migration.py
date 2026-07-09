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


def get_extensions_directory() -> Path:
    """Resolve the drop-in extensions directory, adopting the legacy layout.

    Extensions live in the data folder's ``extensions/`` subdirectory. Installs
    that predate the "extensions" name keep their files under ``plugins/``; when
    ``extensions/`` is absent and that legacy directory exists, it is renamed in
    place so the user's drop-in extensions keep loading. An existing
    ``extensions/`` directory is never clobbered — a leftover legacy directory
    is then simply ignored. This only resolves (and migrates) the path; callers
    that need the directory to exist create it themselves.
    """
    sculptor_path = build_utils.get_sculptor_folder()
    extensions_dir = sculptor_path / "extensions"
    legacy_dir = sculptor_path / "plugins"
    if not extensions_dir.exists() and legacy_dir.is_dir():
        try:
            legacy_dir.rename(extensions_dir)
            logger.info("Renamed legacy extensions directory {} to {}", legacy_dir, extensions_dir)
        except OSError as e:
            logger.info("Failed to rename legacy extensions directory {}: {}", legacy_dir, e)
    return extensions_dir


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
