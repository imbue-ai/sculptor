import plistlib
import shutil
import subprocess
import sys
from pathlib import Path
from typing import assert_never

from loguru import logger

from sculptor.foundation.processes.local_process import run_blocking
from sculptor.foundation.subprocess_utils import ProcessSetupError
from sculptor.foundation.subprocess_utils import ProcessTimeoutError
from sculptor.web.data_types import ExternalApp
from sculptor.web.data_types import OpenPathInAppResult

# Maps ExternalApp values to macOS bundle identifiers for app discovery via Spotlight.
# Multiple IDs are tried in order (e.g. professional vs community editions).
_EXTERNAL_APP_BUNDLE_IDS: dict[ExternalApp, list[str]] = {
    ExternalApp.FINDER: ["com.apple.finder"],
    ExternalApp.VSCODE: ["com.microsoft.VSCode"],
    ExternalApp.CURSOR: ["com.todesktop.230313mzl4w4u92"],
    ExternalApp.PYCHARM: [
        "com.jetbrains.pycharm",
        "com.jetbrains.pycharm.ce",
        "com.jetbrains.PyCharm-EAP",
    ],
    ExternalApp.GHOSTTY: ["com.mitchellh.ghostty"],
    ExternalApp.ITERM: ["com.googlecode.iterm2"],
    ExternalApp.TERMINAL: ["com.apple.Terminal"],
}

# Maps ExternalApp values to CLI executable names for discovery via shutil.which().
_EXTERNAL_APP_CLI_NAMES: dict[ExternalApp, list[str]] = {
    ExternalApp.FINDER: [],
    ExternalApp.VSCODE: ["code"],
    ExternalApp.CURSOR: ["cursor"],
    ExternalApp.PYCHARM: ["pycharm", "pycharm-community", "charm"],
    ExternalApp.GHOSTTY: ["ghostty"],
    ExternalApp.ITERM: [],
    ExternalApp.TERMINAL: [],
}

# Well-known macOS .app bundle paths (fallback when Spotlight is disabled).
_MACOS_APP_PATHS: dict[ExternalApp, list[str]] = {
    ExternalApp.FINDER: ["/System/Library/CoreServices/Finder.app"],
    ExternalApp.VSCODE: ["/Applications/Visual Studio Code.app"],
    ExternalApp.CURSOR: ["/Applications/Cursor.app"],
    ExternalApp.PYCHARM: ["/Applications/PyCharm.app", "/Applications/PyCharm CE.app"],
    ExternalApp.GHOSTTY: ["/Applications/Ghostty.app"],
    ExternalApp.ITERM: ["/Applications/iTerm.app"],
    ExternalApp.TERMINAL: [
        "/System/Applications/Utilities/Terminal.app",
        "/Applications/Utilities/Terminal.app",
    ],
}

# Terminal emulators to try on Linux, in preference order.
_LINUX_TERMINAL_EXECUTABLES: list[str] = [
    "ghostty",
    "gnome-terminal",
    "konsole",
    "xfce4-terminal",
    "alacritty",
    "kitty",
    "xterm",
]


def _find_cli_executable(app: ExternalApp) -> str | None:
    """Find an app's CLI executable on PATH."""
    for name in _EXTERNAL_APP_CLI_NAMES.get(app, []):
        path = shutil.which(name)
        if path is not None:
            return path
    return None


def _read_bundle_id_from_plist(plist_path: Path) -> str | None:
    """Read CFBundleIdentifier from a macOS Info.plist file."""
    try:
        with plist_path.open("rb") as f:
            plist_data = plistlib.load(f)
        return plist_data.get("CFBundleIdentifier")
    except (OSError, plistlib.InvalidFileException, ValueError):
        return None


def _find_macos_app_bundle(app: ExternalApp) -> str | None:
    """Find a macOS app bundle ID via Spotlight, then well-known paths."""
    for bundle_id in _EXTERNAL_APP_BUNDLE_IDS.get(app, []):
        try:
            result = run_blocking(
                ["mdfind", f"kMDItemCFBundleIdentifier == '{bundle_id}'"],
                timeout=5,
                is_checked=False,
            )
            paths = [p.strip() for p in result.stdout.strip().splitlines() if p.strip()]
            if paths:
                return bundle_id
        except (ProcessTimeoutError, ProcessSetupError):
            continue

    for known_path in _MACOS_APP_PATHS.get(app, []):
        app_path = Path(known_path)
        if app_path.exists():
            plist_path = app_path / "Contents" / "Info.plist"
            bundle_id = _read_bundle_id_from_plist(plist_path)
            if bundle_id is not None:
                return bundle_id
    return None


def _find_linux_terminal() -> str | None:
    """Find the first available terminal emulator on Linux."""
    for name in _LINUX_TERMINAL_EXECUTABLES:
        path = shutil.which(name)
        if path is not None:
            return path
    return None


def _get_app_launch_info(app: ExternalApp, target_path: Path) -> tuple[list[str], Path | None] | None:
    """Build the command to open a path in the given external app.

    Returns (command, optional_cwd) or None if the app is not available.
    """
    if sys.platform == "darwin":
        return _get_macos_launch_info(app, target_path)
    elif sys.platform.startswith("linux"):
        return _get_linux_launch_info(app, target_path)
    else:
        return None


def _get_macos_launch_info(app: ExternalApp, target_path: Path) -> tuple[list[str], Path | None] | None:
    """Build launch command for macOS."""
    match app:
        case ExternalApp.FINDER:
            return (["open", str(target_path)], None)
        case ExternalApp.TERMINAL:
            bundle_id = _find_macos_app_bundle(app)
            if bundle_id is not None:
                return (["open", "-b", bundle_id, str(target_path)], None)
            return None
        case ExternalApp.ITERM:
            bundle_id = _find_macos_app_bundle(app)
            if bundle_id is not None:
                return (["open", "-b", bundle_id, str(target_path)], None)
            return None
        case ExternalApp.GHOSTTY:
            bundle_id = _find_macos_app_bundle(app)
            if bundle_id is not None:
                return (["open", "-b", bundle_id, str(target_path)], None)
            cli_path = _find_cli_executable(app)
            if cli_path is not None:
                cwd = target_path if target_path.is_dir() else target_path.parent
                return ([cli_path], cwd)
            return None
        case ExternalApp.VSCODE:
            return _macos_launch_editor(app, target_path)
        case ExternalApp.CURSOR:
            return _macos_launch_editor(app, target_path)
        case ExternalApp.PYCHARM:
            return _macos_launch_editor(app, target_path)
        case _ as unreachable:
            assert_never(unreachable)


def _macos_launch_editor(app: ExternalApp, target_path: Path) -> tuple[list[str], Path | None] | None:
    """Try CLI first, then bundle for editors/IDEs on macOS."""
    cli_path = _find_cli_executable(app)
    if cli_path is not None:
        return ([cli_path, str(target_path)], None)
    bundle_id = _find_macos_app_bundle(app)
    if bundle_id is not None:
        return (["open", "-b", bundle_id, str(target_path)], None)
    return None


def _get_linux_launch_info(app: ExternalApp, target_path: Path) -> tuple[list[str], Path | None] | None:
    """Build launch command for Linux."""
    match app:
        case ExternalApp.FINDER:
            return (["xdg-open", str(target_path)], None)
        case ExternalApp.ITERM:
            return None
        case ExternalApp.TERMINAL:
            terminal = _find_linux_terminal()
            if terminal is not None:
                cwd = target_path if target_path.is_dir() else target_path.parent
                return ([terminal], cwd)
            return None
        case ExternalApp.VSCODE:
            return _linux_launch_cli_app(app, target_path)
        case ExternalApp.CURSOR:
            return _linux_launch_cli_app(app, target_path)
        case ExternalApp.PYCHARM:
            return _linux_launch_cli_app(app, target_path)
        case ExternalApp.GHOSTTY:
            return _linux_launch_cli_app(app, target_path)
        case _ as unreachable:
            assert_never(unreachable)


def _linux_launch_cli_app(app: ExternalApp, target_path: Path) -> tuple[list[str], Path | None] | None:
    """Try to find and launch a CLI app on Linux."""
    cli_path = _find_cli_executable(app)
    if cli_path is not None:
        return ([cli_path, str(target_path)], None)
    return None


def open_path_in_external_app(app: ExternalApp, path: Path) -> OpenPathInAppResult:
    """Open a file system path in an external application."""
    if not path.exists():
        return OpenPathInAppResult(success=False, error_message=f"Path does not exist: {path}")

    launch_info = _get_app_launch_info(app, path)
    if launch_info is None:
        return OpenPathInAppResult(success=False, error_message=f"{app.value} is not installed")

    command, cwd = launch_info
    logger.debug("Opening path in {}: {}", app.value, path)

    try:
        subprocess.Popen(command, cwd=cwd)
    except OSError as e:
        return OpenPathInAppResult(success=False, error_message=f"Failed to open {app.value}: {e}")

    return OpenPathInAppResult(success=True)
