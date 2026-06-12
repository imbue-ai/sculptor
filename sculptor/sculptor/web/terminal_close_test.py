"""Integration test for DELETE /api/v1/workspaces/{id}/terminal/{index}.

Goes through the real HTTP route (FastAPI TestClient) and a real
LocalTerminalManager managing a real pty + shell. Asserts:

- the route returns 204
- the registry no longer contains the terminal
- the shell pid actually dies

The shell-pid capture is intentionally agnostic about the underlying
pty implementation -- it reads ``_helper.shell_pid``
(posix_spawn-backed SpawnedPtyProcess) or ``_handle.shell_pid``
(forkserver-backed SpawnedPtyProcess from !1138), whichever exists --
so this test survives the pty implementation swap regardless of which
approach lands.
"""

import os
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.database.models import Project
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    LocalTerminalManager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    get_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    make_terminal_id,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_terminal_manager,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    unregister_terminal_manager,
)
from sculptor.web.auth import authenticate_anonymous

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="POSIX-only")


def _shell_pid(manager: LocalTerminalManager) -> int:
    """Read the shell pid in a way that works across all current pty backends:
    ``_helper.shell_pid`` (posix_spawn helper), ``_handle.shell_pid``
    (forkserver helper from !1138), or ``_pid`` (legacy direct fork)."""
    pty_process = manager._pty_process
    assert pty_process is not None
    for attr in ("_helper", "_handle"):
        ref = getattr(pty_process, attr, None)
        if ref is not None:
            return int(ref.shell_pid)
    pid = getattr(pty_process, "_pid", None)
    assert pid is not None
    return int(pid)


def _wait_for_dead(pid: int, timeout: float = 1.0) -> bool:
    """Return True once ``os.kill(pid, 0)`` raises ProcessLookupError.

    ``manager.stop()`` is synchronous upstream of this check (the DELETE
    route waits for terminate() before returning 204), so in the common
    case the pid is already gone and the first probe succeeds in
    microseconds. The polling tail covers the brief kernel-reap window
    -- 5ms ticks are far below normal scheduler granularity.
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return True
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        time.sleep(0.005)
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
    return False


def test_delete_terminal_kills_shell_and_unregisters(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    tmp_path: Path,
) -> None:
    """Closing a terminal via the HTTP route stops the shell + frees the registry."""
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="terminal-close-test",
            transaction=transaction,
        )
        # The route looks up workspace.environment_id; assign one explicitly
        # so we don't depend on background environment provisioning.
        environment_id = "test-env-for-terminal-close"
        transaction.update_workspace_fields(workspace.object_id, environment_id=environment_id)

    terminal_id = make_terminal_id(environment_id, 0)
    with ConcurrencyGroup(name="terminal-close-test") as group:
        manager = LocalTerminalManager(
            environment_id=environment_id,
            terminal_index=0,
            workspace_path=tmp_path,
            working_directory=tmp_path,
            concurrency_group=group,
        )
        manager.start()
        register_terminal_manager(terminal_id, manager)
        try:
            shell_pid = _shell_pid(manager)
            # Shell is alive right now.
            os.kill(shell_pid, 0)
            assert get_terminal_manager(terminal_id) is manager

            response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/terminal/0")
            assert response.status_code == 204

            # Registry no longer holds the terminal.
            assert get_terminal_manager(terminal_id) is None
            # Shell pid is gone within a deadline.
            assert _wait_for_dead(shell_pid), f"shell pid {shell_pid} still alive after DELETE"
        finally:
            try:
                manager.stop()
            except BaseException:
                pass
            unregister_terminal_manager(terminal_id)


def test_delete_terminal_404_when_workspace_missing(client: TestClient) -> None:
    response = client.delete("/api/v1/workspaces/ws_00000000000000000000000000/terminal/0")
    assert response.status_code in (404, 422)


def test_delete_terminal_404_when_terminal_not_started(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
) -> None:
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        workspace = test_services.workspace_service.create_workspace(
            project=test_project,
            initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
            source_branch=None,
            requested_branch_name=None,
            description="terminal-close-404-test",
            transaction=transaction,
        )
        transaction.update_workspace_fields(workspace.object_id, environment_id="env-no-terminal")
    response = client.delete(f"/api/v1/workspaces/{workspace.object_id}/terminal/99")
    assert response.status_code == 404
