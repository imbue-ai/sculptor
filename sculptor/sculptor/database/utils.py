from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse

from sculptor.database.core import IN_MEMORY_SQLITE

_SQLITE_URL_PREFIX = "sqlite:///"


def maybe_get_db_path(database_url: str) -> Path | None:
    """Return the on-disk path for a file-backed sqlite URL, or None for in-memory URLs."""
    if (
        not database_url.startswith(_SQLITE_URL_PREFIX)
        or database_url == IN_MEMORY_SQLITE
        or "mode=memory" in database_url
    ):
        return None
    path_without_prefix = database_url.removeprefix(_SQLITE_URL_PREFIX)
    path_without_options = path_without_prefix.split("?", 1)[0]
    return Path(path_without_options)


def is_read_only_sqlite_url(database_url: str) -> bool:
    """
    Check if the given database connection string is a read-only sqlite connection.

    E.g. sqlite:///file:myapp.db?mode=ro

    """
    if not database_url.startswith(_SQLITE_URL_PREFIX):
        return False
    parsed_url = urlparse(database_url)
    if not parsed_url.path.startswith("/file:"):
        return False
    query_params = parse_qs(parsed_url.query)
    return "mode" in query_params and query_params["mode"] == ["ro"]
