from pathlib import Path

import pytest

from imbue_core.agents.data_types.ids import ProjectID
from sculptor.database.models import Project
from sculptor.primitives.ids import OrganizationReference
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
