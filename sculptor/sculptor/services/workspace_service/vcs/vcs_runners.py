"""The command runners the VCS seam uses, built in one place for every caller.

Sculptor's own calls build them from the dependency service's
`resolve_binary_path`; agent-side calls build them from their execution
environment's `get_tool_binary_path` and `get_project_env_overrides`.
"""

from typing import Mapping

from pydantic import ConfigDict

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.foundation.secrets_utils import Secret
from sculptor.services.workspace_service.vcs.git_cli import BinaryResolver
from sculptor.services.workspace_service.vcs.git_cli import EnvOverridesReader
from sculptor.services.workspace_service.vcs.git_cli import GitCli


class VcsRunners(FrozenModel):
    """Every command runner the seam uses, sharing one binary resolver and one env-overrides reader."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    git: GitCli


def _no_env_overrides() -> Mapping[str, str | Secret]:
    return {}


def build_vcs_runners(
    concurrency_group: ConcurrencyGroup,
    resolve_binary: BinaryResolver,
    read_env_overrides: EnvOverridesReader = _no_env_overrides,
) -> VcsRunners:
    return VcsRunners(git=GitCli(concurrency_group, resolve_binary, read_env_overrides))
