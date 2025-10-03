from pathlib import Path
from typing import Generator

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from loguru import logger

from sculptor.config.settings import SculptorSettings
from sculptor.database.models import Project
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.service_collections.service_collection import get_services
from sculptor.testing.resources import test_repo_factory_  # noqa: F401
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.web.app import APP
from sculptor.web.auth import UserSession
from sculptor.web.auth import authenticate
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.auth import create_test_token
from sculptor.web.middleware import get_settings
from sculptor.web.middleware import services_factory

TEST_USER_EMAIL = "test@imbue.com"
TEST_ORGANIZATION_REFERENCE = "authentik-organization-id"
TEST_PRIVATE_KEY_PATH = Path(__file__).parent.parent.parent / "keys" / "private_test.pem"


@pytest.fixture
def test_services(test_settings: SculptorSettings) -> Generator[CompleteServiceCollection, None, None]:
    services = get_services(test_settings)
    services.task_service.is_spawner_suppressed = True
    services.start_all()
    try:
        yield services
    finally:
        services.stop_all()


@pytest.fixture
def client(test_settings: SculptorSettings, test_services: CompleteServiceCollection):
    def override_get_settings() -> SculptorSettings:
        return test_settings

    def override_services_factory(settings: SculptorSettings = Depends(get_settings)) -> CompleteServiceCollection:
        return test_services

    APP.dependency_overrides[get_settings] = override_get_settings
    APP.dependency_overrides[services_factory] = override_services_factory
    yield TestClient(APP)
    APP.dependency_overrides.clear()


@pytest.fixture
def client_with_auth(test_settings: SculptorSettings, test_services: CompleteServiceCollection):
    def override_get_settings() -> SculptorSettings:
        return test_settings.model_copy(update={"ALLOW_ANONYMOUS_USERS": False})

    def override_services_factory(settings: SculptorSettings = Depends(get_settings)) -> CompleteServiceCollection:
        return test_services

    APP.dependency_overrides[get_settings] = override_get_settings
    APP.dependency_overrides[services_factory] = override_services_factory
    yield TestClient(APP)
    APP.dependency_overrides.clear()


@pytest.fixture
def client_with_app_secret_required(test_settings: SculptorSettings, test_services: CompleteServiceCollection):
    def override_get_settings() -> SculptorSettings:
        return test_settings.model_copy(update={"ELECTRON_APP_SECRET": "test_secret"})

    def override_services_factory(settings: SculptorSettings = Depends(get_settings)) -> CompleteServiceCollection:
        return test_services

    APP.dependency_overrides[get_settings] = override_get_settings
    APP.dependency_overrides[services_factory] = override_services_factory
    yield TestClient(APP)
    APP.dependency_overrides.clear()


@pytest.fixture
def test_auth_headers() -> dict[str, str]:
    token = create_test_token(TEST_USER_EMAIL, TEST_ORGANIZATION_REFERENCE, private_key_path=TEST_PRIVATE_KEY_PATH)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def test_user_session(test_services, test_settings, test_auth_headers) -> UserSession:
    user_session = authenticate(test_auth_headers["Authorization"].split()[1], test_services, request_id=RequestID())
    return user_session


@pytest.fixture
def test_project(
    test_settings: SculptorSettings, test_repo_factory_: TestRepoFactory, test_services: CompleteServiceCollection
) -> Project:
    project_repo = test_repo_factory_.create_repo("project-repo", "main")
    project_path = project_repo.repo.base_path
    logger.info("using project path: {}", project_path)
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        project = test_services.project_service.initialize_project(
            project_path=project_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
        test_services.project_service.activate_project(project)
    assert project is not None, "By now, the project should be initialized."
    return project
