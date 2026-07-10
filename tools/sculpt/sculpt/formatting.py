"""Output formatting utilities for the sculpt CLI."""

import datetime
import json
import sys
from collections.abc import Sequence
from typing import NoReturn

import typer

from sculpt.commands.data_types import ErrorOutput

_ELLIPSIS = "..."

# ANSI escape sequences for in-place TTY updates.
_MOVE_CURSOR_UP = "\033[A"
_CLEAR_LINE = "\033[2K"


def format_table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    """Format data as an aligned table."""
    if not rows:
        return ""

    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            if i < len(col_widths):
                col_widths[i] = max(col_widths[i], len(cell))

    header_line = "  ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))

    row_lines = []
    for row in rows:
        row_line = "  ".join(cell.ljust(col_widths[i]) if i < len(col_widths) else cell for i, cell in enumerate(row))
        row_lines.append(row_line)

    return "\n".join([header_line] + row_lines)


def format_datetime(dt: datetime.datetime) -> str:
    """Format datetime for display (YYYY-MM-DD HH:MM)."""
    return dt.strftime("%Y-%m-%d %H:%M")


def truncate(text: str, max_length: int = 50) -> str:
    """Truncate text with ellipsis."""
    text = text.replace("\n", " ").strip()
    if len(text) <= max_length:
        return text
    return text[: max_length - len(_ELLIPSIS)] + _ELLIPSIS


def json_error(error: str, detail: str = "", code: str | None = None) -> str:
    """Return a JSON-formatted error string."""
    return ErrorOutput(error=error, detail=detail, code=code).model_dump_json()


def cli_error(
    message: str,
    *,
    detail: str = "",
    code: str | None = None,
    json_output: bool = False,
    exit_code: int = 1,
) -> NoReturn:
    """Print an error and exit with the given code (default 1).

    When json_output is True, writes structured JSON to stderr.
    Otherwise writes human-readable text to stderr.

    ``code`` carries a machine-readable error code (usually straight from the
    backend's structured error detail) so ``--json`` consumers can branch on it
    instead of pattern-matching prose. It appears in the JSON output only.

    The exit_code keyword lets specific commands surface category-distinct
    exit codes that an agent's tool harness can pattern-match on.
    """
    if json_output:
        typer.echo(json_error(message, detail, code), err=True)
    else:
        typer.echo(f"Error: {message}", err=True)
        if detail:
            typer.echo(detail, err=True)
    raise typer.Exit(code=exit_code)


def handle_connection_error(json_output: bool = False, *, exit_code: int = 1) -> NoReturn:
    """Handle a connection error to the Sculptor server."""
    cli_error("Could not connect to Sculptor server", json_output=json_output, exit_code=exit_code)


def is_tty() -> bool:
    """Check if stdout is a TTY."""
    return sys.stdout.isatty()


def overwrite_lines(text: str, previous_line_count: int) -> int:
    """Print text, overwriting previous output in-place on a TTY.

    Returns the number of lines in the new text (for the next call).
    """
    if previous_line_count > 0:
        for _ in range(previous_line_count):
            sys.stdout.write(_MOVE_CURSOR_UP + _CLEAR_LINE)
    sys.stdout.write(text + "\n")
    sys.stdout.flush()
    return text.count("\n") + 1
