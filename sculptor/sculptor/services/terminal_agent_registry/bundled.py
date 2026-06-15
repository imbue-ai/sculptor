"""Install the bundled Claude Code registration on first run.

Sculptor ships `samples/terminal_agents/claude-code/` both as the reference
example for registration authors and as a registration every user gets out
of the box. At backend startup the two files are copied once into the user's
registrations directory, where they are ordinary user-owned files:

- Existing files are never overwritten, so user edits stick.
- A sentinel records that the install happened, so deleting the files is
  permanent — they are not re-installed on the next start.

The registry itself stays unaware of all this: after installation the
registration is indistinguishable from a hand-written one.
"""

from pathlib import Path

from loguru import logger

from sculptor.common.plugin import get_plugins_base_dir
from sculptor.services.terminal_agent_registry.registry import get_registrations_dir

_SENTINEL_FILE_NAME = ".claude-code.installed"
_BUNDLED_FILE_NAMES = ("claude-code.toml", "claude-code-hooks.json")
_HOOKS_FILE_NAME = "claude-code-hooks.json"
# Named placeholder the sample TOML carries in place of its hooks-file path;
# the installer rewrites it to the absolute, shell-quoted path where the hooks
# actually land (see _install_claude_code_registration). A named token avoids
# matching a brittle hardcoded path string and keeps the manual-install
# substitution point obvious — see the comment beside it in claude-code.toml.
# Deliberately NOT a {brace} token: the registration loader reserves {…} for
# the launch-time {session_id} placeholder and rejects any other brace token,
# so an install-time token must use a distinct syntax.
_SAMPLE_HOOKS_PATH_TOKEN = "__SCULPTOR_HOOKS_PATH__"


def get_bundled_claude_code_dir() -> Path | None:
    """Locate the shipped claude-code sample directory, or None if absent.

    Packaged app: bundled as data next to the plugins (`_internal/samples/…`).
    Running from source: `samples/` at the repo root.
    """
    base = get_plugins_base_dir()
    # Two candidates, one per layout (probed in order):
    #  - Packaged app: get_plugins_base_dir() is the PyInstaller `_internal/`
    #    dir, and the build bundles samples as data at `_internal/samples/…`
    #    (see build-sidecar.sh), so the sample is at `base / "samples"`.
    #  - Source checkout: get_plugins_base_dir() is `<repo>/sculptor/` (the
    #    project dir), while `samples/` lives at the repo root one level up,
    #    so the sample is at `base.parent / "samples"`.
    candidates = (
        base / "samples" / "terminal_agents" / "claude-code",
        base.parent / "samples" / "terminal_agents" / "claude-code",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return None


def install_bundled_registrations() -> None:
    """Copy the bundled Claude Code registration into the registrations dir, once.

    Failure is never fatal — a missing sample or unwritable directory costs
    the menu entry, not startup.
    """
    try:
        _install_claude_code_registration()
    except OSError as e:
        # Info level per the no-logger-warning ratchet (matching the loader).
        logger.info("Could not install the bundled Claude Code registration: {}", e)


def _install_claude_code_registration() -> None:
    registrations_dir = get_registrations_dir()
    sentinel = registrations_dir / _SENTINEL_FILE_NAME
    if sentinel.exists():
        return
    source_dir = get_bundled_claude_code_dir()
    if source_dir is None:
        logger.info("Bundled Claude Code sample not found; skipping registration install")
        return

    registrations_dir.mkdir(parents=True, exist_ok=True)
    hooks_destination = registrations_dir / _HOOKS_FILE_NAME
    for file_name in _BUNDLED_FILE_NAMES:
        destination = registrations_dir / file_name
        if destination.exists():
            # The user (or a previous partial install) already has this file.
            continue
        content = (source_dir / file_name).read_text()
        if file_name.endswith(".toml"):
            # Double quotes are safe both inside the TOML literal string and
            # in the shell (handles spaces in the sculptor folder path).
            content = content.replace(_SAMPLE_HOOKS_PATH_TOKEN, f'"{hooks_destination}"')
        destination.write_text(content)
        logger.info("Installed bundled terminal-agent file {}", destination)
    sentinel.write_text(
        "The bundled Claude Code registration was installed once into this directory.\n"
        + "This marker makes deleting claude-code.toml permanent — remove it to have\n"
        + "Sculptor re-install the registration on the next start.\n"
    )
