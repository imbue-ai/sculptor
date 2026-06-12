"""Tests for `BtwService` and end-to-end `/btw` subprocess behavior.

Covers two load-bearing guarantees:

1. A `/btw` turn must NOT mutate main's Claude session
   JSONL. Exercised against a real FakeClaude subprocess so the
   ``--fork-session --no-session-persistence`` flag combo is evaluated
   end-to-end. Architecture R1 flags this as the single most important
   regression gate.

2. **Architecture §4.4.3** — at most one in-flight `/btw` per agent: when a
   second request arrives, the first subprocess is aborted via SIGTERM and
   its terminal update is `state="aborted"`.
"""

import hashlib
import shutil
import threading
import time
from pathlib import Path
from queue import Empty
from queue import Queue
from typing import Generator
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from imbue_core.agents.data_types.ids import ProjectID
from imbue_core.agents.data_types.ids import TaskID
from imbue_core.concurrency_group import ConcurrencyGroup
from sculptor.agents.default.claude_code_sdk.btw_process_manager import BtwProcessManager
from sculptor.agents.default.claude_code_sdk.btw_process_manager import NoBtwSessionAvailable
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import WorkspaceID
from sculptor.services.btw_service.api import BtwService
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LOCAL_WORKSPACE_DIR
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.web.data_types import BtwUpdate
from sculptor.web.data_types import StreamingUpdateSourceTypes


@pytest.fixture
def local_environment(
    test_root_concurrency_group: ConcurrencyGroup,
) -> Generator[AgentExecutionEnvironment, None, None]:
    workspace_dir = LOCAL_WORKSPACE_DIR / str(uuid4().hex)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    repo_dir = workspace_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    try:
        local_env = LocalEnvironment.create(
            environment_id=LocalEnvironmentID(str(workspace_dir)),
            project_id=ProjectID(),
            concurrency_group=test_root_concurrency_group,
            repo_host_path=repo_dir,
        )
        mock_cg = MagicMock(spec=ConcurrencyGroup)
        dep_service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
        yield LocalAgentExecutionEnvironment(local_env, TaskID(), dep_service)
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def _write_main_session(environment: AgentExecutionEnvironment, session_id: str, jsonl_contents: str) -> Path:
    """Pre-populate a main-agent session: state file + claude JSONL."""
    state_dir = environment.get_state_path()
    environment.write_file(str(state_dir / "session_id"), session_id)

    jsonl_dir = CLAUDE_CODE_HARNESS.get_jsonl_path_for_working_directory(
        Path.home(), environment.get_working_directory()
    )
    assert jsonl_dir is not None
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = jsonl_dir / f"{session_id}.jsonl"
    jsonl_path.write_text(jsonl_contents)
    return jsonl_path


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_btw_does_not_mutate_main_session_jsonl(
    local_environment: AgentExecutionEnvironment,
) -> None:
    """A /btw run leaves main's session JSONL byte-identical
    and writes no new file in the claude jsonl directory."""
    session_id = "session_btw_isolation_test"
    jsonl_contents = '{"type": "user", "sessionId": "session_btw_isolation_test", "message": {"role": "user", "content": "main pre-existing content"}}\n'
    jsonl_path = _write_main_session(local_environment, session_id, jsonl_contents)

    jsonl_dir = jsonl_path.parent
    files_before = sorted(p.name for p in jsonl_dir.iterdir())
    hash_before = _hash(jsonl_path)

    updates: list[BtwUpdate] = []
    manager = BtwProcessManager(
        environment=local_environment,
        task_id=TaskID(),
        workspace_id=WorkspaceID(),
        publish=updates.append,
        harness=CLAUDE_CODE_HARNESS,
        is_fake_claude=True,
    )
    manager.run_btw(question='fake_claude:text `{"text": "isolated answer"}`', request_id="iso-1")

    hash_after = _hash(jsonl_path)
    files_after = sorted(p.name for p in jsonl_dir.iterdir())

    assert updates, "expected at least one BtwUpdate to be published"
    assert updates[-1].state == "done", (
        f"expected terminal state='done', got {updates[-1].state!r} (error={updates[-1].error_message!r})"
    )
    assert hash_before == hash_after, (
        "/btw mutated main's session JSONL. Verify --fork-session and --no-session-persistence are still emitted."
    )
    assert files_before == files_after, (
        f"/btw left new files in the claude jsonl directory: before={files_before}, after={files_after}. Check --no-session-persistence and the FakeClaude session-write path."
    )


def _drain_terminal_updates(
    queue: Queue[StreamingUpdateSourceTypes], request_ids: set[str], timeout: float
) -> dict[str, BtwUpdate]:
    """Pull from `queue` until each request_id has a terminal-state update or `timeout` elapses."""
    terminals: dict[str, BtwUpdate] = {}
    deadline = time.monotonic() + timeout
    while terminals.keys() != request_ids and time.monotonic() < deadline:
        try:
            update = queue.get(timeout=0.2)
        except Empty:
            continue
        if not isinstance(update, BtwUpdate):
            continue
        if update.request_id in request_ids and update.state in ("done", "error", "aborted"):
            terminals[update.request_id] = update
    return terminals


def test_run_btw_for_task_waits_for_late_session_write(
    local_environment: AgentExecutionEnvironment,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Cold-start race: `/btw` arriving before main's first `system/init`
    should wait briefly for the session file rather than 409'ing.

    Pre-populates the claude JSONL (so the forked subprocess can succeed)
    but holds back the session-id state file until 200ms after the call
    starts — mirroring the real flow where the main agent emits init
    shortly after the user fires /btw.
    """
    session_id = "session_btw_late_write_test"
    jsonl_contents = (
        '{"type": "user", "sessionId": "session_btw_late_write_test", '
        '"message": {"role": "user", "content": "main pre-existing content"}}\n'
    )
    jsonl_dir = CLAUDE_CODE_HARNESS.get_jsonl_path_for_working_directory(
        Path.home(), local_environment.get_working_directory()
    )
    assert jsonl_dir is not None
    jsonl_dir.mkdir(parents=True, exist_ok=True)
    (jsonl_dir / f"{session_id}.jsonl").write_text(jsonl_contents)

    state_dir = local_environment.get_state_path()

    def write_session_id_after_delay() -> None:
        time.sleep(0.2)
        local_environment.write_file(str(state_dir / "session_id"), session_id)

    btw_service = BtwService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("btw_service_late_write_test")
    )

    writer = threading.Thread(target=write_session_id_after_delay)
    with btw_service.run():
        writer.start()
        try:
            # Without the cold-start wait, this raises NoBtwSessionAvailable
            # immediately because the session-id file isn't on disk yet.
            btw_service.run_btw_for_task(
                environment=local_environment,
                task_id=TaskID(),
                workspace_id=WorkspaceID(),
                question='fake_claude:text `{"text": "late-write answer"}`',
                request_id="late-write-1",
                is_fake_claude=True,
            )
        finally:
            writer.join()


def test_run_btw_for_task_fails_fast_when_main_agent_not_started(
    local_environment: AgentExecutionEnvironment,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """First-message-is-/btw: if the user has never started the main agent,
    no session id is coming. Skip the cold-start wait and fail immediately
    so the frontend's "/btw is unavailable until you've sent a message"
    toast appears without a 10s delay."""
    btw_service = BtwService(
        concurrency_group=test_root_concurrency_group.make_concurrency_group("btw_service_fast_fail_test")
    )

    with btw_service.run():
        start = time.monotonic()
        with pytest.raises(NoBtwSessionAvailable):
            btw_service.run_btw_for_task(
                environment=local_environment,
                task_id=TaskID(),
                workspace_id=WorkspaceID(),
                question="anything",
                request_id="fast-fail-1",
                is_fake_claude=True,
                main_agent_started=False,
            )
        elapsed = time.monotonic() - start

    assert elapsed < 1.0, f"fast-fail took {elapsed:.2f}s — should not have waited for the cold-start cushion"


def test_second_btw_aborts_first_in_flight(
    local_environment: AgentExecutionEnvironment,
    test_root_concurrency_group: ConcurrencyGroup,
) -> None:
    """Architecture §4.4.3: a second /btw on the same agent must SIGTERM the first.

    Without this guarantee the first subprocess keeps burning Haiku tokens
    even after the popup has moved on. We fire two /btw calls back to back
    against a fake-claude subprocess that sleeps for ten seconds; the
    first must be aborted (terminal state="aborted") well before its
    sleep would complete naturally.
    """
    session_id = "session_btw_abort_on_replace_test"
    jsonl_contents = '{"type": "user", "sessionId": "session_btw_abort_on_replace_test", "message": {"role": "user", "content": "main pre-existing content"}}\n'
    _write_main_session(local_environment, session_id, jsonl_contents)

    task_id = TaskID()
    workspace_id = WorkspaceID()
    btw_service = BtwService(concurrency_group=test_root_concurrency_group.make_concurrency_group("btw_service_test"))

    # Subscribe an observer queue so we can read the BtwUpdate stream the
    # service emits for both turns.
    observer_queue: Queue[StreamingUpdateSourceTypes] = Queue()
    btw_service.add_observer_queue(observer_queue)

    with btw_service.run():
        try:
            # First /btw — long sleep that would otherwise block for 10s.
            btw_service.run_btw_for_task(
                environment=local_environment,
                task_id=task_id,
                workspace_id=workspace_id,
                question='fake_claude:sleep `{"seconds": 10}`',
                request_id="req-A",
                is_fake_claude=True,
            )
            # Give the subprocess a moment to start before firing the replacement.
            time.sleep(0.5)

            # Second /btw — short sleep so it completes promptly after the first
            # is aborted.
            start = time.monotonic()
            btw_service.run_btw_for_task(
                environment=local_environment,
                task_id=task_id,
                workspace_id=workspace_id,
                question='fake_claude:sleep `{"seconds": 1}`',
                request_id="req-B",
                is_fake_claude=True,
            )

            terminals = _drain_terminal_updates(observer_queue, {"req-A", "req-B"}, timeout=8.0)
            elapsed = time.monotonic() - start
        finally:
            btw_service.remove_observer_queue(observer_queue)

    assert "req-A" in terminals, (
        f"first /btw never produced a terminal update — got terminals for {sorted(terminals)}."
        + " Check that BtwService aborts the in-flight subprocess when a second /btw arrives."
    )
    assert "req-B" in terminals, (
        f"second /btw never produced a terminal update — got terminals for {sorted(terminals)}."
    )
    assert terminals["req-A"].state == "aborted", (
        f"first /btw should have been aborted by the replacement; got state={terminals['req-A'].state!r}"
        + f" (error_message={terminals['req-A'].error_message!r}). Architecture §4.4.3 mandates SIGTERM-on-replace."
    )
    assert terminals["req-B"].state == "done", (
        f"second /btw should have completed normally; got state={terminals['req-B'].state!r}."
    )
    # The first turn's natural duration is 10s. If the abort actually fires,
    # both turns settle within ~2s of when the second was dispatched. A wall
    # clock close to 10s means the first ran to completion despite the
    # replacement. The budget clears the abort's 5.0s force-kill grace
    # (BtwProcessManager.abort), so a slow-but-working SIGTERM reap under CI
    # load isn't a false failure, while staying under the 10s no-abort case.
    assert elapsed < 9.0, (
        f"both /btw turns took {elapsed:.1f}s to settle — the first /btw was not aborted promptly."
        + " Architecture §4.4.3 requires the in-flight subprocess to be SIGTERM'd when a replacement arrives."
    )
