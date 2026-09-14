"""The naming-convention docs: where each tier lives on the host, and how to read and write them.

A repo (or a user) steers how the agent auto-names its workspace, itself, and its
branch by supplying a `naming.md`. There are three tiers, mirroring Claude Code's
User < Project < Local settings precedence:

- User:    `~/.sculptor/naming.md` — your machine, applies in every repo, never committed.
- Project: `.sculptor/naming.md` — committed, shared by all collaborators on the repo.
- Local:   `.sculptor/naming.local.md` — gitignored, just you in this one repo.

The settings UI reads and writes these files through the API; the first-message
reminder reads them (see `naming_conventions.resolve_naming_conventions`). Both go
through the names and paths defined here, which the .gitignore and the settings copy
also reference, so update those together if these change.
"""

from enum import StrEnum
from pathlib import Path
from typing import assert_never

from loguru import logger

SCULPTOR_CONFIG_DIRNAME = ".sculptor"
NAMING_CONVENTIONS_FILENAME = "naming.md"
NAMING_CONVENTIONS_LOCAL_FILENAME = "naming.local.md"


class NamingConventionTier(StrEnum):
    USER = "user"
    PROJECT = "project"
    LOCAL = "local"


# Starter content the settings editor offers for a file that does not exist yet.
DEFAULT_NAMING_CONVENTIONS_TEMPLATE = """# Naming conventions

How Sculptor's auto-rename should name things. Later files override earlier ones:
your global file, then this repo's shared file, then your local file.

## Workspace name: the task or goal

- 3 to 6 words, sentence case, no trailing period.
- Lead with the ticket ID when there is one.

## Agent name: the action being taken

- Imperative verb first, for example "Write failing tests".

## Branch slug

- When Sculptor asks you to rename the placeholder branch, use a kebab-case slug of
  the workspace name: lowercase ASCII letters, digits, and hyphens, at most 5 words.
"""


def naming_conventions_file_path(tier: NamingConventionTier, sculptor_folder: Path, project_path: Path | None) -> Path:
    """Where a tier's doc lives; `project_path` is the repo root, required for the project and local tiers."""
    match tier:
        case NamingConventionTier.USER:
            return sculptor_folder / NAMING_CONVENTIONS_FILENAME
        case NamingConventionTier.PROJECT:
            return _project_doc(project_path, NAMING_CONVENTIONS_FILENAME)
        case NamingConventionTier.LOCAL:
            return _project_doc(project_path, NAMING_CONVENTIONS_LOCAL_FILENAME)
        case _ as unreachable:
            assert_never(unreachable)


def _project_doc(project_path: Path | None, filename: str) -> Path:
    if project_path is None:
        raise ValueError("A project path is required for the project and local naming-convention tiers")
    return project_path / SCULPTOR_CONFIG_DIRNAME / filename


def read_naming_conventions_file(path: Path) -> str | None:
    """The doc's text, or None when it is absent or unreadable."""
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        logger.warning("Could not read naming conventions at {}: {}", path, e)
        return None


def write_naming_conventions_file(path: Path, content: str) -> None:
    """Store `content` at `path`; blank content removes the file instead."""
    if not content.strip():
        path.unlink(missing_ok=True)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
