"""Utilities for stubbing external CLI dependencies in integration tests.

All stubbing uses PATH shadowing: we write bash scripts into a temporary
directory and prepend it to PATH so the stubs are found before real binaries.
"""

import os
import shutil
import sys
from enum import StrEnum
from pathlib import Path

import pytest

from sculptor.services.dependency_management_service import CLAUDE_VERSION_RANGE
from sculptor.services.dependency_management_service import PI_VERSION_RANGE

# Session-level opt-out for the default claude stub install. When set, all
# call sites of ``install_default_claude_stub`` skip the stub write and
# resolve the real ``claude`` binary via PATH instead. Used by the
# ``real_claude`` test suite, which needs the actual Claude CLI rather than
# a stub. Module-level state is fine here because it is set once per pytest
# session by a conftest fixture and never reset.
_default_claude_stub_disabled_for_session: bool = False

# Session-level opt-out for the default pi stub install. Mirrors the claude
# variant — set by the real_pi conftest so tests resolve the real ``pi``
# binary on PATH instead of the stub.
_default_pi_stub_disabled_for_session: bool = False


def disable_default_claude_stub_for_session() -> None:
    """Skip default claude stub installs for the rest of this pytest session.

    After this is called, ``install_default_claude_stub`` does not write a
    stub binary and returns the absolute path to the real ``claude`` on
    PATH instead. The shared instance fixture pins this path into
    ``DependencyPaths.claude``, so the agent invokes the real CLI.

    Intended for ``real_claude`` tests; do not call from regular integration
    tests, which rely on the stub for hermetic version/auth behavior.
    """
    global _default_claude_stub_disabled_for_session
    _default_claude_stub_disabled_for_session = True


def _resolve_real_claude_for_real_claude_tests() -> Path:
    """Return the absolute path to the real ``claude`` binary on PATH.

    Raises if ``claude`` is not found — real_claude tests cannot run
    without the actual CLI installed.
    """
    found = shutil.which("claude")
    if found is None:
        raise RuntimeError(
            "real_claude tests require the real `claude` CLI on PATH but none was found. "
            + "Install it with `npm install -g @anthropic-ai/claude-code`."
        )
    return Path(found).resolve()


def disable_default_pi_stub_for_session() -> None:
    """Skip default pi stub installs for the rest of this pytest session.

    After this is called, ``install_default_pi_stub`` does not write a
    stub binary and returns the absolute path to the pinned ``pi`` in the
    workspace venv instead. Intended for ``real_pi`` tests; do not call from
    regular integration tests.
    """
    global _default_pi_stub_disabled_for_session
    _default_pi_stub_disabled_for_session = True


def _resolve_real_pi_for_real_pi_tests() -> Path:
    """Return the path to the pinned ``pi`` binary in the workspace venv.

    Resolves ``<sys.prefix>/bin/pi`` (planted by ``just install-pi``) rather
    than searching PATH, so an unrelated ``pi`` on PATH cannot shadow the
    version-pinned build the real_pi suite requires.
    """
    venv_pi = Path(sys.prefix) / "bin" / "pi"
    if not venv_pi.exists():
        raise RuntimeError(
            f"real_pi tests require the pinned `pi` binary at {venv_pi} but it was not found. "
            + "Install it with `just install-pi`."
        )
    return venv_pi.resolve()


class DependencyState(StrEnum):
    """Possible states for a dependency in tests."""

    # binary not found (exit 127)
    NOT_INSTALLED = "NOT_INSTALLED"
    # binary found but not working (exit 1)
    NOT_RUNNING = "NOT_RUNNING"
    # binary reports valid version but errors on real usage
    INSTALLED_STUB = "INSTALLED_STUB"
    # binary found, version OK, but auth check fails
    INSTALLED_NOT_AUTHENTICATED = "INSTALLED_NOT_AUTHENTICATED"
    # binary found, version OK, auth check fails, and `auth login` does NOT
    # self-complete: it prints a sign-in URL and blocks waiting for a pasted
    # code on stdin (the headless/remote fallback exercised by SCU-1502).
    INSTALLED_NEEDS_PASTE_CODE = "INSTALLED_NEEDS_PASTE_CODE"


# Stub script content for disabled dependencies.
# These scripts shadow the real binaries and fail with a clear error message.

# Exit code 127 simulates "command not found" (not installed).
GIT_NOT_INSTALLED_STUB = """#!/bin/bash
echo "git: command not found" >&2
exit 127
"""

CLAUDE_NOT_INSTALLED_STUB = """#!/bin/bash
echo "claude: command not found" >&2
exit 127
"""

CLAUDE_INSTALLED_STUB_VERSION = CLAUDE_VERSION_RANGE.recommended_version
CLAUDE_INSTALLED_STUB = f"""#!/bin/bash
case "$1" in
    --version|-v)
        echo "claude {CLAUDE_INSTALLED_STUB_VERSION}"
        exit 0
        ;;
    auth)
        case "$2" in
            status)
                echo "Authenticated as stub@example.com"
                exit 0
                ;;
            *)
                exit 1
                ;;
        esac
        ;;
    *)
        echo '{{"type":"error","error":{{"type":"stub_error","message":"Claude stub: not a real installation"}}}}' >&2
        exit 1
        ;;
esac
"""

CLAUDE_INSTALLED_NOT_AUTHENTICATED_STUB = f"""#!/bin/bash
# State file to track authentication across invocations
AUTH_STATE_FILE="/tmp/claude_stub_auth_$$_state"
# Use a shared state dir based on the stub's directory
AUTH_STATE_DIR="$(dirname "$0")"
AUTH_STATE_FILE="${{AUTH_STATE_DIR}}/.claude_auth_state"

case "$1" in
    --version|-v)
        echo "claude {CLAUDE_INSTALLED_STUB_VERSION}"
        exit 0
        ;;
    auth)
        case "$2" in
            status)
                if [ -f "$AUTH_STATE_FILE" ]; then
                    echo "Authenticated as stub@example.com"
                    exit 0
                fi
                echo "Not authenticated" >&2
                exit 1
                ;;
            login)
                echo "Opening browser to sign in…" >&2
                echo "If the browser didn't open, visit: https://example.com/fake-auth" >&2
                touch "$AUTH_STATE_FILE"
                echo "Login successful."
                exit 0
                ;;
            *)
                exit 1
                ;;
        esac
        ;;
    *)
        echo '{{"type":"error","error":{{"type":"stub_error","message":"Claude stub: not a real installation"}}}}' >&2
        exit 1
        ;;
esac
"""

# The sign-in URL the paste-a-code stub prints; the onboarding UI surfaces it as
# a link for the user to open.
CLAUDE_PASTE_CODE_AUTH_URL = "https://example.com/headless-sign-in"
# The only code the paste-a-code stub accepts. Tests paste this to complete
# sign-in; anything else makes the stub exit non-zero.
CLAUDE_PASTE_CODE_VALID = "valid-paste-code"

# Mimics `claude auth login` in a headless/remote environment: the localhost
# browser-loopback flow can't reach the user, so the CLI prints a sign-in URL and
# then blocks reading a code from stdin. Sign-in succeeds only when the pasted
# code matches CLAUDE_PASTE_CODE_VALID; success is persisted to a state file so a
# subsequent `auth status` reports authenticated (mirroring the real CLI).
CLAUDE_INSTALLED_NEEDS_PASTE_CODE_STUB = f"""#!/bin/bash
AUTH_STATE_DIR="$(dirname "$0")"
AUTH_STATE_FILE="${{AUTH_STATE_DIR}}/.claude_auth_state"

case "$1" in
    --version|-v)
        echo "claude {CLAUDE_INSTALLED_STUB_VERSION}"
        exit 0
        ;;
    auth)
        case "$2" in
            status)
                if [ -f "$AUTH_STATE_FILE" ]; then
                    echo "Authenticated as stub@example.com"
                    exit 0
                fi
                echo "Not authenticated" >&2
                exit 1
                ;;
            login)
                # Print the URL, then block on stdin waiting for the pasted code.
                echo "Open this URL to sign in: {CLAUDE_PASTE_CODE_AUTH_URL}" >&2
                read code
                if [ "$code" = "{CLAUDE_PASTE_CODE_VALID}" ]; then
                    touch "$AUTH_STATE_FILE"
                    echo "Login successful."
                    exit 0
                fi
                echo "invalid code" >&2
                exit 1
                ;;
            *)
                exit 1
                ;;
        esac
        ;;
    *)
        echo '{{"type":"error","error":{{"type":"stub_error","message":"Claude stub: not a real installation"}}}}' >&2
        exit 1
        ;;
esac
"""

PI_NOT_INSTALLED_STUB = """#!/bin/bash
echo "pi: command not found" >&2
exit 127
"""

PI_INSTALLED_STUB_VERSION = PI_VERSION_RANGE.recommended_version
# WHY: real pi emits --version to stderr, not stdout; the stub mirrors that.
PI_INSTALLED_STUB = f"""#!/bin/bash
case "$1" in
    --version|-v)
        echo "pi {PI_INSTALLED_STUB_VERSION}" >&2
        exit 0
        ;;
    *)
        echo '{{"type":"error","error":{{"type":"stub_error","message":"Pi stub: not a real installation"}}}}' >&2
        exit 1
        ;;
esac
"""

DEPENDENCY_STUB_SCRIPTS: dict[tuple[str, DependencyState], str] = {
    ("git", DependencyState.NOT_INSTALLED): GIT_NOT_INSTALLED_STUB,
    ("claude", DependencyState.NOT_INSTALLED): CLAUDE_NOT_INSTALLED_STUB,
    ("claude", DependencyState.INSTALLED_STUB): CLAUDE_INSTALLED_STUB,
    ("claude", DependencyState.INSTALLED_NOT_AUTHENTICATED): CLAUDE_INSTALLED_NOT_AUTHENTICATED_STUB,
    ("claude", DependencyState.INSTALLED_NEEDS_PASTE_CODE): CLAUDE_INSTALLED_NEEDS_PASTE_CODE_STUB,
    ("pi", DependencyState.NOT_INSTALLED): PI_NOT_INSTALLED_STUB,
    ("pi", DependencyState.INSTALLED_STUB): PI_INSTALLED_STUB,
}

# Pytest marker for stubbing dependencies in tests.
# Usage: @stub_dependency("git") or @stub_dependency("claude", state=DependencyState.INSTALLED_STUB)
stub_dependency = pytest.mark.stub_dependency

# The default claude stub state installed for every integration test that
# doesn't override it via @stub_dependency.  Tests see a valid-version claude
# binary so the dependency check passes, but any real invocation fails loudly.
DEFAULT_CLAUDE_STUB_STATE: DependencyState = DependencyState.INSTALLED_STUB


def install_default_claude_stub(fake_bin_dir: Path) -> Path:
    """Install the default claude stub into ``fake_bin_dir``.

    Returns the absolute path to the stub script so callers can wire it into
    the user config via ``DependencyPaths(claude=...)`` — using an absolute
    path avoids PATH-ordering races when PTY-spawned subprocesses mutate PATH.

    When ``disable_default_claude_stub_for_session`` has been called (real_claude
    suite), the stub write is skipped and the absolute path to the real
    ``claude`` on PATH is returned instead. Callers do not need to know which
    mode they are in; they just pin whatever path comes back into the user
    config.
    """
    if _default_claude_stub_disabled_for_session:
        return _resolve_real_claude_for_real_claude_tests()
    create_disabled_dependency_stub(fake_bin_dir, "claude", DEFAULT_CLAUDE_STUB_STATE)
    return fake_bin_dir / "claude"


DEFAULT_PI_STUB_STATE: DependencyState = DependencyState.INSTALLED_STUB


def install_default_pi_stub(fake_bin_dir: Path) -> Path:
    """Install the default pi stub into ``fake_bin_dir``.

    Returns the absolute path to the stub script so callers can wire it
    into the user config via ``DependencyPaths(pi=...)``. When
    ``disable_default_pi_stub_for_session`` has been called (real_pi
    suite), the stub write is skipped and the absolute path to the pinned
    ``pi`` in the workspace venv is returned instead.
    """
    if _default_pi_stub_disabled_for_session:
        return _resolve_real_pi_for_real_pi_tests()
    create_disabled_dependency_stub(fake_bin_dir, "pi", DEFAULT_PI_STUB_STATE)
    return fake_bin_dir / "pi"


def iter_stub_dependency_markers(request: pytest.FixtureRequest) -> list[tuple[str, DependencyState]]:
    """Return ``(dep_name, state)`` pairs from all ``@stub_dependency`` markers on ``request``."""
    result: list[tuple[str, DependencyState]] = []
    for marker in request.node.iter_markers(stub_dependency.name):
        if not marker.args:
            continue
        dep_name = marker.args[0].lower()
        state = DependencyState(marker.kwargs.get("state", DependencyState.NOT_RUNNING))
        result.append((dep_name, state))
    return result


def has_stub_dependency_marker_for(request: pytest.FixtureRequest, dep_name: str) -> bool:
    """True iff the test node carries a ``@stub_dependency`` marker for ``dep_name``."""
    return any(name == dep_name.lower() for name, _ in iter_stub_dependency_markers(request))


def assert_no_stub_dependency_markers(request: pytest.FixtureRequest) -> None:
    """Fail fast if the test node has any ``@stub_dependency`` markers.

    Used by the shared-instance fixture: it doesn't honour these markers (the
    backend process is already running with a baked-in stub), so accepting a
    test with one would silently ignore the override.
    """
    markers = iter_stub_dependency_markers(request)
    if markers:
        names = sorted({name for name, _ in markers})
        pytest.fail(
            f"@stub_dependency is not supported with the shared sculptor_instance_ fixture (markers found: {names}). Use sculptor_instance_factory_ instead."
        )


def create_cli_stub(stub_dir: Path, name: str, script: str) -> Path:
    """Write *script* as an executable file named *name* inside *stub_dir*.

    Returns the path to the created stub.  Callers should prepend *stub_dir*
    to ``PATH`` so the stub shadows any real binary of the same name.

    Available for tests that need custom CLI fakes (e.g. gh/glab with
    mode-file switching in ``test_pr_button_errors.py``).
    """
    stub_path = stub_dir / name
    stub_path.write_text(script)
    stub_path.chmod(0o755)
    return stub_path


def create_disabled_dependency_stub(
    stub_dir: Path, binary_name: str, state: DependencyState = DependencyState.NOT_RUNNING
) -> None:
    """Create a stub script that shadows a binary and fails when called.

    Places a failing stub script in *stub_dir* so it shadows the real binary
    when *stub_dir* is prepended to PATH.
    """
    stub_path = stub_dir / binary_name
    script_content = DEPENDENCY_STUB_SCRIPTS[(binary_name, state)]
    stub_path.write_text(script_content)
    stub_path.chmod(0o755)


def create_claude_stub_dir(parent_dir: Path) -> Path:
    """Create a directory containing a stub ``claude`` binary that reports a valid version.

    Returns the directory path so it can be prepended to PATH.
    """
    stub_dir = parent_dir / "claude_stub"
    stub_dir.mkdir(exist_ok=True)
    create_disabled_dependency_stub(stub_dir, "claude", DependencyState.INSTALLED_STUB)
    return stub_dir


def create_claude_version_stub_dir(parent_dir: Path, version: str) -> Path:
    """Create a directory containing a stub ``claude`` binary that reports a specific version.

    Returns the directory path so it can be prepended to PATH.
    """
    stub_dir = parent_dir / "claude_version_stub"
    stub_dir.mkdir(exist_ok=True)
    script = f"""#!/bin/bash
case "$1" in
    --version|-v)
        echo "claude {version}"
        exit 0
        ;;
    *)
        echo '{{"type":"error","error":{{"type":"stub_error","message":"Claude stub: not a real installation"}}}}' >&2
        exit 1
        ;;
esac
"""
    create_cli_stub(stub_dir, "claude", script)
    return stub_dir


def apply_stubs_from_request(
    request: pytest.FixtureRequest,
    environment: dict[str, str | None],
    tmp_path: Path,
) -> None:
    """Apply per-test stub overrides from ``@stub_dependency`` markers.

    Called from ``sculptor_instance_factory_`` to disable dependencies for
    specific tests. Creates stub scripts and prepends them to PATH.
    """
    stubs: dict[str, DependencyState] = dict(iter_stub_dependency_markers(request))

    if not stubs:
        return

    stub_dir = tmp_path / "disabled_dependency_stubs"
    stub_dir.mkdir(exist_ok=True)

    for dep_name, state in stubs.items():
        create_disabled_dependency_stub(stub_dir, dep_name, state)

    original_path = environment.get("PATH") or os.environ.get("PATH", "")
    environment["PATH"] = f"{stub_dir}{os.pathsep}{original_path}"
