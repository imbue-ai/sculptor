"""Declarative terminal-agent registrations.

One TOML file per registration under ``<sculptor folder>/terminal_agents/``;
the ``registration_id`` IS the filename stem (``claude-code.toml`` →
``claude-code``) — unique by construction and stable across edits (a rename
changes identity, but tasks stamped from the old id keep working because the
config is resolved at creation). Deliberately NOT part of `UserConfig`.

Every consumer re-reads the directory (it is tiny), so menu contents track
the filesystem without restarts and without cache-invalidation bugs.
"""

import re
import tomllib
from pathlib import Path

from loguru import logger
from pydantic import ValidationError
from pydantic import model_validator

from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.utils.build import get_sculptor_folder

_REGISTRATIONS_DIR_NAME = "terminal_agents"
_REGISTRATION_ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")

# The replacement placeholders a registration's commands may contain, each
# substituted with a concrete value at command-render time (see
# `render_terminal_command` in the terminal-session module). Directory
# placeholders resolve to absolute paths and are valid in any command;
# `{session_id}` is only meaningful in `resume_command_template` (there is no
# session at first launch). The loader rejects any other `{…}` token so a typo
# fails loudly here instead of surviving verbatim into the launched command.
SESSION_ID_PLACEHOLDER = "{session_id}"
SCULPTOR_DIRECTORY_PLACEHOLDER = "{sculptor_directory}"
TERMINAL_AGENTS_DIRECTORY_PLACEHOLDER = "{terminal_agents_directory}"
_DIRECTORY_PLACEHOLDERS = frozenset({SCULPTOR_DIRECTORY_PLACEHOLDER, TERMINAL_AGENTS_DIRECTORY_PLACEHOLDER})
_LAUNCH_COMMAND_PLACEHOLDERS = _DIRECTORY_PLACEHOLDERS
_RESUME_COMMAND_PLACEHOLDERS = _DIRECTORY_PLACEHOLDERS | {SESSION_ID_PLACEHOLDER}
_PLACEHOLDER_PATTERN = re.compile(r"\{[^}]*\}")


def _reject_unknown_placeholders(command: str, allowed: frozenset[str], field_name: str) -> None:
    unknown = sorted({p for p in _PLACEHOLDER_PATTERN.findall(command) if p not in allowed})
    if unknown:
        raise ValueError(
            f"{field_name} contains unsupported placeholder(s) {unknown}; allowed: {', '.join(sorted(allowed))}"
        )


class TerminalAgentRegistration(SerializableModel):
    """A registered terminal agent, validated from one TOML file.

    The TOML body carries everything except ``registration_id``, which is
    derived from the filename stem.
    """

    registration_id: str
    display_name: str
    # May contain the directory placeholders; rendered with `str.replace` at
    # launch (see `render_terminal_command`), NOT `.format`.
    launch_command: str
    # May contain `{session_id}` plus the directory placeholders, same render.
    resume_command_template: str | None = None
    accepts_automated_prompts: bool = False

    @model_validator(mode="after")
    def _validate_command_placeholders(self) -> "TerminalAgentRegistration":
        _reject_unknown_placeholders(self.launch_command, _LAUNCH_COMMAND_PLACEHOLDERS, "launch_command")
        template = self.resume_command_template
        if template is not None:
            _reject_unknown_placeholders(template, _RESUME_COMMAND_PLACEHOLDERS, "resume_command_template")
            # A resume command resumes exactly one session; the directory
            # placeholders may repeat freely, but a second {session_id} is a
            # mistake.
            if template.count(SESSION_ID_PLACEHOLDER) > 1:
                raise ValueError(f"resume_command_template may contain {SESSION_ID_PLACEHOLDER} at most once")
        return self


def get_registrations_dir() -> Path:
    return get_sculptor_folder() / _REGISTRATIONS_DIR_NAME


def load_registrations() -> list[TerminalAgentRegistration]:
    """Load all valid registrations, sorted by id for stable menu order.

    Per-file errors (parse, validation, bad filename stem) are logged (info
    level — the no-logger-warning ratchet) and skipped — one bad file must not
    break the menu. A missing directory yields an empty list (it is created
    lazily by the user).
    """
    registrations_dir = get_registrations_dir()
    if not registrations_dir.is_dir():
        return []
    registrations: list[TerminalAgentRegistration] = []
    for path in sorted(registrations_dir.glob("*.toml")):
        registration_id = path.stem
        if _REGISTRATION_ID_PATTERN.fullmatch(registration_id) is None:
            logger.info("Skipping terminal-agent registration {}: filename stem must match [a-z0-9][a-z0-9_-]*", path)
            continue
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
            registrations.append(TerminalAgentRegistration(registration_id=registration_id, **data))
        except (OSError, tomllib.TOMLDecodeError, ValidationError, TypeError) as e:
            logger.info("Skipping invalid terminal-agent registration {}: {}", path, e)
    return registrations


def get_registration(registration_id: str) -> TerminalAgentRegistration | None:
    """Find one registration by id, re-reading the directory."""
    for registration in load_registrations():
        if registration.registration_id == registration_id:
            return registration
    return None
