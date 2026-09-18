"""Pure-function helpers for generating workspace branch names.

No git operations and no I/O. The caller is responsible for fetching
`git config user.name` and for choosing between a per-project override
and the user-global default pattern.
"""

from coolname import generate_slug
from slugify import slugify

_MAX_SLUG_LENGTH = 20
_RANDOM_SLUG_WORD_COUNT = 2

USER_PLACEHOLDER = "<user>"
SLUG_PLACEHOLDER = "<slug>"


def slugify_workspace_name(name: str) -> str:
    """Slugify a user-supplied workspace name into a kebab-case slug.

    Empty or pure-whitespace/punctuation input returns the empty string.
    Output is capped on a word boundary to avoid a trailing partial token.
    """
    if not name or not name.strip():
        return ""
    return slugify(name, max_length=_MAX_SLUG_LENGTH, word_boundary=True, separator="-", lowercase=True)


def generate_random_slug() -> str:
    """Return a random `<adjective>-<noun>` slug (UX-quality randomness)."""
    return generate_slug(_RANDOM_SLUG_WORD_COUNT)


def resolve_pattern(pattern: str, user_slug: str, name_slug: str) -> str:
    """Substitute `<user>` and `<slug>` placeholders in `pattern`.

    Unknown placeholders (e.g. `<foo>`) are left literal. Empty
    substitutions collapse: a leading `/` is stripped and consecutive
    `/` characters are reduced to one.
    """
    resolved = pattern.replace(USER_PLACEHOLDER, user_slug).replace(SLUG_PLACEHOLDER, name_slug)
    while "//" in resolved:
        resolved = resolved.replace("//", "/")
    if resolved.startswith("/"):
        resolved = resolved[1:]
    return resolved


def resolve_naming_pattern(project_pattern: str | None, default_pattern: str) -> str:
    """The pattern in force for a project: its own override when set and non-blank, else the user-global default."""
    if project_pattern is not None and project_pattern.strip():
        return project_pattern
    return default_pattern


def user_slug_from_full_name(full_name: str) -> str:
    """The `<user>` substitution: a slug of the first token of a git `user.name`, or empty when there is none."""
    tokens = full_name.split()
    if not tokens:
        return ""
    return slugify_workspace_name(tokens[0])
