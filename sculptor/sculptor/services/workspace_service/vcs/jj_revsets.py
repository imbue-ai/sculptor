"""Pure builders for the revsets, filesets and string patterns Sculptor passes to jj.

A name or path from a request or from jj's own output reaches jj only as a quoted
string literal inside one of these builders, so it is matched as text and never
evaluated as revset syntax.
"""

import re

from sculptor.services.workspace_service.vcs.errors import InvalidRevisionError
from sculptor.services.workspace_service.vcs.jj_data_types import JjBookmarkSymbol

_FULL_COMMIT_ID_PATTERN = re.compile(r"[0-9a-f]{40}")


class JjRevset(str):
    """A revset expression produced by this module's builders."""


class JjFileset(str):
    """A fileset expression produced by this module's builders."""


def quote_string_literal(value: str) -> str:
    """`value` as a jj string literal, usable in revsets, filesets and string patterns."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def exact_string_pattern(value: str) -> str:
    """A string pattern matching exactly `value`, for revset functions and for name arguments that take globs."""
    return f"exact:{quote_string_literal(value)}"


def local_bookmark_revset(name: str) -> JjRevset:
    return JjRevset(f"bookmarks({exact_string_pattern(name)})")


def remote_bookmark_revset(name: str, remote: str) -> JjRevset:
    return JjRevset(f"remote_bookmarks({exact_string_pattern(name)}, {exact_string_pattern(remote)})")


def any_remote_bookmark_revset(name: str) -> JjRevset:
    """The bookmark `name` on every remote, including jj's synthetic `git` remote in a colocated repository."""
    return JjRevset(f"remote_bookmarks({exact_string_pattern(name)})")


def working_copy_revset(workspace_name: str) -> JjRevset:
    """The working-copy commit of the workspace `workspace_name`, resolvable from any workspace of the repository."""
    return JjRevset(f"{quote_string_literal(workspace_name)}@")


def root_file_fileset(path: str) -> JjFileset:
    """The file at `path` relative to the workspace root, whatever the command's working directory."""
    return JjFileset(f"root-file:{quote_string_literal(path)}")


def parse_bookmark_symbol(symbol: str) -> JjBookmarkSymbol:
    """Read `name` as a local bookmark and `name@remote` as a remote one; raises `InvalidRevisionError` otherwise."""
    name, separator, remote = symbol.partition("@")
    if not name or "@" in remote or (separator and not remote):
        raise InvalidRevisionError(f"Not a jj bookmark symbol: {symbol!r}")
    return JjBookmarkSymbol(name=name, remote=remote if separator else None)


def bookmark_name_of_symbol(symbol: str | None) -> str | None:
    """The bookmark name in a symbol, such as `main` for `main@origin`; None for no symbol or a malformed one."""
    if symbol is None:
        return None
    try:
        return parse_bookmark_symbol(symbol).name
    except InvalidRevisionError:
        return None


def format_bookmark_symbol(symbol: JjBookmarkSymbol) -> str:
    """The symbol in jj's own syntax; a remote bookmark is `name@remote`, never git's `remote/name`."""
    if symbol.remote is None:
        return symbol.name
    return f"{symbol.name}@{symbol.remote}"


def is_full_commit_id(value: str) -> bool:
    """Whether `value` is a full commit id, the only form of commit id jj never reads as a symbol."""
    return _FULL_COMMIT_ID_PATTERN.fullmatch(value) is not None


def revset_for_base(symbol_or_commit_id: str) -> JjRevset:
    """The revset for a workspace base given as a bookmark symbol or a full commit id.

    Raises `InvalidRevisionError` for anything else.
    """
    if is_full_commit_id(symbol_or_commit_id):
        return JjRevset(symbol_or_commit_id)
    symbol = parse_bookmark_symbol(symbol_or_commit_id)
    if symbol.remote is None:
        return local_bookmark_revset(symbol.name)
    return remote_bookmark_revset(symbol.name, symbol.remote)
