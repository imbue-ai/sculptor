"""POST /api/v1/dependencies/jj/identity writes jj's author identity and returns fresh status."""

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from sculptor.config.user_config import DependencyPaths
from sculptor.config.user_config import UserConfig
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.jj_repos import JjBinary
from sculptor.testing.jj_repos import JjIsolatedEnv
from sculptor.utils.build import SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG
from sculptor.utils.build import get_sculptor_folder

_IDENTITY_ROUTE = "/api/v1/dependencies/jj/identity"


def _use_jj(jj_value: str) -> None:
    set_user_config_instance(
        UserConfig(
            user_email="test@example.com",
            user_id=uuid4().hex,
            organization_id=uuid4().hex,
            instance_id=uuid4().hex,
            dependency_paths=DependencyPaths(jj=jj_value),
        )
    )


@pytest.fixture
def jj_without_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, jj_isolated_env: JjIsolatedEnv, jj_binary: JjBinary
) -> Iterator[JjBinary]:
    monkeypatch.delenv("JJ_USER")
    monkeypatch.delenv("JJ_EMAIL")
    monkeypatch.setenv(SCULPTOR_FOLDER_OVERRIDE_ENV_FLAG, str(tmp_path))
    get_sculptor_folder.cache_clear()
    yield jj_binary
    get_sculptor_folder.cache_clear()
    set_user_config_instance(None)


def test_setting_the_jj_identity_makes_jj_available(jj_without_identity: JjBinary, client: TestClient) -> None:
    _use_jj(str(jj_without_identity.path))

    response = client.post(_IDENTITY_ROUTE, json={"name": "Grace Hopper", "email": "grace@example.com"})

    assert response.status_code == 200
    readiness = response.json()["jjReadiness"]
    assert readiness["blocker"] is None
    assert readiness["identity"] == {"name": "Grace Hopper", "email": "grace@example.com"}


def test_an_empty_jj_identity_is_rejected(jj_without_identity: JjBinary, client: TestClient) -> None:
    _use_jj(str(jj_without_identity.path))

    response = client.post(_IDENTITY_ROUTE, json={"name": "", "email": "grace@example.com"})

    assert response.status_code == 422


def test_setting_the_jj_identity_without_jj_is_a_conflict(jj_without_identity: JjBinary, client: TestClient) -> None:
    _use_jj("CUSTOM")

    response = client.post(_IDENTITY_ROUTE, json={"name": "Grace Hopper", "email": "grace@example.com"})

    assert response.status_code == 409
    assert response.json()["detail"] == "jj is not installed"
