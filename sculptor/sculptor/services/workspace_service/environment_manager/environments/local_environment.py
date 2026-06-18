import os
import shutil
import signal
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable
from typing import Mapping
from typing import Sequence
from typing import TYPE_CHECKING
from typing import Union

from loguru import logger
from pydantic import PrivateAttr

from sculptor.agents.default.constants import CLONE_MODE_PROMPT
from sculptor.agents.default.constants import IN_PLACE_MODE_PROMPT
from sculptor.agents.default.constants import WORKTREE_MODE_PROMPT
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.event_utils import CompoundEvent
from sculptor.foundation.event_utils import MutableEvent
from sculptor.foundation.event_utils import ReadOnlyEvent
from sculptor.foundation.processes.local_process import RunningProcess
from sculptor.foundation.processes.local_process import run_background
from sculptor.foundation.secrets_utils import Secret
from sculptor.interfaces.environments.base import Environment
from sculptor.interfaces.environments.errors import FileOrDirectoryCouldNotBeDeletedError
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.services.workspace_service.environment_manager.env_file_parser import atomic_copy_env_file
from sculptor.services.workspace_service.environment_manager.env_file_parser import load_project_env_vars
from sculptor.services.workspace_service.environment_manager.environments.clone_strategy import clone_repository
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    TerminalEnvironmentConfig,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    register_environment_config,
)
from sculptor.services.workspace_service.environment_manager.environments.local_terminal_manager import (
    stop_terminals_for_environment,
)
from sculptor.services.workspace_service.environment_manager.environments.worktree_strategy import create_worktree
from sculptor.utils.build import get_workspaces_folder

# Workspace directory for local environments
LOCAL_WORKSPACE_DIR = get_workspaces_folder()

# Budget for polling getpgid() until the child's setsid lands. Under Modal's
# slow PID namespace the parent can observe the child before setsid runs (see
# the comment in run_setup_subprocess for the full story). 200 ms is well
# beyond the observed convergence time without making genuine setsid failures
# slow to report.
_SETUP_PGID_CONVERGE_TIMEOUT_S = 0.2
_SETUP_PGID_POLL_INTERVAL_S = 0.005

# Cancel ladder for the setup subprocess: escalate SIGINT -> SIGTERM -> SIGKILL,
# giving the process group a grace period at each step to exit on its own.
_CANCEL_SIGTERM_DELAY_S = 2.0
_CANCEL_SIGKILL_DELAY_S = 5.0

# https://github.com/python/typeshed/tree/main/stdlib/_typeshed
if TYPE_CHECKING:
    # for proper file mode typing
    from _typeshed import OpenBinaryModeReading
    from _typeshed import OpenBinaryModeWriting
    from _typeshed import OpenTextModeReading
    from _typeshed import OpenTextModeWriting


class LocalEnvironment(Environment):
    object_type: str = "LocalEnvironment"
    # pyrefly: ignore [bad-override-mutable-attribute]
    environment_id: LocalEnvironmentID
    concurrency_group: ConcurrencyGroup
    # The repo host path - points directly to the user's repository.
    # This is always set when creating or resuming an environment.
    repo_host_path: Path | None = None
    initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.IN_PLACE
    _processes: list[RunningProcess] = PrivateAttr(default_factory=list)
    _is_closed: bool = PrivateAttr(default=False)
    _closing_lock: threading.Lock = PrivateAttr(default_factory=threading.Lock)
    _project_env_vars: dict[str, str] = PrivateAttr(default_factory=dict)
    _env_var_override: bool = PrivateAttr(default=False)
    # Resolved at create/resume so per-command env reloads can target the same folder
    # the initial load used (tests pass an explicit folder; runtime falls back to
    # SCULPTOR_FOLDER via env_file_parser.load_project_env_vars).
    _sculptor_folder: Path | None = PrivateAttr(default=None)
    # SCULPT_* env vars to expose in terminals (e.g. for the sculpt CLI).
    # The terminal pty strips all inherited SCULPTOR_* vars to avoid leaking backend
    # internals; SCULPT_* vars are injected via extra_env so the sculpt CLI works.
    _sculpt_terminal_env_vars: dict[str, str] = PrivateAttr(default_factory=dict)

    def get_project_env_var_names(self) -> list[str]:
        return list(self._project_env_vars.keys())

    def set_sculpt_terminal_env_vars(self, env_vars: dict[str, str]) -> None:
        """Set SCULPT_* env vars that should be available in terminal sessions.

        The terminal pty strips all SCULPTOR_* vars inherited from the backend process.
        SCULPT_* vars set here are injected via extra_env so the sculpt CLI works in terminals.
        """
        self._sculpt_terminal_env_vars = env_vars

    # ===== Capability Properties =====

    @property
    def supports_terminal(self) -> bool:
        """Local environments support terminal via direct pty management."""
        return True

    @property
    def workspace_path(self) -> str:
        """The workspace path as a string (the environment_id).

        The workspace is the task's root folder containing state/, artifacts/, etc.
        """
        return self.environment_id

    def get_workspace_path(self) -> Path:
        """Get the workspace path for LocalEnvironment.

        Returns the path to the task's workspace directory (state/artifacts).
        """
        return Path(self.workspace_path)

    def get_working_directory(self) -> Path:
        """Get the directory where the agent should perform all work.

        - In-place mode: Returns the user's original repository path.
        - Clone mode / Worktree mode: Returns the checkout at workspace/code/.
        """
        if self.initialization_strategy in (
            WorkspaceInitializationStrategy.CLONE,
            WorkspaceInitializationStrategy.WORKTREE,
        ):
            return self.get_workspace_path() / "code"
        if self.repo_host_path is None:
            raise ValueError("repo_host_path must be set for LocalEnvironment")
        return self.repo_host_path

    def get_system_prompt(self) -> str | None:
        """Get the environment-specific system prompt content.

        Returns mode-specific instructions based on initialization_strategy,
        plus the workspace attachments path for image display.
        """
        if self.initialization_strategy == WorkspaceInitializationStrategy.IN_PLACE:
            mode_prompt = IN_PLACE_MODE_PROMPT
        elif self.initialization_strategy == WorkspaceInitializationStrategy.WORKTREE:
            mode_prompt = WORKTREE_MODE_PROMPT
        else:
            mode_prompt = CLONE_MODE_PROMPT

        attachments_path = self.get_attachments_path()
        attachments_prompt = f"\nThe workspace attachments directory is: {attachments_path}\nSave any media you want to display (e.g. screenshots, video recordings) to this directory.\n"

        return mode_prompt + attachments_prompt

    @classmethod
    def create(
        cls,
        environment_id: LocalEnvironmentID,
        project_id: ProjectID,
        concurrency_group: ConcurrencyGroup,
        repo_host_path: Path,
        initialization_strategy: WorkspaceInitializationStrategy = WorkspaceInitializationStrategy.IN_PLACE,
        source_branch: str | None = None,
        requested_branch_name: str | None = None,
        env_var_override: bool = False,
        sculptor_folder: Path | None = None,
    ) -> "LocalEnvironment":
        """Factory method to create a new LocalEnvironment with directories initialized.

        Creates the environment and ensures the state and artifacts directories exist.
        For clone mode, clones the repository to workspace/code/.
        For worktree mode, runs `git worktree add` off the user's repository into workspace/code/.
        For in-place mode, the agent works directly in the user's repository.
        Use the constructor directly when resuming an existing environment.

        Args:
            environment_id: The ID for this environment.
            project_id: The project this environment belongs to.
            concurrency_group: Concurrency group for process management.
            repo_host_path: Path to the user's repository.
            initialization_strategy: Strategy for workspace initialization.
            source_branch: Branch to checkout after cloning (for CLONE mode) or base
                ref off which to create the worktree branch (for WORKTREE mode).
            requested_branch_name: For WORKTREE mode, the new branch name created by
                `git worktree add -b`; required for WORKTREE, unused otherwise.
            sculptor_folder: Override for the sculptor folder path (uses get_workspaces_folder() if None).
        """
        environment = cls(
            environment_id=environment_id,
            project_id=project_id,
            concurrency_group=concurrency_group,
            repo_host_path=repo_host_path,
            initialization_strategy=initialization_strategy,
        )
        # Create state and artifacts directories
        environment.to_host_path(environment.get_state_path()).mkdir(parents=True, exist_ok=True)
        environment.to_host_path(environment.get_artifacts_path()).mkdir(parents=True, exist_ok=True)

        # For clone mode, clone the repository to workspace/code/
        if initialization_strategy == WorkspaceInitializationStrategy.CLONE:
            assert repo_host_path is not None
            clone_repository(
                source_repo_path=repo_host_path,
                destination=environment.get_working_directory(),
                concurrency_group=concurrency_group,
                target_branch=source_branch,
            )
            # If the user asked for a named branch inside the clone, create and
            # check it out off the base branch. The collision re-check happens at
            # the API layer so we don't need to handle "already exists" here.
            if requested_branch_name is not None and requested_branch_name.strip():
                concurrency_group.run_process_to_completion(
                    command=["git", "checkout", "-b", requested_branch_name],
                    cwd=environment.get_working_directory(),
                    is_checked_after=True,
                )
            # Copy .sculptor/.env from the source repo into the clone.
            # Git does not copy gitignored files, so this must be done explicitly.
            source_env_file = repo_host_path / ".sculptor" / ".env"
            if source_env_file.exists():
                dest_env_file = environment.get_working_directory() / ".sculptor" / ".env"
                atomic_copy_env_file(source_env_file, dest_env_file)
        elif initialization_strategy == WorkspaceInitializationStrategy.WORKTREE:
            if requested_branch_name is None:
                raise ValueError("requested_branch_name is required for WORKTREE initialization")
            if source_branch is None:
                raise ValueError("source_branch (base ref) is required for WORKTREE initialization")
            create_worktree(
                user_repo_path=repo_host_path,
                destination=environment.get_working_directory(),
                concurrency_group=concurrency_group,
                base_ref=source_branch,
                new_branch=requested_branch_name,
            )
            # Gitignored files don't follow the worktree either; mirror the CLONE behavior.
            source_env_file = repo_host_path / ".sculptor" / ".env"
            if source_env_file.exists():
                dest_env_file = environment.get_working_directory() / ".sculptor" / ".env"
                atomic_copy_env_file(source_env_file, dest_env_file)

        environment._sculptor_folder = sculptor_folder
        environment._project_env_vars = load_project_env_vars(
            environment.get_working_directory(), sculptor_folder=sculptor_folder
        )
        environment._env_var_override = env_var_override

        return environment

    def get_root_path(self) -> Path:
        """Get the root path for LocalEnvironment.

        Returns the workspace path where environment files are stored.
        """
        return self.get_workspace_path()

    def get_user_home_directory(self) -> Path:
        """Return the current user's home directory."""
        return Path.home()

    def to_host_path(self, path: Path) -> Path:
        """Convert an environment path to a host filesystem path.

        For LocalEnvironment:
        - Paths already under working directory or workspace are returned as-is
        - Other absolute paths are mapped to workspace_path/...
        """
        assert path.is_absolute()

        # Check if path is under or equal to the working directory
        working_dir = self.get_working_directory()
        if path.is_relative_to(working_dir):
            return path

        # Check if path is under or equal to the workspace path
        workspace_path = self.get_workspace_path()
        if path.is_relative_to(workspace_path):
            return path

        # Other paths map to workspace_path
        return workspace_path / str(path).lstrip("/")

    def to_environment_path(self, path: Path) -> Path:
        """Convert a host filesystem path to an environment path.

        For LocalEnvironment:
        - Paths under the working directory are returned as-is
        - Paths under workspace_path are converted to /... relative paths

        Uses ``Path.resolve()`` so that macOS ``/var`` ↔ ``/private/var``
        symlinks don't cause spurious mismatches.  The returned path is
        reconstructed with the original (non-resolved) base so that
        downstream ``startswith`` checks against ``workspace_path`` remain
        consistent.
        """
        assert path.is_absolute()
        resolved_path = path.resolve()

        # Check if path is under or equal to the working directory
        working_dir = self.get_working_directory()
        resolved_working_dir = working_dir.resolve()
        if resolved_path.is_relative_to(resolved_working_dir):
            # Reconstruct using the original working_dir base for consistency
            return working_dir / resolved_path.relative_to(resolved_working_dir)

        # Paths under workspace_path are converted to /... relative paths
        workspace_path = self.get_workspace_path()
        resolved_workspace_path = workspace_path.resolve()
        assert resolved_path.is_relative_to(resolved_workspace_path), (
            f"Path {path} is not under working directory or workspace"
        )
        relative_path = resolved_path.relative_to(resolved_workspace_path)
        return Path("/") / relative_path

    def get_extra_logger_context(self) -> Mapping[str, str | float | int | bool | None]:
        return {"workspace_path": self.workspace_path}

    def _run_process_in_background(
        self,
        command: Sequence[str],
        secrets: Mapping[str, str | Secret],
        cwd: str | None = None,
        is_interactive: bool = False,
        run_with_sudo_privileges: bool = False,
        run_as_root: bool = False,
        shutdown_event: MutableEvent | None = None,
        timeout: float | None = None,
        is_checked: bool = False,
        on_output: Callable[[str, bool], None] | None = None,
        open_stdin: bool = False,
        isolate_process_group: bool = False,
    ) -> RunningProcess:
        if run_with_sudo_privileges or run_as_root:
            raise NotImplementedError()

        secrets_dict = {k: v.unwrap() if isinstance(v, Secret) else v for k, v in secrets.items()}
        # Re-read .env files on every launch so existing agents pick up changes
        # the user makes to ~/.sculptor/.env or .sculptor/.env after the workspace
        # was created.
        project_env_vars = load_project_env_vars(self.get_working_directory(), sculptor_folder=self._sculptor_folder)
        if self._env_var_override:
            merged = {**os.environ, **project_env_vars}
        else:
            merged = {**project_env_vars, **os.environ}
        env = {**merged, **secrets_dict}
        # Remove CLAUDECODE so spawned Claude Code processes don't refuse to start
        # thinking they're nested inside another Claude Code session.
        env.pop("CLAUDECODE", None)
        logger.info("Launching process: {} in workspace: {}", (" ".join(command))[:50], self.workspace_path)
        logger.trace("Launching process: {}", " ".join(command))
        workdir = self.to_host_path(Path(cwd) if cwd else self.get_working_directory())
        process = run_background(
            command,
            cwd=workdir,
            env={k: str(v) for k, v in env.items() if v is not None},
            is_checked=is_checked,
            timeout=timeout,
            shutdown_event=shutdown_event,
            open_stdin=open_stdin,
            isolate_process_group=isolate_process_group,
        )
        self._processes.append(process)
        return process

    def run_setup_subprocess(
        self,
        command: str,
        on_chunk: Callable[[bytes], None],
        on_pid: Callable[[int], None],
        shutdown_event: ReadOnlyEvent,
    ) -> int:
        # Run setup in the agent's working directory: for CLONE workspaces
        # this is the freshly-cloned copy under workspace/code/, not the
        # user's original repo. That's where build artifacts should land
        # (node_modules, .venv, etc.) so the agent sees them when it runs.
        working_directory = self.get_working_directory()
        if self._env_var_override:
            merged = {**os.environ, **self._project_env_vars}
        else:
            merged = {**self._project_env_vars, **os.environ}
        merged.pop("CLAUDECODE", None)
        env = {k: str(v) for k, v in merged.items() if v is not None}
        logger.info("Starting setup subprocess in workspace: {}", self.workspace_path)
        process = subprocess.Popen(
            ["bash", "-l", "-c", command],
            cwd=str(working_directory),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            bufsize=0,
            env=env,
        )
        # Verify start_new_session=True took effect: the child should be its
        # own process-group leader (setsid makes pgid == pid). Two races can
        # fire on Modal's slow PID namespace, so poll briefly instead of
        # reading once:
        #
        # 1. Fast-exit race (SCU-534, commit adc6c9378b1): the child can be
        #    reaped before getpgid() runs, so getpgid raises
        #    ProcessLookupError. Nothing to verify on a corpse — skip the
        #    check.
        # 2. Slow-setsid race (SCU-1205): CPython's _posixsubprocess.fork_exec
        #    calls the child's setsid() after fork without the parent waiting
        #    on it, so getpgid() can observe the child *before* setsid lands
        #    and return the parent's pgid. Poll until pgid converges to pid
        #    or the budget runs out.
        deadline = time.monotonic() + _SETUP_PGID_CONVERGE_TIMEOUT_S
        child_pgid: int | None = None
        while True:
            try:
                child_pgid = os.getpgid(process.pid)
            except ProcessLookupError:
                child_pgid = None
                break
            if child_pgid == process.pid:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(_SETUP_PGID_POLL_INTERVAL_S)
        if child_pgid is not None and child_pgid != process.pid:
            try:
                process.kill()
            finally:
                process.wait()
            raise RuntimeError(
                f"setup subprocess pgid {child_pgid} != pid {process.pid}; start_new_session did not take effect"
            )

        on_pid(process.pid)

        combined_event = CompoundEvent([shutdown_event, self.concurrency_group.shutdown_event])
        reader_thread = threading.Thread(
            target=_drain_setup_stdout,
            args=(process, on_chunk),
            name="setup-subprocess-reader",
            daemon=True,
        )
        reader_thread.start()

        cancel_state = _CancelLadderState()
        try:
            while True:
                try:
                    process.wait(timeout=0.1)
                    break
                except subprocess.TimeoutExpired:
                    if combined_event.is_set():
                        cancel_state.advance(process.pid)
        finally:
            reader_thread.join(timeout=5.0)

        logger.info("Setup subprocess exited with code {}", process.returncode)
        return process.returncode

    def is_alive(self) -> bool:
        # Local workspaces are always "alive" as long as the directory exists
        return Path(self.workspace_path).exists()

    def exists(self, path: str) -> bool:
        file_path = self.to_host_path(Path("/" + path.lstrip("/")))
        return file_path.exists()

    def read_file(self, path: str, mode: Union["OpenTextModeReading", "OpenBinaryModeReading"] = "r") -> str | bytes:
        file_path = self.to_host_path(Path("/" + path.lstrip("/")))
        with open(file_path, mode) as f:
            return f.read()

    def write_file(
        self,
        path: str,
        content: str | bytes,
        mode: Union["OpenTextModeWriting", "OpenBinaryModeWriting"] = "w",
    ) -> None:
        file_path = self.to_host_path(Path("/" + path.lstrip("/")))
        file_path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes) and "b" not in mode:
            raise TypeError(f"Cannot write bytes content with text mode '{mode}'. Use mode='wb' for binary content.")
        with open(file_path, mode) as f:
            f.write(content)

    def delete_file_or_directory(self, path: str) -> None:
        file_path = self.to_host_path(Path("/" + path.lstrip("/")))
        try:
            if file_path.is_dir():
                shutil.rmtree(file_path)
            else:
                file_path.unlink()
        except OSError as e:
            raise FileOrDirectoryCouldNotBeDeletedError(f"Failed to delete file or directory at {path}: {e}") from e

    def start_terminal_manager(
        self,
        concurrency_group: ConcurrencyGroup,
    ) -> None:
        """Register terminal config so terminals can be created on demand.

        PTY processes are NOT started here — they are created lazily when the
        frontend opens a terminal WebSocket connection. This avoids CG lock
        contention during startup when many agents restart simultaneously.

        Args:
            concurrency_group: Long-lived concurrency group for terminal thread/process
                lifecycle management. Should outlive individual agent runs.
        """
        # Register environment config so the on-demand terminal creation path
        # (WebSocket endpoint -> create_terminal_for_environment) can find the
        # workspace path, working directory, and CG for this environment.
        # Project env vars are NOT registered here — create_terminal_for_environment
        # re-reads them from disk so newly opened terminals pick up changes the
        # user makes after workspace creation. Only the static SCULPT_* vars are
        # registered as ``extra_env`` (the pty strips inherited SCULPTOR_* vars,
        # so SCULPT_* must be re-injected for the sculpt CLI to work).
        register_environment_config(
            str(self.environment_id),
            TerminalEnvironmentConfig(
                workspace_path=self.get_workspace_path(),
                working_directory=self.get_working_directory(),
                concurrency_group=concurrency_group,
                extra_env=dict(self._sculpt_terminal_env_vars),
                env_var_override=self._env_var_override,
                sculptor_folder=self._sculptor_folder,
            ),
        )

    def close(self) -> None:
        with self._closing_lock:
            if self._is_closed:
                return
            logger.info("Stopping all processes for LocalEnvironment")

            # Terminal is NOT stopped here — it outlives individual agent runs and is
            # only stopped when the workspace is destroyed (see destroy()).

            for process in self._processes:
                try:
                    if process.poll() is None:
                        process.terminate(force_kill_seconds=5.0)
                except Exception as e:
                    logger.warning(f"Failed to terminate process: {e}")

            self._is_closed = True

    def destroy(self, is_killing: bool = False) -> None:
        # Stop all terminals (all indices) before closing — terminals only die when workspace is destroyed.
        stop_terminals_for_environment(str(self.environment_id))
        self.close()
        with self._closing_lock:
            remove_local_environment(Path(self.workspace_path))


def _drain_setup_stdout(process: subprocess.Popen, on_chunk: Callable[[bytes], None]) -> None:
    stdout = process.stdout
    assert stdout is not None
    fd = stdout.fileno()
    try:
        while True:
            try:
                chunk = os.read(fd, 4096)
            except OSError:
                break
            if not chunk:
                break
            try:
                on_chunk(chunk)
            except Exception as exc:
                logger.error("setup on_chunk callback raised: {}", exc)
    finally:
        try:
            stdout.close()
        except OSError as exc:
            logger.debug("Failed to close setup subprocess stdout: {}", exc)


class _CancelLadderState:
    def __init__(self) -> None:
        self.sent_sigint: bool = False
        self.sent_sigterm: bool = False
        self.cancel_started_at: float = 0.0

    def advance(self, pid: int) -> None:
        try:
            pgid = os.getpgid(pid)
        except ProcessLookupError:
            return
        now = time.monotonic()
        if not self.sent_sigint:
            logger.info("Cancelling setup subprocess: SIGINT to pgid {}", pgid)
            try:
                os.killpg(pgid, signal.SIGINT)
            except ProcessLookupError:
                return
            self.sent_sigint = True
            self.cancel_started_at = now
            return
        elapsed = now - self.cancel_started_at
        if not self.sent_sigterm and elapsed >= _CANCEL_SIGTERM_DELAY_S:
            logger.info("Cancel ladder: SIGTERM to pgid {}", pgid)
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                return
            self.sent_sigterm = True
            return
        if self.sent_sigterm and elapsed >= _CANCEL_SIGKILL_DELAY_S:
            logger.info("Cancel ladder: SIGKILL to pgid {}", pgid)
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                return


def remove_local_environment(workspace_path: Path) -> None:
    logger.info("Deleting workspace path {}", workspace_path)
    workspace_path = workspace_path.resolve()
    # Resolve LOCAL_WORKSPACE_DIR as well to handle macOS symlinks
    local_workspace_dir_resolved = LOCAL_WORKSPACE_DIR.resolve()
    assert len(str(local_workspace_dir_resolved)) > 3, "Just double checking that you're not deleting your root dir"
    if not workspace_path.is_relative_to(local_workspace_dir_resolved):
        raise RuntimeError(
            f"Refusing to delete workspace path {workspace_path} outside of {local_workspace_dir_resolved}"
        )
    shutil.rmtree(workspace_path, ignore_errors=True)
