"""The rule that keeps a directory inside a jj workspace from becoming a Sculptor project.

The project routes and `sculptor <path>` on the command line share it, and
each reports a refusal in its own way.
"""

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

    Registering such a directory leaves every workspace creation failing, and
    making it a project runs git there: `git init` puts a `.git` into the jj
    workspace, which switches off the tripwire that keeps Sculptor's git calls
    out of jj workspaces, and `git commit` commits in any git repository around
    it. The path is resolved first, so a symlink into a jj workspace is refused
    too.
    """
    jj_workspace_root = find_jj_workspace_root(project_path.resolve())
    if jj_workspace_root is not None:
        raise ProjectInJjWorkspaceError(jj_workspace_root)
