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
_SESSION_ID_PLACEHOLDER = "{session_id}"
_PLACEHOLDER_PATTERN = re.compile(r"\{[^}]*\}")


class TerminalAgentRegistration(SerializableModel):
    """A registered terminal agent, validated from one TOML file.

    The TOML body carries everything except ``registration_id``, which is
    derived from the filename stem.
    """

    registration_id: str
    display_name: str
    launch_command: str
    # May contain the literal `{session_id}` placeholder (at most once, no
    # other placeholders) — it is rendered with `str.replace`, not `.format`.
    resume_command_template: str | None = None
    accepts_automated_prompts: bool = False

    @model_validator(mode="after")
    def _validate_resume_command_template(self) -> "TerminalAgentRegistration":
        template = self.resume_command_template
        if template is None:
            return self
        placeholders = _PLACEHOLDER_PATTERN.findall(template)
        if any(placeholder != _SESSION_ID_PLACEHOLDER for placeholder in placeholders):
            raise ValueError(
                f"resume_command_template may only contain the {_SESSION_ID_PLACEHOLDER} placeholder; got {placeholders}"
            )
        if len(placeholders) > 1:
            raise ValueError(f"resume_command_template may contain {_SESSION_ID_PLACEHOLDER} at most once")
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
