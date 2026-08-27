"""Resolve the layered naming-convention docs injected into the auto-rename reminder.

A repo (or a user) can steer how the agent auto-names its workspace and itself by
supplying a `naming.md`. There are three tiers, mirroring Claude Code's
User < Project < Local settings precedence:

- User:    `~/.sculptor/naming.md` — your machine, applies in every repo, never committed.
- Project: `.sculptor/naming.md` — committed, shared by all collaborators on the repo.
- Local:   `.sculptor/naming.local.md` — gitignored, just you in this one repo.

The tiers layer rather than replace: whichever exist are concatenated (least
specific first), and a more-specific tier wins on conflict — the reminder tells
the agent that a later block overrides an earlier one. `naming.local.md` is
therefore the escape hatch for overriding a committed team convention.

The project and local docs live in the repo checkout, so they are read through
the agent environment (which resolves paths correctly in every isolation mode).
The user doc lives on the host next to the user's config, outside any single
repo, so it is read directly from `get_sculptor_folder()`.
"""

from pathlib import Path

from loguru import logger

from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.interfaces.environments.errors import EnvironmentFailure
from sculptor.interfaces.environments.errors import FileNotFoundEnvironmentError
from sculptor.utils.build import get_sculptor_folder

# Directory and filenames of the convention docs. Kept here as the single source
# of truth; the settings-toggle copy, help docs, and .gitignore reference the same
# names, so update those together if these change.
SCULPTOR_CONFIG_DIRNAME = ".sculptor"
NAMING_CONVENTIONS_FILENAME = "naming.md"
NAMING_CONVENTIONS_LOCAL_FILENAME = "naming.local.md"

# Per-tier character cap. Conventions are meant to be a few lines; this only
# guards against a stray large file bloating every first-message reminder.
_MAX_TIER_CHARS = 4000


def _clip(text: str) -> str:
    if len(text) <= _MAX_TIER_CHARS:
        return text
    return text[:_MAX_TIER_CHARS].rstrip() + "\n…(truncated)"


def _read_user_tier(sculptor_folder: Path) -> str | None:
    """Read the host-side user-global doc, or None if it is absent/unreadable."""
    path = sculptor_folder / NAMING_CONVENTIONS_FILENAME
    try:
        return path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except OSError as e:
        logger.warning("Could not read user naming conventions at {}: {}", path, e)
        return None


def _read_repo_tier(environment: AgentExecutionEnvironment, filename: str) -> str | None:
    """Read a repo-root convention doc through the environment, or None if absent.

    `.sculptor/<filename>` lives at the repo root, i.e. the environment's working
    directory. `read_file` resolves relative paths against the workspace root
    (which is a level above the working directory), so pass the absolute
    working-directory path to hit the repo checkout.
    """
    path = environment.get_working_directory() / SCULPTOR_CONFIG_DIRNAME / filename
    try:
        content = environment.read_file(str(path))
    except FileNotFoundEnvironmentError:
        return None
    except (EnvironmentFailure, OSError) as e:
        logger.warning("Could not read naming conventions at {}: {}", path, e)
        return None
    if isinstance(content, bytes):
        content = content.decode("utf-8", errors="replace")
    return content


def resolve_naming_conventions(
    environment: AgentExecutionEnvironment,
    sculptor_folder: Path | None = None,
) -> str | None:
    """Assemble the layered naming-convention block for the auto-rename reminder.

    Returns the formatted block — labeled sections, least-specific tier first — or
    None when no tier provides any non-empty content.
    """
    if sculptor_folder is None:
        sculptor_folder = get_sculptor_folder()

    # Ordered least-specific to most-specific; the reminder tells the agent a later
    # block overrides an earlier one, so appending Local last gives it the final say.
    raw_tiers: tuple[tuple[str, str | None], ...] = (
        (
            f"~/{SCULPTOR_CONFIG_DIRNAME}/{NAMING_CONVENTIONS_FILENAME} (your personal conventions, all repos)",
            _read_user_tier(sculptor_folder),
        ),
        (
            f"{SCULPTOR_CONFIG_DIRNAME}/{NAMING_CONVENTIONS_FILENAME} (this repo's shared conventions)",
            _read_repo_tier(environment, NAMING_CONVENTIONS_FILENAME),
        ),
        (
            f"{SCULPTOR_CONFIG_DIRNAME}/{NAMING_CONVENTIONS_LOCAL_FILENAME} (your local overrides for this repo)",
            _read_repo_tier(environment, NAMING_CONVENTIONS_LOCAL_FILENAME),
        ),
    )

    sections = [
        f"### {label}\n{_clip(content.strip())}" for label, content in raw_tiers if content and content.strip()
    ]
    if not sections:
        return None
    return "\n\n".join(sections)
