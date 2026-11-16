from pathlib import Path

from loguru import logger

from sculptor.agents.default.claude_code_sdk.diff_tracker import create_unified_diff
from sculptor.agents.default.constants import FILE_CHANGE_TOOL_NAMES
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.services.workspace_service.vcs.errors import VcsCommandError
from sculptor.services.workspace_service.vcs.interfaces import TurnDiffTracker
from sculptor.services.workspace_service.vcs.jj_cli import JjCli
from sculptor.services.workspace_service.vcs.jj_cli import JjSnapshotPolicy
from sculptor.services.workspace_service.vcs.jj_repo_queries import snapshot_working_copy
from sculptor.services.workspace_service.vcs.jj_revsets import root_file_fileset
from sculptor.state.chat_state import ToolInput


class JjTurnDiffTracker(TurnDiffTracker):
    """Tracks the files an agent changes in a jj workspace during one turn.

    The baseline is the working-copy commit right after a snapshot, so changes
    made any way, including by shell commands and by the agent's own jj
    commits, are measured from it. A jj failure, such as a stale working copy,
    is logged and reads as no change.
    """

    def __init__(self, jj: JjCli, checkout_path: Path, concurrency_group: ConcurrencyGroup) -> None:
        self._jj = jj
        self._checkout_path = checkout_path
        self._concurrency_group = concurrency_group
        self._content_by_relative_path: dict[str, str | bytes] = {}
        self._baseline_commit_id = self._snapshot_commit_id()

    def rebaseline(self) -> None:
        self._baseline_commit_id = self._snapshot_commit_id()
        self._content_by_relative_path.clear()

    def compute_diff_for_tool(self, tool_name: str, tool_input: ToolInput) -> str | None:
        """The diff between the file as this turn last saw it and as it is now."""
        if tool_name not in FILE_CHANGE_TOOL_NAMES:
            return None
        raw_file_path = tool_input.get("file_path")
        if not raw_file_path:
            return None
        path = Path(str(raw_file_path))
        if not path.is_absolute():
            path = self._checkout_path / path
        relative_path = self._find_relative_path(path)
        if relative_path is None:
            logger.debug("File {} is outside the checkout, skipping diff", path)
            return None
        try:
            new_content = _read_file_content(path)
        except OSError as e:
            logger.debug("Cannot read {}, skipping diff: {}", path, e)
            return None
        if relative_path in self._content_by_relative_path:
            old_content = self._content_by_relative_path[relative_path]
        else:
            old_content = self._read_baseline_content(relative_path)
        diff = create_unified_diff(str(path), old_content, new_content, self._concurrency_group)
        self._content_by_relative_path[relative_path] = new_content
        return diff

    def get_changed_file_paths(self) -> list[str]:
        """Root-relative paths of the files that differ between the baseline and a fresh snapshot."""
        if self._baseline_commit_id is None:
            return []
        try:
            current_commit_id = snapshot_working_copy(self._jj, self._checkout_path).commit_id
            if current_commit_id == self._baseline_commit_id:
                return []
            result = self._jj.run(
                ["diff", "--from", self._baseline_commit_id, "--to", current_commit_id, "--name-only"],
                self._checkout_path,
                snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
            )
        except VcsCommandError as e:
            logger.warning("Cannot list the files changed in jj workspace {}: {}", self._checkout_path, e)
            return []
        return result.stdout.splitlines()

    def to_repo_relative_path(self, file_path: str) -> str:
        if not file_path:
            return file_path
        path = Path(file_path)
        if not path.is_absolute():
            path = self._checkout_path / path
        relative_path = self._find_relative_path(path)
        return file_path if relative_path is None else relative_path

    def _find_relative_path(self, path: Path) -> str | None:
        """`path` relative to the checkout root, or None when it is outside; symlinks such as macOS's /var are resolved."""
        resolved_path = path.resolve()
        resolved_root = self._checkout_path.resolve()
        if resolved_path == resolved_root or not resolved_path.is_relative_to(resolved_root):
            return None
        return str(resolved_path.relative_to(resolved_root))

    def _snapshot_commit_id(self) -> str | None:
        try:
            return snapshot_working_copy(self._jj, self._checkout_path).commit_id
        except VcsCommandError as e:
            logger.warning("Cannot snapshot jj workspace {} for a turn baseline: {}", self._checkout_path, e)
            return None

    def _read_baseline_content(self, relative_path: str) -> str | None:
        """The file's content at the baseline; None when the baseline has no such file."""
        if self._baseline_commit_id is None:
            return None
        try:
            result = self._jj.run(
                ["file", "show", "-r", self._baseline_commit_id, root_file_fileset(relative_path)],
                self._checkout_path,
                snapshot=JjSnapshotPolicy.IGNORE_WORKING_COPY,
                is_checked=False,
            )
        except VcsCommandError as e:
            logger.warning("Cannot read {} at the turn baseline: {}", relative_path, e)
            return None
        if result.returncode != 0:
            return None
        return result.stdout


def _read_file_content(path: Path) -> str | bytes:
    try:
        return path.read_text()
    except UnicodeDecodeError:
        return path.read_bytes()
