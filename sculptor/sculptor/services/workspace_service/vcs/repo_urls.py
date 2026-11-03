"""Pure parsing of repository and remote URLs."""

import urllib.parse
from pathlib import Path

_FILE_URL_PREFIX = "file://"


def _is_scp_style(url: str) -> bool:
    """Whether `url` is the `user@host:path` form git accepts for SSH remotes."""
    return ":" in url and not url.startswith(("https://", "http://", "ssh://"))


def extract_remote_hostname(url: str) -> str:
    """The host a remote URL points at, or "" when it has none (e.g. a local path)."""
    if _is_scp_style(url):
        return url.split("@", 1)[-1].split(":")[0]
    return urllib.parse.urlparse(url).hostname or ""


def is_github_remote_url(url: str) -> bool:
    """Whether the remote is hosted on GitHub, including GitHub Enterprise hosts."""
    return "github" in extract_remote_hostname(url).lower()


def parse_remote_owner_and_name(url: str) -> tuple[str, str] | None:
    """`(owner, name)` from a remote URL whose path is exactly `owner/name[.git]`."""
    if _is_scp_style(url):
        path = url.split(":", 1)[1]
    else:
        path = urllib.parse.urlparse(url).path
    parts = path.strip("/").split("/")
    if len(parts) != 2:
        return None
    owner, name = parts
    name = name.removesuffix(".git")
    if not owner or not name:
        return None
    return owner, name


def file_url_to_path(url: str | None) -> Path | None:
    """The local path a `file://` URL names, or None for any other URL."""
    if url is None or not url.startswith(_FILE_URL_PREFIX):
        return None
    return Path(url.removeprefix(_FILE_URL_PREFIX))
