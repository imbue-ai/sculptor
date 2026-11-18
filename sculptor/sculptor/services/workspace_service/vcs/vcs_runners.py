"""The command runners the VCS seam uses, built together so that a new runner is added in one place."""

from pydantic import ConfigDict

from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.pydantic_serialization import FrozenModel
from sculptor.services.workspace_service.vcs.git_cli import GitCli
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.runner_support import BinaryResolver
from sculptor.services.workspace_service.vcs.runner_support import EnvOverridesReader
from sculptor.services.workspace_service.vcs.runner_support import read_no_env_overrides


class VcsRunners(FrozenModel):
    """Every command runner the seam uses, sharing one binary resolver and one env-overrides reader."""

    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)

    git: GitCli
    jj: JjCli


def build_vcs_runners(
    concurrency_group: ConcurrencyGroup,
    resolve_binary: BinaryResolver,
    read_env_overrides: EnvOverridesReader = read_no_env_overrides,
) -> VcsRunners:
    return VcsRunners(
        git=GitCli(concurrency_group, resolve_binary, read_env_overrides),
        jj=JjCli(concurrency_group, resolve_binary, read_env_overrides),
    )
