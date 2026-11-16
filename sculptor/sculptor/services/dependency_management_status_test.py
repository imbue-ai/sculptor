"""The dependency status the service keeps, and what makes it compute a new one.

Git and jj are wrappers that record each run before running the real tool, on a
PATH that holds nothing else, so a test can tell when a read ran a probe.
"""

from collections.abc import Iterator
from pathlib import Path
from queue import Queue

import pytest

import sculptor.services.dependency_management_service as dependency_management_service_module
from sculptor.config.user_config import DependencyPaths
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.interfaces.environments.agent_execution_environment import Dependency
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.user_config.user_config import get_user_config_instance
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.recording_binaries import RecordingBinaries
from sculptor.testing.recording_binaries import recording_git_and_jj  # noqa: F401
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled


@pytest.fixture
def service() -> Iterator[DependencyManagementService]:
    with ConcurrencyGroup(name="dependency_management_service") as concurrency_group:
        yield DependencyManagementService(concurrency_group=concurrency_group)


def _unstarted_service() -> DependencyManagementService:
    return DependencyManagementService(concurrency_group=ConcurrencyGroup(name="dependency_management_service"))


def _drain(queue: Queue[DependenciesStatus]) -> list[DependenciesStatus]:
    statuses: list[DependenciesStatus] = []
    while not queue.empty():
        statuses.append(queue.get_nowait())
    return statuses


def test_reading_the_status_again_runs_no_probe(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    service: DependencyManagementService,
) -> None:
    first_status = service.get_status()
    assert recording_git_and_jj.read_runs() != []
    recording_git_and_jj.forget_runs()

    statuses = [service.get_status(), service.get_status()]
    jj_readiness = service.get_jj_readiness()

    assert recording_git_and_jj.read_runs() == []
    assert statuses == [first_status, first_status]
    assert jj_readiness == first_status.jj_readiness


def test_refreshing_the_status_finds_a_jj_installed_since_it_was_last_computed(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    jj_binary: JjBinary,
    service: DependencyManagementService,
) -> None:
    (recording_git_and_jj.bin_dir / "jj").unlink()
    assert service.get_status().jj.installed is False
    recording_git_and_jj.add("jj", jj_binary.path)

    status_before_refresh = service.get_status()
    refreshed_status = service.refresh_status()

    assert status_before_refresh.jj.installed is False
    assert refreshed_status.jj.installed is True
    assert service.get_status() == refreshed_status


def test_refreshing_the_status_pushes_it_to_every_observer(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    service: DependencyManagementService,
) -> None:
    queues: list[Queue[DependenciesStatus]] = [Queue(), Queue()]
    for queue in queues:
        service.add_observer_queue(queue)

    status = service.refresh_status()

    assert [_drain(queue) for queue in queues] == [[status], [status]]


def test_an_observer_receives_the_last_computed_status_when_it_registers(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    service: DependencyManagementService,
) -> None:
    early_queue: Queue[DependenciesStatus] = Queue()
    service.add_observer_queue(early_queue)
    status = service.get_status()
    late_queue: Queue[DependenciesStatus] = Queue()

    service.add_observer_queue(late_queue)

    assert (_drain(early_queue), _drain(late_queue)) == ([status], [status])


def test_probing_jj_readiness_finds_an_identity_removed_since_the_status_was_computed(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert service.get_status().jj_readiness == JjAvailable(
        blocker=None, identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL)
    )
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")

    stored_readiness = service.get_jj_readiness()
    probed_readiness = service.probe_jj_readiness()

    assert isinstance(stored_readiness, JjAvailable)
    assert probed_readiness == JjNoIdentity(
        blocker=JjBlocker.NO_IDENTITY,
        suggested_identity=JjIdentity(name=JJ_TEST_USER_NAME, email=JJ_TEST_USER_EMAIL),
    )


def test_reading_jj_readiness_before_any_status_is_computed_runs_only_jj_and_stores_nothing(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    service: DependencyManagementService,
) -> None:
    readiness = service.get_jj_readiness()

    assert isinstance(readiness, JjAvailable)
    assert [run.split()[0] for run in recording_git_and_jj.read_runs()] == ["jj", "jj"]
    assert service.get_last_computed_status() is None


def test_a_running_service_refreshes_the_status_on_a_slow_timer_with_no_one_asking(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependency_management_service_module, "_DEPENDENCY_STATUS_REFRESH_INTERVAL_SECONDS", 0.05)
    service = _unstarted_service()
    queue: Queue[DependenciesStatus] = Queue()
    service.add_observer_queue(queue)

    with service.run():
        first_status = queue.get(timeout=10.0)
        second_status = queue.get(timeout=10.0)

    assert first_status.jj.installed is True
    assert second_status == first_status


def test_a_running_service_refreshes_the_status_soon_after_jj_resolves_to_nothing(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
) -> None:
    service = _unstarted_service()
    with service.run():
        assert service.get_status().jj.installed is True
        queue: Queue[DependenciesStatus] = Queue()
        service.add_observer_queue(queue)
        _drain(queue)
        (recording_git_and_jj.bin_dir / "jj").unlink()

        assert service.resolve_binary_path(Dependency.JJ) is None
        refreshed_status = queue.get(timeout=10.0)

    assert refreshed_status.jj_readiness == JjNotInstalled(blocker=JjBlocker.NOT_INSTALLED)


def test_a_running_service_refreshes_the_status_soon_after_a_gate_finds_jj_changed(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = _unstarted_service()
    with service.run():
        assert isinstance(service.get_status().jj_readiness, JjAvailable)
        queue: Queue[DependenciesStatus] = Queue()
        service.add_observer_queue(queue)
        _drain(queue)
        monkeypatch.delenv("JJ_USER")
        monkeypatch.delenv("JJ_EMAIL")

        probed_readiness = service.probe_jj_readiness()
        refreshed_status = queue.get(timeout=10.0)

    assert refreshed_status.jj_readiness == probed_readiness
    assert isinstance(probed_readiness, JjNoIdentity)


def _log_each_login_shell_run(jj_isolated_env: JjIsolatedEnv, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Make the user's login shell bash, with a profile that logs each run to the returned file."""
    runs_log = jj_isolated_env.home_path / "profile_runs.log"
    runs_log.touch()
    monkeypatch.setenv("SHELL", "/bin/bash")
    (jj_isolated_env.home_path / ".bash_profile").write_text(f'echo ran >> "{runs_log}"\n')
    return runs_log


def test_timed_refreshes_keep_the_login_shells_last_answer_and_a_re_check_asks_it_again(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    jj_isolated_env: JjIsolatedEnv,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependency_management_service_module, "_DEPENDENCY_STATUS_REFRESH_INTERVAL_SECONDS", 0.05)
    profile_runs_log = _log_each_login_shell_run(jj_isolated_env, monkeypatch)
    service = _unstarted_service()
    queue: Queue[DependenciesStatus] = Queue()
    service.add_observer_queue(queue)

    with service.run():
        timed_statuses = [queue.get(timeout=10.0) for _ in range(4)]
        runs_after_the_timed_refreshes = profile_runs_log.read_text().splitlines()
        service.recheck_status()
        runs_after_the_re_check = profile_runs_log.read_text().splitlines()

    assert [isinstance(status.jj_readiness, JjAvailable) for status in timed_statuses] == [True, True, True, True]
    assert runs_after_the_timed_refreshes == ["ran"]
    assert runs_after_the_re_check == ["ran", "ran"]


def test_a_refresh_asks_the_login_shell_again_when_the_jj_sculptor_resolves_moves(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    jj_binary: JjBinary,
    jj_isolated_env: JjIsolatedEnv,
    service: DependencyManagementService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_runs_log = _log_each_login_shell_run(jj_isolated_env, monkeypatch)
    service.get_status()
    service.refresh_status()
    runs_before_the_move = profile_runs_log.read_text().splitlines()
    set_user_config_instance(
        get_user_config_instance().model_copy(
            update={"dependency_paths": DependencyPaths(claude="CUSTOM", pi="CUSTOM", jj=str(jj_binary.path))}
        )
    )

    status = service.refresh_status()

    assert status.jj.path == str(jj_binary.path)
    assert runs_before_the_move == ["ran"]
    assert profile_runs_log.read_text().splitlines() == ["ran", "ran"]
