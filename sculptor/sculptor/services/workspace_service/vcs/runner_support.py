"""What every VCS command runner shares: how it finds its binary, how its environment is built, and its default timeout.

Binaries come from a resolver callable: Sculptor's own calls pass the
dependency service's `resolve_binary_path` and agent-side calls pass their
execution environment's `get_tool_binary_path`, so no runner looks a tool up on
PATH itself.
"""

import os
from typing import Callable
from typing import Mapping

from sculptor.foundation.secrets_utils import Secret
from sculptor.interfaces.environments.agent_execution_environment import Dependency

DEFAULT_VCS_COMMAND_TIMEOUT_SECONDS = 30.0

# Both `DependencyManagementService.resolve_binary_path` and
# `AgentExecutionEnvironment.get_tool_binary_path` have this shape.
BinaryResolver = Callable[[Dependency], str | None]

# Variables laid over the process environment for every command, read again as
# each command starts so that edits to their source reach later commands.
# Values may stay wrapped in `Secret` until then.
EnvOverridesReader = Callable[[], Mapping[str, str | Secret]]


def read_no_env_overrides() -> Mapping[str, str | Secret]:
    """The `EnvOverridesReader` for callers that add nothing to the process environment."""
    return {}


def build_command_env(
    read_env_overrides: EnvOverridesReader, extra_env: Mapping[str, str] | None
) -> Mapping[str, str] | None:
    """The env overrides, then `extra_env`, over the process environment; None when neither adds anything."""
    overrides = {**read_env_overrides(), **(extra_env or {})}
    if not overrides:
        return None
    unwrapped_overrides = {
        name: value.unwrap() if isinstance(value, Secret) else value for name, value in overrides.items()
    }
    return {**os.environ, **unwrapped_overrides}
