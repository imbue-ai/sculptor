"""The default setup command of each workspace kind; app.py includes the router."""

from fastapi import Depends
from fastapi import Request

from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.services.workspace_service.vcs.checkout_layout import is_isolated_checkout
from sculptor.web.auth import UserSession
from sculptor.web.data_types import WorkspaceSetupCommandDefaults
from sculptor.web.middleware import DecoratedAPIRouter
from sculptor.web.middleware import add_logging_context
from sculptor.web.middleware import get_services_from_request_or_websocket
from sculptor.web.middleware import get_user_session

workspace_setup_command_router = DecoratedAPIRouter(decorator=add_logging_context)


@workspace_setup_command_router.get("/api/v1/workspace_setup_command_defaults")
def get_workspace_setup_command_defaults(
    request: Request,
    user_session: UserSession = Depends(get_user_session),
) -> WorkspaceSetupCommandDefaults:
    """The setup command each workspace kind runs when its project configures none, from that kind's VCS."""
    workspace_service = get_services_from_request_or_websocket(request).workspace_service
    return WorkspaceSetupCommandDefaults(
        default_setup_command_by_initialization_strategy={
            initialization_strategy: workspace_service.get_workspace_vcs(
                initialization_strategy
            ).default_setup_command()
            if is_isolated_checkout(initialization_strategy)
            else None
            for initialization_strategy in WorkspaceInitializationStrategy
        }
    )
