"""Install the bundled Claude Code registration on first run.

Sculptor ships `samples/terminal_agents/claude-code/` both as the reference
example for registration authors and as a registration every user gets out
of the box. At backend startup the two files are copied once into the user's
registrations directory, where they are ordinary user-owned files:

- Existing files are never overwritten, so user edits stick.
- A sentinel records that the install happened, so deleting the files is
  permanent — they are not re-installed on the next start.

The exception is refresh: on every start, any *unmodified* Sculptor-managed
file (the TOML and the hooks JSON) is brought up to the current bundled version
in place, so fixes ship to existing installs. The two files are refreshed
**independently** — a hand-edited copy (its hash is unknown) and a deleted file
(it is absent) are each left untouched, so editing one file never blocks
upgrading the other, and the edits-stick / delete-sticks contract holds.

The registry itself stays unaware of all this: after installation the
registration is indistinguishable from a hand-written one.
"""

import hashlib
from pathlib import Path

from loguru import logger

from sculptor.common.plugin import get_plugins_base_dir
from sculptor.services.terminal_agent_registry.registry import get_registrations_dir

_SENTINEL_FILE_NAME = ".claude-code.installed"
_BUNDLED_FILE_NAMES = ("claude-code.toml", "claude-code-hooks.json")

# Per managed file: the sha256 of every version Sculptor has ever shipped of it.
# An installed copy whose hash is in its file's set is an unmodified
# Sculptor-managed file and may be refreshed in place to the current bundled
# version; any other content is a user edit and is never touched. The files are
# keyed independently, so the two upgrade separately. When a bundled file
# changes, ADD its new hash to that file's set (keep the old ones so the prior
# version still auto-upgrades).
_KNOWN_MANAGED_FILE_SHA256: dict[str, frozenset[str]] = {
    "claude-code.toml": frozenset(
        {
            "f04ba8bc5b7a0730420f05aab2e7bee45d187429322d970c38cd4b4fa4e8dcc3",
        }
    ),
    "claude-code-hooks.json": frozenset(
        {
            "6d608ca2b7a4ed433bd161cdf7c29823120236772c377987dc21306bed898e17",
            "1482d2aa0ae1818205bc33354336173d829754dfefd31823955059e311a9f184",
            "08f8809991efc40d3cc01eca64bfbf3072635c88dbd592a917f25d179d470803",
            "14414cf548315f4da5443a283842f6a0574198205ed8bc5a3deb4ea1cbeb5817",
        }
    ),
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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
    source_dir = get_bundled_claude_code_dir()
    if source_dir is None:
        logger.info("Bundled Claude Code sample not found; skipping registration install")
        return

    sentinel = registrations_dir / _SENTINEL_FILE_NAME
    if not sentinel.exists():
        registrations_dir.mkdir(parents=True, exist_ok=True)
        # Files are copied verbatim: the TOML's {terminal_agents_directory}
        # placeholder is resolved at command-render time (see render_terminal_command),
        # not rewritten here, so the installed registration survives a moved
        # Sculptor folder.
        for file_name in _BUNDLED_FILE_NAMES:
            destination = registrations_dir / file_name
            if destination.exists():
                # The user (or a previous partial install) already has this file.
                continue
            destination.write_text((source_dir / file_name).read_text())
            logger.info("Installed bundled terminal-agent file {}", destination)
        sentinel.write_text(
            "The bundled Claude Code registration was installed once into this directory.\n"
            + "This marker makes deleting claude-code.toml permanent — remove it to have\n"
            + "Sculptor re-install the registration on the next start.\n"
        )

    # Always (post-install too): bring each unmodified managed file up to the
    # current bundled version so fixes reach existing installs. User edits and a
    # deleted file are left untouched, independently per file.
    for file_name, known_hashes in _KNOWN_MANAGED_FILE_SHA256.items():
        _refresh_managed_file(registrations_dir, source_dir, file_name, known_hashes)


def _refresh_managed_file(
    registrations_dir: Path, source_dir: Path, file_name: str, known_hashes: frozenset[str]
) -> None:
    """Overwrite one managed file with the bundled version iff it is unmodified.

    "Unmodified" means its current content hashes to a version Sculptor shipped
    (`known_hashes`). An absent file (user deleted it) or an unknown hash (user
    edited it) is left exactly as-is.
    """
    destination = registrations_dir / file_name
    if not destination.exists():
        return
    current = destination.read_text()
    bundled = (source_dir / file_name).read_text()
    if current == bundled:
        return
    if _sha256(current) not in known_hashes:
        return
    destination.write_text(bundled)
    logger.info("Refreshed Sculptor-managed terminal-agent file {}", destination)
