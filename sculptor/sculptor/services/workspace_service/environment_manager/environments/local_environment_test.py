import os
import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from queue import Empty
from threading import Event
from typing import Generator
from uuid import uuid4

import pytest

from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.async_monkey_patches_test import expect_exact_logged_errors
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LOCAL_WORKSPACE_DIR
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.environment_manager.environments.worktree_strategy import WorktreeError
from sculptor.testing.local_git_repo import LocalGitRepo


@pytest.fixture
def local_environment(test_root_concurrency_group: ConcurrencyGroup) -> Generator[LocalEnvironment, None, None]:
    workspace_dir = LOCAL_WORKSPACE_DIR / str(uuid4().hex)
    workspace_dir.mkdir(parents=True, exist_ok=True)
    # Create a repo directory to simulate the user's repo
    repo_dir = workspace_dir / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    try:
        local_env = LocalEnvironment.create(
            environment_id=LocalEnvironmentID(str(workspace_dir)),
            project_id=ProjectID(),
            concurrency_group=test_root_concurrency_group,
            repo_host_path=repo_dir,
        )
        yield local_env
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


@dataclass
class CloneTestContext:
    """Shared context for clone-mode environment tests."""

    workspace_dir: Path
    source_repo_path: Path
    sculptor_folder: Path
    concurrency_group: ConcurrencyGroup


@pytest.fixture
def clone_test_ctx(
    test_root_concurrency_group: ConcurrencyGroup, tmp_path: Path
) -> Generator[CloneTestContext, None, None]:
    """Set up a workspace dir, source repo, and fake sculptor folder for clone-mode tests."""
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    workspace_dir.mkdir(parents=True, exist_ok=True)
    source_repo_path = tmp_path / "source_repo"
    make_test_repo(source_repo_path)
    try:
        yield CloneTestContext(
            workspace_dir=workspace_dir,
            source_repo_path=source_repo_path,
            sculptor_folder=tmp_path / "fake_sculptor",
            concurrency_group=test_root_concurrency_group,
        )
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def test_run_setup_subprocess_happy_path(local_environment: LocalEnvironment) -> None:
    chunks: list[bytes] = []
    pids: list[int] = []
    rc = local_environment.run_setup_subprocess("echo hi", chunks.append, pids.append, Event())
    assert rc == 0
    assert b"hi" in b"".join(chunks)


def test_run_setup_subprocess_on_pid_invoked_once(local_environment: LocalEnvironment) -> None:
    pids: list[int] = []
    rc = local_environment.run_setup_subprocess("true", lambda _data: None, pids.append, Event())
    assert rc == 0
    assert len(pids) == 1
    # start_new_session=True makes the bash child its own pgid leader, so
    # pgid == pid for the captured PID.
    assert pids[0] > 0


def test_run_setup_subprocess_on_pid_called_before_chunks(local_environment: LocalEnvironment) -> None:
    events: list[str] = []
    pids: list[int] = []

    def _on_chunk(data: bytes) -> None:
        events.append("chunk")

    def _on_pid(pid: int) -> None:
        assert "chunk" not in events, "on_pid must fire before any chunk"
        pids.append(pid)
        events.append("pid")

    rc = local_environment.run_setup_subprocess("echo hello", _on_chunk, _on_pid, Event())
    assert rc == 0
    assert len(pids) == 1
    assert events[0] == "pid"


def test_run_setup_subprocess_on_pid_skipped_on_pgid_failure(
    local_environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    # If getpgid persistently returns a pgid that doesn't match the pid, the
    # function raises RuntimeError before invoking on_pid. The mock returns a
    # stable wrong value (the test process's pgid — guaranteed not equal to
    # the child's pid) instead of delegating to the real getpgid, because the
    # real call can raise ProcessLookupError on a reaped zombie during the
    # polling window and that is the corpse-skip path, not a setsid failure.
    parent_pgid = os.getpgid(0)

    def _bad_pgid(_pid: int) -> int:
        return parent_pgid

    monkeypatch.setattr(os, "getpgid", _bad_pgid)
    pids: list[int] = []
    with pytest.raises(RuntimeError, match="start_new_session did not take effect"):
        local_environment.run_setup_subprocess("true", lambda _data: None, pids.append, Event())
    assert pids == []


def test_run_setup_subprocess_cwd_is_working_directory(clone_test_ctx: CloneTestContext) -> None:
    """In CLONE mode the setup command must run inside the cloned working
    directory (workspace/code/), not the user's source repo. Build artifacts
    have to land in the clone for the agent to see them."""
    env = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(clone_test_ctx.workspace_dir)),
        project_id=ProjectID(),
        concurrency_group=clone_test_ctx.concurrency_group,
        repo_host_path=clone_test_ctx.source_repo_path,
        initialization_strategy=WorkspaceInitializationStrategy.CLONE,
        sculptor_folder=clone_test_ctx.sculptor_folder,
    )
    chunks: list[bytes] = []
    rc = env.run_setup_subprocess("pwd", chunks.append, lambda _pid: None, Event())
    assert rc == 0
    captured = b"".join(chunks).decode()
    expected = str(env.get_working_directory().resolve())
    assert expected in captured or captured.strip().endswith(expected), (
        f"setup ran in {captured.strip()!r}, expected {expected!r}"
    )
    assert str(clone_test_ctx.source_repo_path.resolve()) not in captured, (
        f"setup should NOT run in the user's source repo, got: {captured!r}"
    )


def test_run_setup_subprocess_non_zero_exit(local_environment: LocalEnvironment) -> None:
    chunks: list[bytes] = []
    rc = local_environment.run_setup_subprocess("exit 7", chunks.append, lambda _pid: None, Event())
    assert rc == 7


def test_run_setup_subprocess_stdin_closed(local_environment: LocalEnvironment) -> None:
    chunks: list[bytes] = []
    start = time.monotonic()
    rc = local_environment.run_setup_subprocess("read x; echo done", chunks.append, lambda _pid: None, Event())
    elapsed = time.monotonic() - start
    # `read` should fail immediately because stdin is /dev/null (EOF), so the
    # command exits without hanging.
    assert elapsed < 5.0
    assert rc == 0
    assert b"done" in b"".join(chunks)


def test_run_setup_subprocess_cancel(local_environment: LocalEnvironment) -> None:
    cancel = Event()
    chunks: list[bytes] = []

    def _trigger_cancel() -> None:
        time.sleep(0.5)
        cancel.set()

    threading.Thread(target=_trigger_cancel, daemon=True).start()
    start = time.monotonic()
    rc = local_environment.run_setup_subprocess("sleep 60", chunks.append, lambda _pid: None, cancel)
    elapsed = time.monotonic() - start
    assert elapsed < 10.0
    assert rc != 0


def test_run_setup_subprocess_kills_process_group(local_environment: LocalEnvironment) -> None:
    cancel = Event()
    chunks: list[bytes] = []
    pid_holder: dict[str, int] = {}

    def _capture_pid(data: bytes) -> None:
        chunks.append(data)
        for line in data.decode("utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.isdigit() and "child" not in pid_holder:
                pid_holder["child"] = int(line)

    def _trigger_cancel() -> None:
        # Wait a moment for the child to print its pid.
        for _ in range(50):
            if "child" in pid_holder:
                break
            time.sleep(0.1)
        cancel.set()

    threading.Thread(target=_trigger_cancel, daemon=True).start()
    rc = local_environment.run_setup_subprocess(
        'bash -c "echo $$; sleep 60" & wait', _capture_pid, lambda _pid: None, cancel
    )
    assert rc != 0
    if "child" in pid_holder:
        time.sleep(1.0)
        with pytest.raises(ProcessLookupError):
            os.kill(pid_holder["child"], 0)


def test_run_setup_subprocess_handles_process_lookup_error(
    local_environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Simulate the fast-exit race: getpgid raises ProcessLookupError on
    # the spawned child. The function must treat this as 'no process group to
    # verify on a corpse' and return the subprocess's exit code instead of
    # logging 'setup subprocess must be in its own process group'.
    def _always_raise(_pid: int) -> int:
        raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(os, "getpgid", _always_raise)
    rc = local_environment.run_setup_subprocess("true", lambda _data: None, lambda _pid: None, Event())
    assert rc == 0


def test_processes_are_closed_on_exit(local_environment: LocalEnvironment):
    proc = local_environment.run_process_in_background(["sleep", "60"], {})
    assert len(local_environment._processes) == 1
    # give it a few seconds to start
    # otherwise the test is flaky because the process might not have started before we call close below
    time.sleep(5.0)
    assert proc.poll() is None
    local_environment.close()
    assert proc.poll() is not None


def make_test_repo(
    repo_path: Path,
    user_name: str = "Test User",
    user_email: str = "test@example.com",
    initial_file: str = "test.txt",
    initial_content: str = "content",
    initial_commit_msg: str = "Initial commit",
) -> LocalGitRepo:
    """Helper to create a test repository."""
    repo_path.mkdir(parents=True, exist_ok=True)
    repo = LocalGitRepo(repo_path)
    repo.write_file(initial_file, initial_content)
    repo.configure_git(git_user_name=user_name, git_user_email=user_email)
    return repo


def add_commit_to_repo(repo_path: Path, filename: str, content: str, commit_msg: str) -> None:
    """Helper to add a commit to an existing repository."""
    repo = LocalGitRepo(repo_path)
    repo.write_file(filename, content)
    repo.run_git(["add", filename])
    repo.run_git(["commit", "-m", commit_msg])


def test_write_file_writes_text_content(local_environment: LocalEnvironment) -> None:
    """Test that write_file correctly writes text content."""
    file_path = str(local_environment.get_state_path() / "test.txt")
    local_environment.write_file(path=file_path, content="hello world")

    host_path = local_environment.to_host_path(Path("/" + file_path.lstrip("/")))
    assert host_path.read_text() == "hello world"


def test_write_file_writes_bytes_content(local_environment: LocalEnvironment) -> None:
    """Test that write_file correctly writes binary content (e.g. images)."""
    # Simulate a PNG file header as binary content
    binary_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    file_path = str(local_environment.get_attachments_path() / "test_image.png")
    local_environment.write_file(path=file_path, content=binary_content, mode="wb")

    host_path = local_environment.to_host_path(Path("/" + file_path.lstrip("/")))
    assert host_path.read_bytes() == binary_content


def test_write_file_raises_type_error_when_bytes_content_with_text_mode(local_environment: LocalEnvironment) -> None:
    """Test that write_file raises TypeError when bytes content is passed with text mode."""
    binary_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    file_path = str(local_environment.get_attachments_path() / "should_fail.png")

    with pytest.raises(TypeError, match="Cannot write bytes content with text mode"):
        local_environment.write_file(path=file_path, content=binary_content)


def _collect_stdout(environment: LocalEnvironment, command: list[str]) -> str:
    """Run a command in the environment and return all stdout as a single string."""
    process = environment.run_process_in_background(command, secrets={})
    queue = process.get_queue()
    lines: list[str] = []
    while not process.is_finished() or not queue.empty():
        try:
            line, is_stdout = queue.get(timeout=0.1)
        except Empty:
            continue
        if is_stdout:
            lines.append(line)
    return "".join(lines)


def test_project_env_vars_available_in_process(clone_test_ctx: CloneTestContext) -> None:
    """Project env vars from .sculptor/.env should be available in spawned processes."""
    env_dir = clone_test_ctx.source_repo_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("SCTEST_PROJ_VAR=hello_from_env\n")

    env = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(clone_test_ctx.workspace_dir)),
        project_id=ProjectID(),
        concurrency_group=clone_test_ctx.concurrency_group,
        repo_host_path=clone_test_ctx.source_repo_path,
        initialization_strategy=WorkspaceInitializationStrategy.CLONE,
        sculptor_folder=clone_test_ctx.sculptor_folder,
    )

    output = _collect_stdout(env, ["printenv", "SCTEST_PROJ_VAR"])
    assert "hello_from_env" in output


def test_env_var_override_false_preserves_existing(
    local_environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With env_var_override=False (default), existing os.environ values take precedence."""
    monkeypatch.setenv("SCTEST_EXISTING", "original")
    env_file = local_environment.get_working_directory() / ".sculptor" / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("SCTEST_EXISTING=should_not_win\n")
    local_environment._sculptor_folder = tmp_path
    local_environment._env_var_override = False

    output = _collect_stdout(local_environment, ["printenv", "SCTEST_EXISTING"])
    assert "original" in output


def test_env_var_override_true_overrides_existing(
    local_environment: LocalEnvironment, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """With env_var_override=True, project env vars override existing os.environ values."""
    monkeypatch.setenv("SCTEST_OVERRIDE", "old_value")
    env_file = local_environment.get_working_directory() / ".sculptor" / ".env"
    env_file.parent.mkdir(parents=True, exist_ok=True)
    env_file.write_text("SCTEST_OVERRIDE=new_value\n")
    local_environment._sculptor_folder = tmp_path
    local_environment._env_var_override = True

    output = _collect_stdout(local_environment, ["printenv", "SCTEST_OVERRIDE"])
    assert "new_value" in output


def test_get_system_prompt_dispatches_on_initialization_strategy(local_environment: LocalEnvironment) -> None:
    """get_system_prompt returns a distinct <Environment mode> block for each strategy."""
    local_environment.initialization_strategy = WorkspaceInitializationStrategy.IN_PLACE
    in_place_prompt = local_environment.get_system_prompt()
    assert in_place_prompt is not None and "in-place mode" in in_place_prompt

    local_environment.initialization_strategy = WorkspaceInitializationStrategy.CLONE
    clone_prompt = local_environment.get_system_prompt()
    assert clone_prompt is not None and "clone mode" in clone_prompt

    local_environment.initialization_strategy = WorkspaceInitializationStrategy.WORKTREE
    worktree_prompt = local_environment.get_system_prompt()
    assert worktree_prompt is not None
    assert "worktree mode" in worktree_prompt
    assert "`.git`" in worktree_prompt
    assert "local` remote" in worktree_prompt
    assert "NEVER" in worktree_prompt


def test_create_worktree_happy_path(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    """LocalEnvironment.create with WORKTREE mode runs git worktree add and returns the environment."""
    user_repo_path = tmp_path / "user_repo"
    make_test_repo(user_repo_path)
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    try:
        env = LocalEnvironment.create(
            environment_id=LocalEnvironmentID(str(workspace_dir)),
            project_id=ProjectID(),
            concurrency_group=test_root_concurrency_group,
            repo_host_path=user_repo_path,
            initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
            source_branch="main",
            requested_branch_name="feat/x",
        )

        working_dir = env.get_working_directory()
        assert working_dir == workspace_dir / "code"
        assert (working_dir / ".git").exists()
        basename = working_dir.name
        assert (user_repo_path / ".git" / "worktrees" / basename).exists()
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def test_create_worktree_missing_branch_name_raises(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo_path = tmp_path / "user_repo"
    make_test_repo(user_repo_path)
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    try:
        with pytest.raises(ValueError, match="requested_branch_name is required"):
            LocalEnvironment.create(
                environment_id=LocalEnvironmentID(str(workspace_dir)),
                project_id=ProjectID(),
                concurrency_group=test_root_concurrency_group,
                repo_host_path=user_repo_path,
                initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
                source_branch="main",
                requested_branch_name=None,
            )
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def test_create_worktree_missing_source_branch_raises(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    user_repo_path = tmp_path / "user_repo"
    make_test_repo(user_repo_path)
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    try:
        with pytest.raises(ValueError, match="source_branch"):
            LocalEnvironment.create(
                environment_id=LocalEnvironmentID(str(workspace_dir)),
                project_id=ProjectID(),
                concurrency_group=test_root_concurrency_group,
                repo_host_path=user_repo_path,
                initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
                source_branch=None,
                requested_branch_name="feat/x",
            )
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)


def test_create_worktree_branch_exists_raises(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    user_repo_path = tmp_path / "user_repo"
    make_test_repo(user_repo_path)
    LocalGitRepo(user_repo_path).run_git(["branch", "feat/x"])
    workspace_dir = LOCAL_WORKSPACE_DIR / uuid4().hex
    try:
        with expect_exact_logged_errors(["{}: {}"]):
            with pytest.raises(WorktreeError):
                LocalEnvironment.create(
                    environment_id=LocalEnvironmentID(str(workspace_dir)),
                    project_id=ProjectID(),
                    concurrency_group=test_root_concurrency_group,
                    repo_host_path=user_repo_path,
                    initialization_strategy=WorkspaceInitializationStrategy.WORKTREE,
                    source_branch="main",
                    requested_branch_name="feat/x",
                )
    finally:
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir, ignore_errors=True)
