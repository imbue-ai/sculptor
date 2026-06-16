"""Workspace setup command runner.

Owns the lifecycle of the per-project bash setup command for a workspace:
state machine, head+tail bounded log buffer, on-disk log persistence, and
observer-based event emission for the streaming layer.
"""

import dataclasses
import os
import threading
import time
import uuid
from collections import deque
from pathlib import Path
from typing import Callable
from typing import Literal
from typing import Protocol
from typing import runtime_checkable

from loguru import logger

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import CompoundEvent
from sculptor.foundation.event_utils import ReadOnlyEvent

SubprocessRunner = Callable[[str, Callable[[bytes], None], Callable[[int], None], ReadOnlyEvent], int]

SetupStatus = Literal["not_configured", "pending", "running", "succeeded", "failed", "legacy"]

HEAD_BYTES = 512 * 1024
TAIL_BYTES = 512 * 1024
TRUNCATION_MARKER = b"\n--- output truncated ---\n"
LOG_FILENAME = "setup_log.txt"
# Upper bound on how long DefaultSetupStateProvider will block on
# wait_for_pid before giving up and skipping the reminder. The bash PID is
# recorded synchronously right after Popen succeeds — typically within
# milliseconds of the worker thread starting — so half a second is already
# generous. Anything past this is a stuck slot, and we'd rather drop the
# reminder than block the agent's first message.
PROVIDER_WAIT_FOR_PID_TIMEOUT_SECONDS = 0.5


@dataclasses.dataclass(frozen=True)
class SetupStateChanged:
    workspace_id: str
    status: SetupStatus
    run_id: str | None
    command: str | None
    exit_code: int | None
    started_at: float | None
    finished_at: float | None
    log_truncated: bool
    log_path: str | None
    pid: int | None = None


@dataclasses.dataclass(frozen=True)
class RunningSetup:
    command: str
    pid: int
    log_path: str


@dataclasses.dataclass(frozen=True)
class FailedSetup:
    command: str
    exit_code: int
    log_path: str


SetupReminderState = RunningSetup | FailedSetup


@runtime_checkable
class SetupStateProvider(Protocol):
    def get_reminder_state(self) -> SetupReminderState | None: ...


@dataclasses.dataclass(frozen=True)
class SetupOutputChunk:
    workspace_id: str
    run_id: str
    seq: int
    data: bytes


class RunnerSlot:
    def __init__(self, workspace_id: str) -> None:
        self.workspace_id: str = workspace_id
        self.run_id: str | None = None
        self.command: str | None = None
        self.status: SetupStatus = "pending"
        self.exit_code: int | None = None
        self.started_at: float | None = None
        self.finished_at: float | None = None
        self.log_truncated: bool = False
        self.log_path: str | None = None
        self.head_buffer: bytearray = bytearray()
        self.tail_buffer: deque[bytes] = deque()
        self.tail_size: int = 0
        self.seq: int = 0
        self.cancel_event: threading.Event = threading.Event()
        self.lock: threading.Lock = threading.Lock()
        self.pid: int | None = None
        self.pid_ready: threading.Event = threading.Event()
        self.state_dir: Path | None = None

    def to_state_changed(self) -> SetupStateChanged:
        return SetupStateChanged(
            workspace_id=self.workspace_id,
            status=self.status,
            run_id=self.run_id,
            command=self.command,
            exit_code=self.exit_code,
            started_at=self.started_at,
            finished_at=self.finished_at,
            log_truncated=self.log_truncated,
            log_path=self.log_path,
            pid=self.pid,
        )


class SetupCommandRunner:
    def __init__(self, concurrency_group: ConcurrencyGroup) -> None:
        self._concurrency_group: ConcurrencyGroup = concurrency_group
        self._slots: dict[str, RunnerSlot] = {}
        self._lock: threading.Lock = threading.Lock()
        self._state_observers: list[Callable[[SetupStateChanged], None]] = []
        self._output_observers: list[Callable[[SetupOutputChunk], None]] = []
        self._observer_lock: threading.Lock = threading.Lock()

    def add_state_observer(self, callback: Callable[[SetupStateChanged], None]) -> None:
        with self._observer_lock:
            self._state_observers.append(callback)

    def remove_state_observer(self, callback: Callable[[SetupStateChanged], None]) -> None:
        with self._observer_lock:
            if callback in self._state_observers:
                self._state_observers.remove(callback)

    def add_output_observer(self, callback: Callable[[SetupOutputChunk], None]) -> None:
        with self._observer_lock:
            self._output_observers.append(callback)

    def remove_output_observer(self, callback: Callable[[SetupOutputChunk], None]) -> None:
        with self._observer_lock:
            if callback in self._output_observers:
                self._output_observers.remove(callback)

    def _notify_state(self, event: SetupStateChanged) -> None:
        with self._observer_lock:
            observers = list(self._state_observers)
        for callback in observers:
            try:
                callback(event)
            except Exception as exc:
                logger.error("setup state observer raised: {}", exc)

    def _notify_output(self, event: SetupOutputChunk) -> None:
        with self._observer_lock:
            observers = list(self._output_observers)
        for callback in observers:
            try:
                callback(event)
            except Exception as exc:
                logger.error("setup output observer raised: {}", exc)

    def get_state(self, workspace_id: str) -> SetupStateChanged | None:
        with self._lock:
            slot = self._slots.get(workspace_id)
            if slot is None:
                return None
            return slot.to_state_changed()

    def iter_states(self) -> list[SetupStateChanged]:
        with self._lock:
            return [slot.to_state_changed() for slot in self._slots.values()]

    def get_buffered_output(self, workspace_id: str) -> tuple[str | None, int, bytes, bytes, bool]:
        with self._lock:
            slot = self._slots.get(workspace_id)
            if slot is None:
                return None, 0, b"", b"", False
            with slot.lock:
                head = bytes(slot.head_buffer)
                tail = b"".join(slot.tail_buffer)
                return slot.run_id, slot.seq, head, tail, slot.log_truncated

    def start(
        self,
        workspace_id: str,
        command: str,
        subprocess_runner: SubprocessRunner,
        shutdown_event_source: ReadOnlyEvent,
        state_dir: Path,
        on_persist: Callable[[SetupStateChanged], None],
    ) -> SetupStateChanged:
        """Begin (or re-begin) a setup run for `workspace_id`.

        Idempotent for in-flight runs: returns the current state without
        starting a new one if a run is already `running`. Used both for the
        initial kick-off and for manual reruns after a terminal state.
        """
        with self._lock:
            existing = self._slots.get(workspace_id)
            if existing is not None and existing.status == "running":
                return existing.to_state_changed()
            log_path = state_dir / LOG_FILENAME
            try:
                if log_path.exists():
                    log_path.unlink()
            except OSError as exc:
                logger.error("failed to remove old setup log {}: {}", log_path, exc)
            slot = RunnerSlot(workspace_id)
            slot.run_id = str(uuid.uuid4())
            slot.command = command
            slot.status = "running"
            slot.started_at = time.time()
            slot.state_dir = state_dir
            self._slots[workspace_id] = slot
            event = slot.to_state_changed()
        # Dispatch the running-state event before starting the worker thread.
        # Otherwise a fast subprocess can complete and emit its terminal event
        # before this initial event is delivered, flipping the observable order.
        try:
            on_persist(event)
        except Exception as exc:
            logger.error("on_persist failed for setup start: {}", exc)
        self._notify_state(event)
        self._concurrency_group.start_new_thread(
            target=self._run_worker,
            args=(slot, command, subprocess_runner, shutdown_event_source, state_dir, on_persist),
            name=f"setup-runner-{workspace_id}",
            is_checked=False,
        )
        return event

    def _run_worker(
        self,
        slot: RunnerSlot,
        command: str,
        subprocess_runner: SubprocessRunner,
        shutdown_event_source: ReadOnlyEvent,
        state_dir: Path,
        on_persist: Callable[[SetupStateChanged], None],
    ) -> None:
        combined = CompoundEvent([slot.cancel_event, shutdown_event_source])
        chunk_handler = _ChunkHandler(self, slot)
        pid_handler = _PidHandler(self, slot, on_persist)

        exit_code: int | None = None
        event: SetupStateChanged | None = None
        try:
            try:
                exit_code = subprocess_runner(command, chunk_handler, pid_handler, combined)
            except Exception as exc:
                logger.error("setup subprocess raised: {}", exc)
                exit_code = None
            with slot.lock:
                slot.exit_code = exit_code
                slot.finished_at = time.time()
                try:
                    _write_log_file(slot, state_dir)
                except Exception as exc:
                    logger.error("failed to persist setup log file: {}", exc)
                slot.status = "succeeded" if exit_code == 0 else "failed"
                event = slot.to_state_changed()
        except Exception as exc:
            # Belt-and-suspenders: if anything unexpected escapes the body
            # above, force a terminal failed state so waiters do not hang.
            logger.error("setup worker raised unexpectedly: {}", exc)
            with slot.lock:
                if slot.status == "running":
                    slot.exit_code = exit_code
                    slot.finished_at = time.time()
                    slot.status = "failed"
                event = slot.to_state_changed()
        finally:
            # Always release pid_ready so wait_for_pid never blocks indefinitely.
            slot.pid_ready.set()
        if event is not None:
            try:
                on_persist(event)
            except Exception as exc:
                logger.error("on_persist failed for setup terminal state: {}", exc)
            self._notify_state(event)

    def cancel(self, workspace_id: str) -> bool:
        with self._lock:
            slot = self._slots.get(workspace_id)
            if slot is None or slot.status != "running":
                return False
            slot.cancel_event.set()
            return True

    def mark_failed_for_reconcile(
        self,
        workspace_id: str,
        started_at: float | None,
        on_persist: Callable[[SetupStateChanged], None],
    ) -> SetupStateChanged:
        with self._lock:
            slot = self._slots.get(workspace_id)
            if slot is None:
                slot = RunnerSlot(workspace_id)
                self._slots[workspace_id] = slot
            slot.status = "failed"
            slot.exit_code = None
            slot.started_at = started_at
            slot.finished_at = time.time()
            event = slot.to_state_changed()
        slot.pid_ready.set()
        try:
            on_persist(event)
        except Exception as exc:
            logger.error("on_persist failed for reconcile: {}", exc)
        self._notify_state(event)
        return event

    def wait_for_pid(self, workspace_id: str, timeout: float | None = None) -> int | None:
        with self._lock:
            slot = self._slots.get(workspace_id)
            if slot is None:
                return None
        slot.pid_ready.wait(timeout)
        with slot.lock:
            return slot.pid

    def get_log_path(self, workspace_id: str) -> Path | None:
        """Absolute host path to the workspace's persisted setup log.

        Returns ``None`` if no slot exists for the workspace or the slot
        never recorded a ``state_dir`` (e.g. a reconcile-only slot). The
        ``SetupCommandRunner`` is the single source of truth for this path
        so callers never have to recompute the workspace state directory.
        """
        with self._lock:
            slot = self._slots.get(workspace_id)
            if slot is None or slot.state_dir is None:
                return None
            filename = slot.log_path or LOG_FILENAME
            return slot.state_dir / filename

    def stop_all(self) -> None:
        with self._lock:
            slots = list(self._slots.values())
        for slot in slots:
            if slot.status == "running":
                slot.cancel_event.set()
            slot.pid_ready.set()


class _ChunkHandler:
    def __init__(self, runner: "SetupCommandRunner", slot: RunnerSlot) -> None:
        self._runner = runner
        self._slot = slot

    def __call__(self, data: bytes) -> None:
        if not data:
            return
        slot = self._slot
        with slot.lock:
            slot.seq += 1
            head_remaining = HEAD_BYTES - len(slot.head_buffer)
            if head_remaining > 0:
                head_take = data[:head_remaining]
                slot.head_buffer.extend(head_take)
                overflow = data[head_remaining:]
            else:
                overflow = data
            if overflow:
                slot.log_truncated = True
                slot.tail_buffer.append(overflow)
                slot.tail_size += len(overflow)
                while slot.tail_size > TAIL_BYTES and slot.tail_buffer:
                    oldest = slot.tail_buffer[0]
                    excess = slot.tail_size - TAIL_BYTES
                    if len(oldest) <= excess:
                        slot.tail_buffer.popleft()
                        slot.tail_size -= len(oldest)
                    else:
                        slot.tail_buffer[0] = oldest[excess:]
                        slot.tail_size -= excess
            assert slot.run_id is not None
            event = SetupOutputChunk(
                workspace_id=slot.workspace_id,
                run_id=slot.run_id,
                seq=slot.seq,
                data=data,
            )
        self._runner._notify_output(event)


class DefaultSetupStateProvider:
    def __init__(self, runner: "SetupCommandRunner", workspace_id: str) -> None:
        self._runner = runner
        self._workspace_id = workspace_id

    def _absolute_log_path(self) -> str | None:
        path = self._runner.get_log_path(self._workspace_id)
        return None if path is None else str(path)

    def get_reminder_state(self) -> SetupReminderState | None:
        state = self._runner.get_state(self._workspace_id)
        if state is None:
            return None
        if state.status in ("not_configured", "succeeded", "pending", "legacy"):
            return None
        if state.status == "failed":
            if state.command is None or state.exit_code is None:
                return None
            log_path = self._absolute_log_path()
            if log_path is None:
                return None
            return FailedSetup(command=state.command, exit_code=state.exit_code, log_path=log_path)
        if state.status == "running":
            pid = self._runner.wait_for_pid(self._workspace_id, timeout=PROVIDER_WAIT_FOR_PID_TIMEOUT_SECONDS)
            snapshot = self._runner.get_state(self._workspace_id)
            if snapshot is None:
                return None
            if pid is None or snapshot.status != "running":
                # The slot transitioned during the wait (or never recorded a
                # PID). Dispatch on the new status.
                if snapshot.status == "failed":
                    if snapshot.command is None or snapshot.exit_code is None:
                        return None
                    log_path = self._absolute_log_path()
                    if log_path is None:
                        return None
                    return FailedSetup(command=snapshot.command, exit_code=snapshot.exit_code, log_path=log_path)
                return None
            if snapshot.command is None:
                return None
            log_path = self._absolute_log_path()
            if log_path is None:
                return None
            return RunningSetup(command=snapshot.command, pid=pid, log_path=log_path)
        return None


class _PidHandler:
    def __init__(
        self,
        runner: "SetupCommandRunner",
        slot: RunnerSlot,
        on_persist: Callable[[SetupStateChanged], None],
    ) -> None:
        self._runner = runner
        self._slot = slot
        self._on_persist = on_persist

    def __call__(self, pid: int) -> None:
        slot = self._slot
        with slot.lock:
            slot.pid = pid
            snapshot = slot.to_state_changed()
        slot.pid_ready.set()
        try:
            self._on_persist(snapshot)
        except Exception as exc:
            logger.error("on_persist failed for setup pid: {}", exc)
        self._runner._notify_state(snapshot)


def _write_log_file(slot: RunnerSlot, state_dir: Path) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    final_path = state_dir / LOG_FILENAME
    tmp_path = state_dir / (LOG_FILENAME + ".tmp")
    payload = bytes(slot.head_buffer)
    if slot.log_truncated:
        payload += TRUNCATION_MARKER
    payload += b"".join(slot.tail_buffer)
    with tmp_path.open("wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    tmp_path.replace(final_path)
    slot.log_path = LOG_FILENAME
