from pathlib import Path
from urllib.parse import parse_qs
from urllib.parse import urlparse

from sculptor.database.core import IN_MEMORY_SQLITE


def maybe_get_db_path(database_url: str) -> Path | None:
    if not database_url.startswith("sqlite:///") or database_url == IN_MEMORY_SQLITE or "mode=memory" in database_url:
        return None
    # this removes the "sqlite:///" prefix and (should) take off any options after the path
    url_parts = database_url[10:].split("?", 1)
    return Path(url_parts[0])


def is_read_only_sqlite_url(database_url: str) -> bool:
    """
    Check if the given database connection string is a read-only sqlite connection.

    E.g. sqlite:///file:myapp.db?mode=ro

    """
    if not database_url.startswith("sqlite:///"):
        return False
    parsed_url = urlparse(database_url)
    if not parsed_url.path.startswith("/file:"):
        return False
    query_params = parse_qs(parsed_url.query)
    return "mode" in query_params and query_params["mode"] == ["ro"]
