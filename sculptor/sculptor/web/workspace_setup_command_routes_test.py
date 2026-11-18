from fastapi.testclient import TestClient

from sculptor.services.workspace_service.vcs.git_workspace_vcs import DEFAULT_GIT_WORKSPACE_SETUP_COMMAND
from sculptor.services.workspace_service.vcs.jj_workspace_vcs import DEFAULT_JJ_WORKSPACE_SETUP_COMMAND


def test_each_workspace_kind_s_default_setup_command_comes_from_its_version_control(client: TestClient) -> None:
    response = client.get("/api/v1/workspace_setup_command_defaults")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "defaultSetupCommandByInitializationStrategy": {
            "IN_PLACE": None,
            "CLONE": DEFAULT_GIT_WORKSPACE_SETUP_COMMAND,
            "WORKTREE": DEFAULT_GIT_WORKSPACE_SETUP_COMMAND,
            "JJ_WORKSPACE": DEFAULT_JJ_WORKSPACE_SETUP_COMMAND,
        }
    }
