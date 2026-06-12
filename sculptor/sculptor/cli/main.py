"""Pre-import bootstrap for the Sculptor backend.

The canonical ``python -m sculptor.cli.main`` and the ``sculptor``
console-script entry point.  Two responsibilities:

1. **Helper-mode dispatch.**  When invoked with ``--pty-helper`` as
   the first argument, this process is a pty-spawning helper
   subprocess (see ``services/.../environments/pty_helper.py``).
   We dispatch into the helper before any heavy backend import runs,
   so the helper interpreter stays small and starts fast.  In the
   PyInstaller bundle ``sys.executable`` is ``sculptor_backend``
   itself; re-entering the same binary with ``--pty-helper`` is the
   only way to launch the helper without shipping a second
   interpreter.

2. **Normal backend startup.**  When no helper flag is present, hand
   off to ``sculptor.cli.app:entrypoint`` which contains the full
   typer CLI and uvicorn startup.  The heavy imports (typer, uvicorn,
   loguru, sentry, posthog, ``sculptor.web.app``) deliberately live
   in that module, not here, so a helper invocation never pays for
   them.

Imports above ``main()`` MUST stay stdlib-only.  The property test
in ``main_test.py`` pins the discipline.
"""

import sys

_PTY_HELPER_FLAG = "--pty-helper"
_TRACE_TO_FLAG = "--trace-to"


def _parse_trace_to_arg() -> str | None:
    """Find a ``--trace-to=<path>`` or ``--trace-to <path>`` flag in argv,
    consume it from ``sys.argv``, and return the value.

    Hand-rolled rather than going through typer so viztracer can be started
    BEFORE the heavy ``cli/app`` import — this is what lets the trace include
    backend import durations and pre-server-startup work.

    Consuming the flag from ``sys.argv`` is load-bearing: typer's grammar is
    ``[OPTIONS] [PROJECT] COMMAND [ARGS]...``, so a ``--trace-to=...`` that
    appears AFTER the positional project path would be mis-parsed as an
    unknown subcommand and abort startup. Removing it here lets the flag
    appear anywhere on the command line.

    Raises ``SystemExit`` if the flag is present with no value (e.g. as the
    final argv entry) so the user gets an immediate error rather than a
    silent no-op.
    """
    for i, arg in enumerate(sys.argv[1:], start=1):
        if arg.startswith(_TRACE_TO_FLAG + "="):
            value = arg.split("=", 1)[1]
            if not value:
                sys.stderr.write(f"{_TRACE_TO_FLAG}= requires a non-empty path\n")
                raise SystemExit(2)
            del sys.argv[i]
            return value
        if arg == _TRACE_TO_FLAG:
            if i + 1 >= len(sys.argv):
                sys.stderr.write(f"{_TRACE_TO_FLAG} requires a path argument\n")
                raise SystemExit(2)
            value = sys.argv[i + 1]
            del sys.argv[i : i + 2]
            return value
    return None


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == _PTY_HELPER_FLAG:
        # Defer to the helper.  Both this import and the helper run with the
        # interpreter still single-threaded, which is the load-bearing
        # property: pty.fork() inside the helper cannot inherit a leaked
        # lock because no other thread exists in the helper interpreter.
        from sculptor.services.workspace_service.environment_manager.environments import pty_helper

        pty_helper.main()
        return

    trace_to = _parse_trace_to_arg()
    if trace_to is not None:
        from pathlib import Path

        from sculptor.utils.tracing import start_tracing

        start_tracing(Path(trace_to))

    # Normal backend startup: only now do we pay for the heavy imports.
    from sculptor.cli.app import entrypoint as cli_entrypoint
    from sculptor.utils.process_utils import get_original_parent_pid

    get_original_parent_pid()
    cli_entrypoint()


if __name__ == "__main__":
    main()
