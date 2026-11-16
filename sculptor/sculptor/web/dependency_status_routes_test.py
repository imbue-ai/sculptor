"""The routes that report the dependency status or make the backend compute a new one."""

from pathlib import Path
from queue import Queue

import pytest
from fastapi.testclient import TestClient

import sculptor.services.user_config.user_config as user_config_module
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.recording_binaries import RecordingBinaries
from sculptor.testing.recording_binaries import recording_git_and_jj  # noqa: F401
from sculptor.web.data_types import DependenciesStatus


def _observe_dependency_status(services: CompleteServiceCollection) -> Queue[DependenciesStatus]:
    """A queue registered as an open window's would be, emptied of the status it receives on registering."""
    queue: Queue[DependenciesStatus] = Queue()
    services.dependency_management_service.add_observer_queue(queue)
    while not queue.empty():
        queue.get_nowait()
    return queue


def test_re_checking_the_dependencies_finds_a_jj_installed_since_the_status_was_computed_and_tells_every_window(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    jj_binary: JjBinary,
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    (recording_git_and_jj.bin_dir / "jj").unlink()
    assert test_services.dependency_management_service.get_status().jj.installed is False
    recording_git_and_jj.add("jj", jj_binary.path)
    window = _observe_dependency_status(test_services)

    response = client.get("/api/v1/config/dependencies")

    assert response.status_code == 200, response.text
    status = DependenciesStatus.model_validate(response.json())
    assert status.jj.installed is True
    assert window.get(timeout=5.0) == status


def test_changing_the_dependency_paths_tells_every_window_the_fresh_status(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    jj_binary: JjBinary,
    client: TestClient,
    test_services: CompleteServiceCollection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    assert test_services.dependency_management_service.get_status().jj.path == str(recording_git_and_jj.bin_dir / "jj")
    window = _observe_dependency_status(test_services)

    response = client.put(
        "/api/v1/config",
        json={"userConfig": {"dependencyPaths": {"claude": "CUSTOM", "pi": "CUSTOM", "jj": str(jj_binary.path)}}},
    )

    assert response.status_code == 200, response.text
    assert window.get(timeout=5.0).jj.path == str(jj_binary.path)
