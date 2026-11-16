"""The rules for a directory inside a jj workspace offered as a Sculptor project: resolve it to its colocated repository, or refuse it."""

from pathlib import Path

from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.git_cli import find_jj_workspace_root
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_repo_queries import is_jj_colocated

_JJ_DIRECTORY = Path(".jj")
_STORE_LINK = _JJ_DIRECTORY / "repo"


class ProjectInJjWorkspaceError(ValueError):
    """A directory offered as a project lies inside a jj workspace, which has `.jj` and no `.git`."""

    def __init__(self, jj_workspace_root: Path) -> None:
        self.jj_workspace_root = jj_workspace_root
        super().__init__(
            f"Selected directory is inside the jj workspace at {jj_workspace_root}, which has no git repository. "
            + "Sculptor can only add a jj repository that is colocated with git."
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


def resolve_project_in_jj_workspace(project_path: Path, jj: JjCli) -> Path:
    """The directory to register as the project for `project_path`.

    Inside a jj workspace whose repository is colocated with git, that is the
    repository's root, as a git worktree's project is its main repository.
    Outside any jj workspace it is `project_path` itself. Any other jj
    workspace raises `ProjectInJjWorkspaceError`: registering it would leave
    every workspace creation failing. While jj cannot run, no repository reads
    as colocated. The path is resolved first, so a symlink into a jj workspace
    is treated as the workspace.
    """
    jj_workspace_root = find_jj_workspace_root(project_path.resolve())
    if jj_workspace_root is None:
        return project_path
    repository_root = _find_linked_repository_root(jj_workspace_root)
    if repository_root is None or not _is_colocated_while_jj_runs(jj, repository_root):
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


def _is_colocated_while_jj_runs(jj: JjCli, repository_root: Path) -> bool:
    try:
        return is_jj_colocated(jj, repository_root)
    except VcsCommandError:
        return False
