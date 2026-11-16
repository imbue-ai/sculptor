"""The rule that keeps a directory inside a jj workspace from becoming a Sculptor project."""

from pathlib import Path

from sculptor.services.workspace_service.vcs.git_cli import find_jj_workspace_root


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
