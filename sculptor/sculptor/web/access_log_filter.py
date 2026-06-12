import re

FREQUENTLY_POLLED_ROUTES: tuple[str | re.Pattern[str], ...] = (
    "/api/sync/global_singleton_state",
    "/api/v1/health",
    re.compile(r"/api/v1/projects/[^/]+/repo_info$"),
    re.compile(r"/api/v1/projects/[^/]+/current_branch$"),
    re.compile(r"/api/v1/projects/[^/]+/tasks/[^/]+/current_branch$"),
)


def _extract_path(message: str) -> str | None:
    """Extract the URL path from a uvicorn access log message.

    Example: '127.0.0.1:63270 - "GET /api/v1/health HTTP/1.1" 200' -> '/api/v1/health'
    """
    start = message.find(" /")
    if start == -1:
        return None
    start += 1  # skip the space
    end = message.find(" ", start)
    if end == -1:
        return None
    return message[start:end]


def _extract_status_code(message: str) -> int | None:
    """Extract the HTTP status code from a uvicorn access log message."""
    try:
        tail = message.rsplit('"', 1)[1]
    except IndexError:
        return None
    tokens = tail.strip().split()
    if not tokens:
        return None
    status_str = tokens[0]
    if not status_str.isdigit():
        return None
    return int(status_str)


def _matches_frequently_polled_route(path: str) -> bool:
    for route in FREQUENTLY_POLLED_ROUTES:
        if isinstance(route, re.Pattern):
            if route.fullmatch(path):
                return True
        elif route == path:
            return True
    return False


def should_suppress_access_log(message: str) -> bool:
    """Return True when we should drop a noisy access log entry."""
    path = _extract_path(message)
    if path is None:
        return False
    if not _matches_frequently_polled_route(path):
        return False
    status_code = _extract_status_code(message)
    if status_code is None:
        return False
    return status_code == 200
