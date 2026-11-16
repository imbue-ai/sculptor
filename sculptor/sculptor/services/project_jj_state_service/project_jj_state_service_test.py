import fcntl
import shutil
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from queue import Empty
from queue import Queue

import pytest

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.database.models import Project
from sculptor.foundation.processes.local_process import run_blocking
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.project_jj_state_service.project_jj_state_service import ColocationAlreadyRunningError
from sculptor.services.project_jj_state_service.project_jj_state_service import ColocationBlockedError
from sculptor.services.project_jj_state_service.project_jj_state_service import JjUnavailableForRepositoryError
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjColocatedRepo
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.jj_repos import run_jj
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import JjColocationBlocker
from sculptor.web.data_types import JjColocationState
from sculptor.web.data_types import ProjectJjState
from sculptor.web.data_types import StreamingUpdateSourceTypes

_STATE_TIMEOUT_SECONDS = 30.0


@pytest.fixture
def services(test_service_collection: CompleteServiceCollection) -> CompleteServiceCollection:
    return test_service_collection


@pytest.fixture
def published_states(services: CompleteServiceCollection) -> Iterator[Queue[StreamingUpdateSourceTypes]]:
    queue: Queue[StreamingUpdateSourceTypes] = Queue()
    services.project_jj_state_service.add_observer(queue)
    yield queue
    services.project_jj_state_service.remove_observer(queue)


@pytest.fixture
def git_repo(jj_isolated_env: JjIsolatedEnv, tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_blocking(["git", "init", "-q", "-b", "main"], cwd=repo)
    (repo / "file.txt").write_text("first\n")
    run_blocking(["git", "add", "file.txt"], cwd=repo)
    run_blocking(["git", "commit", "-q", "-m", "init"], cwd=repo)
    return repo


def _resolve_jj_to(silly_global_config: UserConfig, jj_value: str) -> None:
    set_user_config_instance(silly_global_config.model_copy(update={"dependency_paths": DependencyPaths(jj=jj_value)}))


@pytest.fixture
def jj_available(silly_global_config: UserConfig, jj_binary: JjBinary) -> None:
    _resolve_jj_to(silly_global_config, str(jj_binary.path))


def _register_project(services: CompleteServiceCollection, repo_path: Path) -> Project:
    user_session = authenticate_anonymous(services, RequestID())
    with user_session.open_transaction(services) as transaction:
        project = services.project_service.initialize_project(
            project_path=repo_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
    services.project_service.activate_project(project)
    return project


def _set_use_jj_for_new_workspaces(services: CompleteServiceCollection, project: Project, value: bool) -> Project:
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        updated = transaction.update_project_fields(project.object_id, use_jj_for_new_workspaces=value)
    assert updated is not None
    services.project_service.activate_project(updated)
    return updated


def _read_use_jj_for_new_workspaces(services: CompleteServiceCollection, project: Project) -> bool:
    with services.data_model_service.open_transaction(RequestID()) as transaction:
        stored = transaction.get_project(project.object_id)
    assert stored is not None
    return stored.use_jj_for_new_workspaces


def _state(project: Project, colocation: JjColocationState, *, creates_jj_workspaces: bool = False) -> ProjectJjState:
    return ProjectJjState(
        project_id=project.object_id,
        colocation=colocation,
        colocation_error=None,
        creates_jj_workspaces=creates_jj_workspaces,
    )


def _wait_for_state(queue: Queue[StreamingUpdateSourceTypes], expected: ProjectJjState) -> None:
    deadline = time.monotonic() + _STATE_TIMEOUT_SECONDS
    seen: list[StreamingUpdateSourceTypes] = []
    while time.monotonic() < deadline:
        try:
            published = queue.get(timeout=max(deadline - time.monotonic(), 0.0))
        except Empty:
            break
        if published == expected:
            return
        seen.append(published)
    raise AssertionError(f"{expected} was never published; published instead: {seen}")


def _wait_for_colocation(
    queue: Queue[StreamingUpdateSourceTypes], project: Project, colocation: JjColocationState
) -> ProjectJjState:
    deadline = time.monotonic() + _STATE_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        published = queue.get(timeout=max(deadline - time.monotonic(), 0.0))
        if isinstance(published, ProjectJjState) and (published.project_id, published.colocation) == (
            project.object_id,
            colocation,
        ):
            return published
    raise AssertionError(f"{project.object_id} was never published as {colocation}")


def test_a_registered_git_repository_is_published_as_not_colocated(
    services: CompleteServiceCollection, published_states: Queue[StreamingUpdateSourceTypes], git_repo: Path
) -> None:
    project = _register_project(services, git_repo)

    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))


def test_a_colocated_repository_creates_jj_workspaces_exactly_while_the_flag_is_on(
    jj_available: None,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(services, jj_colocated_repo.path)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED))

    project = _set_use_jj_for_new_workspaces(services, project, True)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))

    _set_use_jj_for_new_workspaces(services, project, False)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED))


def test_a_new_observer_hears_the_current_state_of_each_repository_at_once(
    services: CompleteServiceCollection, published_states: Queue[StreamingUpdateSourceTypes], git_repo: Path
) -> None:
    project = _register_project(services, git_repo)
    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))
    late_observer: Queue[StreamingUpdateSourceTypes] = Queue()

    services.project_jj_state_service.add_observer(late_observer)

    try:
        assert late_observer.get_nowait() == _state(project, JjColocationState.ABSENT)
    finally:
        services.project_jj_state_service.remove_observer(late_observer)


def test_jj_becoming_available_republishes_a_repository_that_creates_jj_workspaces(
    silly_global_config: UserConfig,
    jj_binary: JjBinary,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    _resolve_jj_to(silly_global_config, "CUSTOM")
    project = _register_project(services, jj_colocated_repo.path)
    project = _set_use_jj_for_new_workspaces(services, project, True)
    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))

    _resolve_jj_to(silly_global_config, str(jj_binary.path))
    services.dependency_management_service.get_status()

    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))


def test_jj_becoming_unavailable_stops_a_repository_creating_jj_workspaces_but_keeps_its_flag(
    silly_global_config: UserConfig,
    jj_available: None,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(services, jj_colocated_repo.path)
    project = _set_use_jj_for_new_workspaces(services, project, True)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))

    _resolve_jj_to(silly_global_config, "CUSTOM")
    services.dependency_management_service.get_status()

    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))
    assert _read_use_jj_for_new_workspaces(services, project) is True


def test_a_colocation_deleted_from_disk_turns_the_flag_off_when_next_read(
    jj_available: None,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(services, jj_colocated_repo.path)
    project = _set_use_jj_for_new_workspaces(services, project, True)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))
    shutil.rmtree(jj_colocated_repo.path / ".jj")

    services.project_jj_state_service.refresh_project(project)

    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))
    assert _read_use_jj_for_new_workspaces(services, project) is False


def test_a_repository_missing_from_disk_keeps_its_flag(
    jj_available: None,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(services, jj_colocated_repo.path)
    project = _set_use_jj_for_new_workspaces(services, project, True)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))
    jj_colocated_repo.path.rename(jj_colocated_repo.path.with_name("unmounted"))

    services.project_jj_state_service.refresh_project(project)

    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))
    assert _read_use_jj_for_new_workspaces(services, project) is True


def _write_jj_wrapper(path: Path, jj_binary: JjBinary, on_init: str) -> Path:
    """A jj that runs the Python statements `on_init` before `jj git init`, and is the pinned jj otherwise."""
    path.write_text(
        f"#!{sys.executable} -I\n"
        + "import fcntl, os, sys\n"
        + 'if "init" in sys.argv[1:]:\n'
        + "".join(f"    {line}\n" for line in on_init.splitlines())
        + f"os.execv({str(jj_binary.path)!r}, [{str(jj_binary.path)!r}, *sys.argv[1:]])\n"
    )
    path.chmod(0o755)
    return path


def _read_git(repo: Path, args: tuple[str, ...]) -> str:
    return run_blocking(["git", *args], cwd=repo).stdout


def test_colocating_a_git_repository_keeps_its_branch_and_files_and_turns_the_flag_on(
    jj_available: None,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    git_repo: Path,
) -> None:
    (git_repo / "file.txt").write_text("edited\n")
    (git_repo / "notes.txt").write_text("notes\n")
    head_before = _read_git(git_repo, ("rev-parse", "HEAD"))
    project = _register_project(services, git_repo)
    _wait_for_state(published_states, _state(project, JjColocationState.ABSENT))

    services.project_jj_state_service.start_colocation(project)

    _wait_for_state(published_states, _state(project, JjColocationState.INITIALIZING))
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))
    assert _read_use_jj_for_new_workspaces(services, project) is True
    assert _read_git(git_repo, ("symbolic-ref", "--short", "HEAD")).strip() == "main"
    assert _read_git(git_repo, ("rev-parse", "HEAD")) == head_before
    assert ((git_repo / "file.txt").read_text(), (git_repo / "notes.txt").read_text()) == ("edited\n", "notes\n")


def test_colocating_an_already_colocated_repository_only_turns_the_flag_on(
    jj_available: None,
    jj_binary: JjBinary,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    jj_colocated_repo: JjColocatedRepo,
) -> None:
    project = _register_project(services, jj_colocated_repo.path)
    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED))
    operations_before = run_jj(jj_binary, ("--ignore-working-copy", "op", "log", "-T", "id"), jj_colocated_repo.path)

    services.project_jj_state_service.start_colocation(project)

    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))
    assert run_jj(jj_binary, ("--ignore-working-copy", "op", "log", "-T", "id"), jj_colocated_repo.path) == (
        operations_before
    )


def test_colocating_is_refused_while_jj_is_unavailable(
    silly_global_config: UserConfig, services: CompleteServiceCollection, git_repo: Path
) -> None:
    _resolve_jj_to(silly_global_config, "CUSTOM")
    project = _register_project(services, git_repo)

    with pytest.raises(JjUnavailableForRepositoryError):
        services.project_jj_state_service.start_colocation(project)

    assert not (git_repo / ".jj").exists()


def test_colocating_a_repository_with_a_blocker_is_refused_with_the_blockers(
    jj_available: None, services: CompleteServiceCollection, git_repo: Path
) -> None:
    (git_repo / ".gitmodules").write_text('[submodule "vendor"]\n\tpath = vendor\n\turl = ../vendor\n')
    project = _register_project(services, git_repo)

    with pytest.raises(ColocationBlockedError) as raised:
        services.project_jj_state_service.start_colocation(project)

    assert raised.value.blockers == (JjColocationBlocker.SUBMODULES,)
    assert not (git_repo / ".jj").exists()


def test_a_second_colocation_is_refused_while_the_first_runs(
    silly_global_config: UserConfig,
    jj_binary: JjBinary,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    git_repo: Path,
    tmp_path: Path,
) -> None:
    init_lock = tmp_path / "init.lock"
    init_lock.touch()
    wrapper = _write_jj_wrapper(tmp_path / "jj", jj_binary, f"fcntl.flock(open({str(init_lock)!r}), fcntl.LOCK_EX)")
    _resolve_jj_to(silly_global_config, str(wrapper))
    project = _register_project(services, git_repo)

    with open(init_lock) as held_lock:
        fcntl.flock(held_lock, fcntl.LOCK_EX)
        services.project_jj_state_service.start_colocation(project)
        _wait_for_state(published_states, _state(project, JjColocationState.INITIALIZING))

        with pytest.raises(ColocationAlreadyRunningError):
            services.project_jj_state_service.start_colocation(project)

    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))


def test_a_failed_colocation_is_published_with_jj_s_error_and_can_be_retried(
    silly_global_config: UserConfig,
    jj_binary: JjBinary,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    git_repo: Path,
    tmp_path: Path,
) -> None:
    wrapper = _write_jj_wrapper(tmp_path / "jj", jj_binary, 'sys.stderr.write("Error: disk full\\n")\nsys.exit(1)')
    _resolve_jj_to(silly_global_config, str(wrapper))
    project = _register_project(services, git_repo)

    services.project_jj_state_service.start_colocation(project)

    _wait_for_state(
        published_states,
        ProjectJjState(
            project_id=project.object_id,
            colocation=JjColocationState.FAILED,
            colocation_error="Error: disk full",
            creates_jj_workspaces=False,
        ),
    )
    assert _read_use_jj_for_new_workspaces(services, project) is False

    _resolve_jj_to(silly_global_config, str(jj_binary.path))
    services.project_jj_state_service.start_colocation(project)

    _wait_for_state(published_states, _state(project, JjColocationState.COLOCATED, creates_jj_workspaces=True))


def test_a_colocation_jj_does_not_then_read_as_colocated_fails(
    silly_global_config: UserConfig,
    jj_binary: JjBinary,
    services: CompleteServiceCollection,
    published_states: Queue[StreamingUpdateSourceTypes],
    git_repo: Path,
    tmp_path: Path,
) -> None:
    wrapper = _write_jj_wrapper(tmp_path / "jj", jj_binary, "sys.exit(0)")
    _resolve_jj_to(silly_global_config, str(wrapper))
    project = _register_project(services, git_repo)

    services.project_jj_state_service.start_colocation(project)

    failed = _wait_for_colocation(published_states, project, JjColocationState.FAILED)
    assert failed.colocation_error is not None
    assert "not colocated" in failed.colocation_error
    assert _read_use_jj_for_new_workspaces(services, project) is False
