"""Tests for the workspace-group API endpoints."""

from typing import Generator

import httpx
import pytest
from fastapi.testclient import TestClient
from loguru import logger

import sculptor.services.user_config.user_config as user_config_module
from sculptor.config.user_config import UserConfig
from sculptor.database.models import Project
from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.foundation.pydantic_serialization import model_dump
from sculptor.primitives.ids import RequestID
from sculptor.service_collections.service_collection import CompleteServiceCollection
from sculptor.services.data_model_service.data_types import DataModelTransaction
from sculptor.services.user_config.user_config import set_user_config_instance
from sculptor.testing.test_repo_factory import TestRepoFactory
from sculptor.web.auth import authenticate_anonymous
from sculptor.web.data_types import AddWorkspaceGroupMemberRequest
from sculptor.web.data_types import CreateWorkspaceGroupRequest
from sculptor.web.data_types import UpdateWorkspaceGroupRequest
from sculptor.web.data_types import WORKSPACE_GROUP_COLOR_PALETTE


def _make_user_config(enable_workspace_groups: bool) -> UserConfig:
    return UserConfig(
        user_email="alice@example.com",
        user_id="user_123",
        organization_id="org_123",
        instance_id="instance_123",
        enable_workspace_groups=enable_workspace_groups,
    )


@pytest.fixture
def workspace_groups_enabled(tmp_path, monkeypatch) -> Generator[UserConfig, None, None]:
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    config = _make_user_config(enable_workspace_groups=True)
    set_user_config_instance(config)
    yield config
    set_user_config_instance(None)


@pytest.fixture
def workspace_groups_disabled(tmp_path, monkeypatch) -> Generator[UserConfig, None, None]:
    monkeypatch.setattr(user_config_module, "_CONFIG_PATH", tmp_path / "config.toml")
    config = _make_user_config(enable_workspace_groups=False)
    set_user_config_instance(config)
    yield config
    set_user_config_instance(None)


@pytest.fixture
def second_test_project(
    test_repo_factory_: TestRepoFactory,
    test_services: CompleteServiceCollection,
) -> Project:
    project_repo = test_repo_factory_.create_repo("second-project-repo", "main")
    project_path = project_repo.repo.base_path
    logger.info("using second project path: {}", project_path)
    user_session = authenticate_anonymous(test_services, RequestID())
    with user_session.open_transaction(test_services) as transaction:
        project = test_services.project_service.initialize_project(
            project_path=project_path,
            organization_reference=user_session.organization_reference,
            transaction=transaction,
        )
        test_services.project_service.activate_project(project)
    assert project is not None
    return project


def _create_workspace(
    transaction: DataModelTransaction,
    services: CompleteServiceCollection,
    project: Project,
    description: str = "test workspace",
) -> Workspace:
    """Create an IN_PLACE workspace for testing."""
    return services.workspace_service.create_workspace(
        project=project,
        initialization_strategy=WorkspaceInitializationStrategy.IN_PLACE,
        source_branch=None,
        requested_branch_name=None,
        description=description,
        transaction=transaction,
    )


def _make_workspaces(services: CompleteServiceCollection, project: Project, count: int) -> list[Workspace]:
    user_session = authenticate_anonymous(services, RequestID())
    with user_session.open_transaction(services) as transaction:
        return [_create_workspace(transaction, services, project, description=f"ws {index}") for index in range(count)]


def _post_create_group(
    client: TestClient,
    project: Project,
    workspaces: list[Workspace],
    name: str | None = None,
    color: str | None = None,
    created_via_cli: bool = False,
) -> httpx.Response:
    return client.post(
        "/api/v1/workspace-groups",
        json=model_dump(
            CreateWorkspaceGroupRequest(
                project_id=str(project.object_id),
                workspace_ids=[str(workspace.object_id) for workspace in workspaces],
                name=name,
                color=color,
                created_via_cli=created_via_cli,
            ),
            is_camel_case=True,
        ),
    )


def _create_group(client: TestClient, project: Project, workspaces: list[Workspace], **kwargs) -> dict:
    response = _post_create_group(client, project, workspaces, **kwargs)
    assert response.status_code == 200, response.text
    return response.json()


def test_create_group_with_defaults_assigns_indexed_names_and_palette_colors(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 2)

    first = _create_group(client, test_project, [workspaces[0]])
    second = _create_group(client, test_project, [workspaces[1]])

    assert first["name"] == "Group 1"
    assert second["name"] == "Group 2"
    assert first["color"] == WORKSPACE_GROUP_COLOR_PALETTE[0].value
    assert second["color"] == WORKSPACE_GROUP_COLOR_PALETTE[1].value
    assert first["workspaceIds"] == [str(workspaces[0].object_id)]
    assert first["createdViaCli"] is False


def test_create_group_with_explicit_name_and_color(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)

    group = _create_group(client, test_project, [workspace], name="Fleet", color="crimson", created_via_cli=True)

    assert group["name"] == "Fleet"
    # Any Radix accent name is accepted, not just the curated palette.
    assert group["color"] == "crimson"
    assert group["createdViaCli"] is True


def test_default_name_skips_collision_with_existing_live_group(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 2)
    first = _create_group(client, test_project, [workspaces[0]])

    # Rename the first group onto the name the next default would pick.
    response = client.patch(
        f"/api/v1/workspace-groups/{first['objectId']}",
        json=model_dump(UpdateWorkspaceGroupRequest(name="Group 2"), is_camel_case=True),
    )
    assert response.status_code == 200, response.text

    second = _create_group(client, test_project, [workspaces[1]])
    assert second["name"] == "Group 3"


def test_default_color_cycles_by_live_group_count(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 3)
    first = _create_group(client, test_project, [workspaces[0]])
    _create_group(client, test_project, [workspaces[1]])

    # Ungrouping the first group drops the live count back to 1, so the next
    # group re-uses the palette's second slot rather than advancing to the third.
    response = client.delete(f"/api/v1/workspace-groups/{first['objectId']}")
    assert response.status_code == 200, response.text

    third = _create_group(client, test_project, [workspaces[2]])
    assert third["color"] == WORKSPACE_GROUP_COLOR_PALETTE[1].value


def test_create_group_requires_at_least_one_workspace(
    client: TestClient,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    response = client.post(
        "/api/v1/workspace-groups",
        json={"projectId": str(test_project.object_id), "workspaceIds": []},
    )
    assert response.status_code == 422, response.text


def test_create_group_rejects_workspace_from_another_project(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    second_test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (foreign_workspace,) = _make_workspaces(test_services, second_test_project, 1)

    response = _post_create_group(client, test_project, [foreign_workspace])
    assert response.status_code == 400, response.text
    assert "different project" in response.json()["detail"]


def test_add_member_rejects_workspace_from_another_project(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    second_test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)
    (foreign_workspace,) = _make_workspaces(test_services, second_test_project, 1)
    group = _create_group(client, test_project, [workspace])

    response = client.post(
        f"/api/v1/workspace-groups/{group['objectId']}/workspaces",
        json=model_dump(
            AddWorkspaceGroupMemberRequest(workspace_id=str(foreign_workspace.object_id)), is_camel_case=True
        ),
    )
    assert response.status_code == 400, response.text


def test_add_and_remove_member(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 2)
    group = _create_group(client, test_project, [workspaces[0]])

    response = client.post(
        f"/api/v1/workspace-groups/{group['objectId']}/workspaces",
        json=model_dump(AddWorkspaceGroupMemberRequest(workspace_id=str(workspaces[1].object_id)), is_camel_case=True),
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["workspaceIds"]) == {str(w.object_id) for w in workspaces}

    # Membership is visible on the workspace itself.
    workspace_response = client.get(f"/api/v1/workspaces/{workspaces[1].object_id}")
    assert workspace_response.json()["groupId"] == group["objectId"]

    response = client.delete(f"/api/v1/workspace-groups/{group['objectId']}/workspaces/{workspaces[1].object_id}")
    assert response.status_code == 200, response.text

    show = client.get(f"/api/v1/workspace-groups/{group['objectId']}")
    assert show.status_code == 200
    assert show.json()["workspaceIds"] == [str(workspaces[0].object_id)]
    workspace_response = client.get(f"/api/v1/workspaces/{workspaces[1].object_id}")
    assert workspace_response.json()["groupId"] is None


def test_removing_last_member_dissolves_group(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)
    group = _create_group(client, test_project, [workspace])

    response = client.delete(f"/api/v1/workspace-groups/{group['objectId']}/workspaces/{workspace.object_id}")
    assert response.status_code == 200, response.text

    assert client.get(f"/api/v1/workspace-groups/{group['objectId']}").status_code == 404
    # The workspace itself is untouched.
    assert client.get(f"/api/v1/workspaces/{workspace.object_id}").status_code == 200


def test_moving_last_member_to_another_group_dissolves_the_source(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 2)
    source = _create_group(client, test_project, [workspaces[0]])
    target = _create_group(client, test_project, [workspaces[1]])

    response = client.post(
        f"/api/v1/workspace-groups/{target['objectId']}/workspaces",
        json=model_dump(AddWorkspaceGroupMemberRequest(workspace_id=str(workspaces[0].object_id)), is_camel_case=True),
    )
    assert response.status_code == 200, response.text
    assert set(response.json()["workspaceIds"]) == {str(w.object_id) for w in workspaces}

    assert client.get(f"/api/v1/workspace-groups/{source['objectId']}").status_code == 404


def test_create_group_moves_workspaces_out_of_existing_groups(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)
    source = _create_group(client, test_project, [workspace])

    replacement = _create_group(client, test_project, [workspace])

    assert replacement["workspaceIds"] == [str(workspace.object_id)]
    assert client.get(f"/api/v1/workspace-groups/{source['objectId']}").status_code == 404


def test_ungroup_releases_members_without_deleting_workspaces(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 2)
    group = _create_group(client, test_project, workspaces)

    response = client.delete(f"/api/v1/workspace-groups/{group['objectId']}")
    assert response.status_code == 200, response.text

    assert client.get(f"/api/v1/workspace-groups/{group['objectId']}").status_code == 404
    for workspace in workspaces:
        workspace_response = client.get(f"/api/v1/workspaces/{workspace.object_id}")
        assert workspace_response.status_code == 200
        assert workspace_response.json()["groupId"] is None


def test_deleting_last_member_workspace_dissolves_group(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    workspaces = _make_workspaces(test_services, test_project, 2)
    group = _create_group(client, test_project, workspaces)

    response = client.delete(f"/api/v1/workspaces/{workspaces[0].object_id}")
    assert response.status_code == 200, response.text
    # One member remains, so the group survives.
    show = client.get(f"/api/v1/workspace-groups/{group['objectId']}")
    assert show.status_code == 200
    assert show.json()["workspaceIds"] == [str(workspaces[1].object_id)]

    response = client.delete(f"/api/v1/workspaces/{workspaces[1].object_id}")
    assert response.status_code == 200, response.text
    assert client.get(f"/api/v1/workspace-groups/{group['objectId']}").status_code == 404


def test_list_groups_filters_by_project_and_carries_palette(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    second_test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)
    (foreign_workspace,) = _make_workspaces(test_services, second_test_project, 1)
    group = _create_group(client, test_project, [workspace])
    foreign_group = _create_group(client, second_test_project, [foreign_workspace])

    response = client.get("/api/v1/workspace-groups", params={"project_id": str(test_project.object_id)})
    assert response.status_code == 200, response.text
    body = response.json()
    assert [g["objectId"] for g in body["groups"]] == [group["objectId"]]
    assert body["palette"] == [color.value for color in WORKSPACE_GROUP_COLOR_PALETTE]

    response = client.get("/api/v1/workspace-groups")
    assert response.status_code == 200, response.text
    assert {g["objectId"] for g in response.json()["groups"]} == {group["objectId"], foreign_group["objectId"]}


def test_patch_renames_and_recolors(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)
    group = _create_group(client, test_project, [workspace])

    response = client.patch(
        f"/api/v1/workspace-groups/{group['objectId']}",
        json=model_dump(UpdateWorkspaceGroupRequest(name="Stacked branches", color="teal"), is_camel_case=True),
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Stacked branches"
    assert response.json()["color"] == "teal"

    # Recolor alone leaves the name unchanged.
    response = client.patch(
        f"/api/v1/workspace-groups/{group['objectId']}",
        json=model_dump(UpdateWorkspaceGroupRequest(color="pink"), is_camel_case=True),
    )
    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Stacked branches"
    assert response.json()["color"] == "pink"


def test_patch_rejects_empty_name(
    client: TestClient,
    test_services: CompleteServiceCollection,
    test_project: Project,
    workspace_groups_enabled: UserConfig,
) -> None:
    (workspace,) = _make_workspaces(test_services, test_project, 1)
    group = _create_group(client, test_project, [workspace])

    response = client.patch(f"/api/v1/workspace-groups/{group['objectId']}", json={"name": "   "})
    assert response.status_code == 400, response.text


def test_show_returns_404_for_unknown_group(
    client: TestClient,
    workspace_groups_enabled: UserConfig,
) -> None:
    response = client.get("/api/v1/workspace-groups/wsg_00000000000000000000000000")
    assert response.status_code == 404, response.text


def test_every_group_endpoint_returns_409_when_flag_is_off(
    client: TestClient,
    test_project: Project,
    workspace_groups_disabled: UserConfig,
) -> None:
    group_path = "/api/v1/workspace-groups/wsg_00000000000000000000000000"
    requests = (
        ("POST", "/api/v1/workspace-groups", {"projectId": str(test_project.object_id), "workspaceIds": ["ws_1"]}),
        ("GET", "/api/v1/workspace-groups", None),
        ("GET", group_path, None),
        ("PATCH", group_path, {"name": "Renamed"}),
        ("POST", f"{group_path}/workspaces", {"workspaceId": "ws_1"}),
        ("DELETE", f"{group_path}/workspaces/ws_1", None),
        ("DELETE", group_path, None),
    )
    for method, path, body in requests:
        response = client.request(method, path, json=body)
        assert response.status_code == 409, f"{method} {path}: {response.status_code} {response.text}"
        assert response.json()["detail"]["error"] == "workspace_groups_disabled", f"{method} {path}"
