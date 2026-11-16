"""The routes that report the dependency status or make the backend compute a new one."""

from pathlib import Path
from queue import Queue

import pytest
from fastapi.testclient import TestClient

import sculptor.services.user_config.user_config as user_config_module
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.testing.recording_binaries import RecordingBinaries
from sculptor.testing.recording_binaries import recording_git_and_jj  # noqa: F401
from sculptor.web.data_types import DependenciesStatus
from sculptor.web.data_types import HealthCheckResponse


def _observe_dependency_status(services: CompleteServiceCollection) -> Queue[DependenciesStatus]:
    """A queue registered as an open window's would be, emptied of the status it receives on registering."""
    queue: Queue[DependenciesStatus] = Queue()
    services.dependency_management_service.add_observer_queue(queue)
    while not queue.empty():
        queue.get_nowait()
    return queue


def test_health_checks_before_any_dependency_status_is_computed_report_none_and_run_no_tool(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    client: TestClient,
) -> None:
    responses = [client.get("/api/v1/health") for _ in range(3)]

    assert [response.status_code for response in responses] == [200, 200, 200]
    assert [HealthCheckResponse.model_validate(response.json()).dependencies_status for response in responses] == [
        None,
        None,
        None,
    ]
    assert recording_git_and_jj.read_runs() == []


def test_health_checks_report_the_last_computed_dependency_status_and_run_no_tool(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    client: TestClient,
    test_services: CompleteServiceCollection,
) -> None:
    status = test_services.dependency_management_service.refresh_status()
    recording_git_and_jj.forget_runs()

    responses = [client.get("/api/v1/health") for _ in range(3)]

    assert [HealthCheckResponse.model_validate(response.json()).dependencies_status for response in responses] == [
        status,
        status,
        status,
    ]
    assert recording_git_and_jj.read_runs() == []


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


def test_re_checking_the_dependencies_asks_the_login_shell_again_where_a_refresh_does_not(
    recording_git_and_jj: RecordingBinaries,  # noqa: F811
    jj_isolated_env: JjIsolatedEnv,
    client: TestClient,
    test_services: CompleteServiceCollection,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile_runs_log = jj_isolated_env.home_path / "profile_runs.log"
    monkeypatch.setenv("SHELL", "/bin/bash")
    (jj_isolated_env.home_path / ".bash_profile").write_text(f'echo ran >> "{profile_runs_log}"\n')
    test_services.dependency_management_service.get_status()
    test_services.dependency_management_service.refresh_status()
    runs_before_the_re_check = profile_runs_log.read_text().splitlines()

    response = client.get("/api/v1/config/dependencies")

    assert response.status_code == 200, response.text
    assert runs_before_the_re_check == ["ran"]
    assert profile_runs_log.read_text().splitlines() == ["ran", "ran"]
