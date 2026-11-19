"""The rules for a directory inside a jj workspace offered as a Sculptor project: resolve it to its colocated repository, or refuse it."""

from pathlib import Path
from typing import assert_never

from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.jj_availability import describe_jj_unavailability
from sculptor.services.workspace_service.vcs.git_cli import find_jj_workspace_root
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_repo_queries import is_jj_colocated
from sculptor.web.data_types import JjAvailable
from sculptor.web.data_types import JjNoIdentity
from sculptor.web.data_types import JjNotInstalled
from sculptor.web.data_types import JjNotRunnable
from sculptor.web.data_types import JjReadiness
from sculptor.web.data_types import JjUnsupportedVersion

_JJ_DIRECTORY = Path(".jj")
_STORE_LINK = _JJ_DIRECTORY / "repo"


class ProjectInJjWorkspaceError(ValueError):
    """A directory offered as a project lies inside a jj workspace, which has `.jj` and no `.git`."""

    def __init__(self, jj_workspace_root: Path) -> None:
        self.jj_workspace_root = jj_workspace_root
        super().__init__(self._describe())

    def _describe(self) -> str:
        return (
            f"Selected directory is inside the jj workspace at {self.jj_workspace_root}, which has no git repository. "
            + "Sculptor can only add a jj repository that is colocated with git."
        )


class JjUnusableForProjectError(ProjectInJjWorkspaceError):
    """Sculptor cannot use the jj it resolves, so it cannot find the repository of the jj workspace holding a project."""

    def __init__(
        self, jj_workspace_root: Path, jj_readiness: JjNotInstalled | JjNotRunnable | JjUnsupportedVersion
    ) -> None:
        self.jj_readiness = jj_readiness
        super().__init__(jj_workspace_root)

    def _describe(self) -> str:
        return (
            f"Selected directory is inside the jj workspace at {self.jj_workspace_root}. "
            + f"Sculptor needs a working jj to find that workspace's repository, but {describe_jj_unavailability(self.jj_readiness)}."
        )


def refuse_project_in_jj_workspace(project_path: Path) -> None:
    """Raise `ProjectInJjWorkspaceError` when `project_path` is inside a jj workspace.

    Sculptor runs git in a project directory, and git must not run in a jj
    workspace: it would act on any git repository around it, and a `.git` it
    created there would switch off the tripwire that keeps git out of jj
    workspaces. The path is resolved first, so a symlink into a jj workspace is
    refused too.
    """
    jj_workspace_root = find_jj_workspace_root(project_path.resolve())
    if jj_workspace_root is not None:
        raise ProjectInJjWorkspaceError(jj_workspace_root)


def resolve_project_in_jj_workspace(
    project_path: Path, jj: JjCli, dependency_management_service: DependencyManagementService
) -> Path:
    """The directory to register as the project for `project_path`.

    Inside a jj workspace whose repository is colocated with git, that is the
    repository's root, as a git worktree's project is its main repository.
    Outside any jj workspace it is `project_path` itself. Any other jj
    workspace raises `ProjectInJjWorkspaceError`. Telling whether the
    repository is colocated runs jj, so a jj that is missing, does not run or
    is too old raises `JjUnusableForProjectError`. The path is resolved first,
    so a symlink into a jj workspace is treated as the workspace.
    """
    jj_workspace_root = find_jj_workspace_root(project_path.resolve())
    if jj_workspace_root is None:
        return project_path
    repository_root = _find_linked_repository_root(jj_workspace_root)
    if repository_root is None:
        raise ProjectInJjWorkspaceError(jj_workspace_root)
    _raise_if_jj_is_unusable(jj_workspace_root, dependency_management_service.probe_jj_readiness())
    if not is_jj_colocated(jj, repository_root):
        raise ProjectInJjWorkspaceError(jj_workspace_root)
    return repository_root


def _find_linked_repository_root(jj_workspace_root: Path) -> Path | None:
    """The root of the repository whose store the workspace links to, or None when it links to no other repository.

    A workspace added with `jj workspace add` holds, in `.jj/repo`, the path
    of the repository's store relative to its own `.jj`, and the store is
    `<repository>/.jj/repo`. A repository's own workspace holds the store
    itself there, as a directory.
    """
    try:
        store_link = (jj_workspace_root / _STORE_LINK).read_text()
    except (FileNotFoundError, IsADirectoryError):
        return None
    store = (jj_workspace_root / _JJ_DIRECTORY / store_link).resolve()
    return store.parent.parent


def _raise_if_jj_is_unusable(jj_workspace_root: Path, jj_readiness: JjReadiness) -> None:
    """Raise `JjUnusableForProjectError` unless jj can read the repository; reading needs no author identity."""
    match jj_readiness:
        case JjAvailable() | JjNoIdentity():
            return
        case JjNotInstalled() | JjNotRunnable() | JjUnsupportedVersion():
            raise JjUnusableForProjectError(jj_workspace_root, jj_readiness)
        case _ as unreachable:
            assert_never(unreachable)
