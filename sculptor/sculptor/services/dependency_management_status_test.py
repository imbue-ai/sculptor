"""The dependency status the service keeps, and what makes it compute a new one.

Git and jj are wrappers that record each run before running the real tool, on a
PATH that holds nothing else, so a test can tell when a read ran a probe.
"""

from collections.abc import Iterator
from queue import Queue

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.testing.jj_repos import JJ_TEST_USER_EMAIL
from sculptor.testing.jj_repos import JJ_TEST_USER_NAME
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.recording_binaries import RecordingBinaries
from sculptor.testing.recording_binaries import recording_git_and_jj  # noqa: F401
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjBlocker
from sculptor.web.data_types import JjIdentity
from sculptor.web.data_types import JjNoIdentity


@pytest.fixture
def service() -> Iterator[DependencyManagementService]:
    with ConcurrencyGroup(name="dependency_management_service") as concurrency_group:
        yield DependencyManagementService(concurrency_group=concurrency_group)


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
