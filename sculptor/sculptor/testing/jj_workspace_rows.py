"""A jj workspace row for tests of services that read a workspace from the database.

The workspace service's create path writes only the row; an environment builds
the checkout when an agent starts. Here jj's seam builds it directly, at
`<environment_path>/code`, so a test needs no environment.
"""

from pathlib import Path

from sculptor.database.models import Workspace
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.primitives.constants import ANONYMOUS_ORGANIZATION_REFERENCE
from sculptor.primitives.ids import RequestID
from sculptor.services.data_model_service.api import DataModelService
from sculptor.services.project_service.api import ProjectService
from sculptor.services.workspace_service.api import WorkspaceService
from sculptor.services.workspace_service.vcs.data_types import CheckoutSpec
from sculptor.testing.jj_repos import JjColocatedRepo


def create_jj_workspace_row(
    data_model_service: DataModelService,
    project_service: ProjectService,
    workspace_service: WorkspaceService,
    repo: JjColocatedRepo,
    environment_path: Path,
    requested_bookmark: str,
) -> Workspace:
    """A jj workspace of `repo` targeting its default bookmark on origin, with its checkout built."""
    target = f"{repo.default_bookmark}@origin"
    with data_model_service.open_transaction(RequestID()) as transaction:
        project = project_service.initialize_project(
            project_path=repo.path, organization_reference=ANONYMOUS_ORGANIZATION_REFERENCE, transaction=transaction
        )
        assert project is not None
        workspace = workspace_service.create_workspace(
            project=project,
            initialization_strategy=WorkspaceInitializationStrategy.JJ_WORKSPACE,
            source_branch=target,
            requested_branch_name=requested_bookmark,
            description="jj workspace",
            transaction=transaction,
            target_branch=target,
        )
        updated = transaction.update_workspace_fields(workspace.object_id, environment_id=str(environment_path))
        assert updated is not None
    workspace_service.get_workspace_vcs(WorkspaceInitializationStrategy.JJ_WORKSPACE).create_checkout(
        CheckoutSpec(
            repo_path=repo.path,
            checkout_path=environment_path / "code",
            base_ref=target,
            new_ref_name=requested_bookmark,
            checkout_name=str(workspace.object_id),
        )
    )
    return updated
