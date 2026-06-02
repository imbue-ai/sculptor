from pathlib import Path
from typing import Generator

import pytest

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Project
from sculptor.database.models import ProjectID
from sculptor.primitives.ids import OrganizationReference
from sculptor.primitives.ids import RequestID
from sculptor.primitives.ids import UserReference
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.service_collections.service_collection import get_services
from sculptor.testing.repo_resources import generate_test_project_repo


@pytest.fixture
def test_service_collection(
    test_root_concurrency_group: ConcurrencyGroup,
    test_settings: SculptorSettings,
) -> Generator[CompleteServiceCollection, None, None]:
    services = get_services(test_root_concurrency_group, test_settings)
    with services.run_all():
        yield services


@pytest.fixture
def mock_repo_path(
    request: pytest.FixtureRequest, test_root_concurrency_group: ConcurrencyGroup
) -> Generator[Path, None, None]:
    with generate_test_project_repo(request, test_root_concurrency_group) as repo:
        yield repo.base_path


@pytest.fixture
def test_user_email() -> str:
    return "test@imbue.com"


@pytest.fixture
def test_user_org_project(
    test_service_collection: CompleteServiceCollection,
    mock_repo_path: Path,
    test_user_email: str,  # noqa: ARG001
) -> tuple[UserReference, OrganizationReference, Project]:
    with test_service_collection.data_model_service.open_transaction(RequestID()) as transaction:
        user_reference = UserReference("test_user")  # Using UserReference for consistency
        organization_reference = OrganizationReference(
            "test_organization"
        )  # Using OrganizationReference for consistency
        project_id = ProjectID()
        project = Project(
            object_id=project_id,
            name="Test Project",
            organization_reference=organization_reference,
            user_git_repo_url=f"file://{mock_repo_path}",
        )
        transaction.upsert_project(project)
        return user_reference, organization_reference, project


@pytest.fixture
def test_project(test_user_org_project: tuple[UserReference, OrganizationReference, Project]) -> Project:
    return test_user_org_project[2]
