from pathlib import Path

import pytest

from sculptor.database.models import Project
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import ProjectID
from sculptor.services.project_service.default_implementation import DefaultProjectService


@pytest.fixture
def _test_project_mounted_and_disconnected() -> Project:
    project_id = ProjectID()
    organization_reference = OrganizationReference("test_organization")
    mounted_path = Path.home() / "mnt" / "test_repo"
    project = Project(
        object_id=project_id,
        name="Test Project",
        organization_reference=organization_reference,
        user_git_repo_url=f"file://{mounted_path}",
    )
    return project


@pytest.mark.skip
def test_remote_project_filesystem_disconnected(
    _test_project_service: DefaultProjectService, _test_project_mounted_and_disconnected: Project
) -> None:
    try:
        _test_project_service._check_and_update_project_accessibility(_test_project_mounted_and_disconnected)
    except OSError as e:
        pytest.fail(f"Remote filesystem project raised an OSError: {e}")
    except Exception:
        pass


def _make_project() -> Project:
    return Project(
        object_id=ProjectID(),
        name="Test Project",
        organization_reference=OrganizationReference("test_organization"),
        user_git_repo_url=f"file://{Path.home() / 'repos' / 'test_repo'}",
    )


def test_activating_a_project_tells_each_activation_observer_about_it(
    _test_project_service: DefaultProjectService,
) -> None:
    first_observed: list[Project] = []
    second_observed: list[Project] = []
    _test_project_service.add_activation_observer(first_observed.append)
    _test_project_service.add_activation_observer(second_observed.append)
    project = _make_project()

    _test_project_service.activate_project(project)

    assert first_observed == [project]
    assert second_observed == [project]


def test_a_removed_activation_observer_hears_of_no_later_activation(
    _test_project_service: DefaultProjectService,
) -> None:
    observed: list[Project] = []
    _test_project_service.add_activation_observer(observed.append)
    _test_project_service.remove_activation_observer(observed.append)

    _test_project_service.activate_project(_make_project())

    assert observed == []
