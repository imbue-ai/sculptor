import re
from pathlib import Path
from typing import Final
from unittest.mock import MagicMock

import pytest

from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.agents.data_types.ids import TaskID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.agents.default.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.agents.default.claude_code_sdk.diff_tracker import _get_file_contents_at_commit_hash
from sculptor.agents.default.claude_code_sdk.diff_tracker import _is_file_present_at_commit_hash
from sculptor.agents.default.claude_code_sdk.diff_tracker import create_unified_diff
from sculptor.database.workspace_enums import WorkspaceInitializationStrategy
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.tasks.handlers.run_agent.git import run_git_command_in_environment

_FILE_CONTENTS: Final[str] = """def foo() -> None:
    pass"""

_NEW_FILE_CONTENTS: Final[str] = """def foo() -> None:
    print('this is new!')"""

_FILE_PATH: Final[str] = "main.py"


def _create_agent_execution_environment(
    path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> AgentExecutionEnvironment:
    local_env = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(path)),
        project_id=ProjectID(),
        concurrency_group=test_root_concurrency_group,
        repo_host_path=path,
    )
    mock_cg = MagicMock(spec=ConcurrencyGroup)
    dep_service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    return LocalAgentExecutionEnvironment(local_env, TaskID(), dep_service)


def _create_clone_mode_agent_execution_environment(
    workspace_root: Path, test_root_concurrency_group: ConcurrencyGroup
) -> AgentExecutionEnvironment:
    """Create a clone-mode environment where workspace_path != working_directory.

    In clone mode, workspace_path is the task root (workspace_root) and the
    working directory is workspace_root/code/.
    """
    code_dir = workspace_root / "code"
    code_dir.mkdir(parents=True, exist_ok=True)
    local_env = LocalEnvironment(
        environment_id=LocalEnvironmentID(str(workspace_root)),
        project_id=ProjectID(),
        concurrency_group=test_root_concurrency_group,
        repo_host_path=code_dir,
        initialization_strategy=WorkspaceInitializationStrategy.CLONE,
    )
    mock_cg = MagicMock(spec=ConcurrencyGroup)
    dep_service = DependencyManagementService.model_construct(concurrency_group=mock_cg)
    return LocalAgentExecutionEnvironment(local_env, TaskID(), dep_service)


def _setup_repo_in_environment_with_initial_files_commit(environment: AgentExecutionEnvironment) -> str:
    working_dir = environment.get_working_directory()
    environment.write_file(str(working_dir / _FILE_PATH), _FILE_CONTENTS)
    run_git_command_in_environment(environment=environment, command=["git", "init"])
    run_git_command_in_environment(environment=environment, command=["git", "add", "."])
    run_git_command_in_environment(environment=environment, command=["git", "commit", "-am", "initial commit"])
    _, commit_hash, _ = run_git_command_in_environment(environment=environment, command=["git", "rev-parse", "HEAD"])
    return commit_hash


@pytest.fixture
def environment_and_initial_repo_commit_hash(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> tuple[AgentExecutionEnvironment, str]:
    environment = _create_agent_execution_environment(tmp_path, test_root_concurrency_group)
    initial_repo_commit_hash = _setup_repo_in_environment_with_initial_files_commit(environment=environment).strip()
    return environment, initial_repo_commit_hash


@pytest.fixture
def clone_mode_environment_and_initial_repo_commit_hash(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> tuple[AgentExecutionEnvironment, str]:
    environment = _create_clone_mode_agent_execution_environment(tmp_path, test_root_concurrency_group)
    initial_repo_commit_hash = _setup_repo_in_environment_with_initial_files_commit(environment=environment).strip()
    return environment, initial_repo_commit_hash


def test_is_file_present_at_commit_hash(
    environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    environment, initial_repo_commit_hash = environment_and_initial_repo_commit_hash
    assert _is_file_present_at_commit_hash(
        environment=environment, commit_hash=initial_repo_commit_hash, relative_file_path=Path(_FILE_PATH)
    )

    assert not _is_file_present_at_commit_hash(
        environment=environment, commit_hash=initial_repo_commit_hash, relative_file_path=Path("does_not_exist.py")
    )


def test_get_file_contents_at_commit_hash(
    environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    environment, initial_repo_commit_hash = environment_and_initial_repo_commit_hash
    file_contents = _get_file_contents_at_commit_hash(
        environment=environment, commit_hash=initial_repo_commit_hash, relative_file_path=Path(_FILE_PATH)
    )
    assert file_contents == _FILE_CONTENTS


def test_diff_tracker_get_file_snapshot(
    environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    environment, _ = environment_and_initial_repo_commit_hash
    diff_tracker = DiffTracker(
        environment=environment,
    )
    assert (
        diff_tracker._get_file_snapshot(file_path=str(environment.get_working_directory() / _FILE_PATH))
        == _FILE_CONTENTS
    )
    assert (
        diff_tracker._get_file_snapshot(file_path=str(environment.get_working_directory() / "does_not_exist.py"))
        is None
    )


def test_compute_diff_after_edit_to_existing_file(
    environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    environment, initial_repo_commit_hash = environment_and_initial_repo_commit_hash
    diff_tracker = DiffTracker(
        environment=environment,
    )
    file_path = str(environment.get_working_directory() / _FILE_PATH)
    environment.write_file(file_path, _NEW_FILE_CONTENTS)
    diff = diff_tracker._compute_diff_for_file_path(file_path=file_path)
    assert diff is not None
    assert (
        "\n".join(diff.splitlines()[2:])
        == f"""--- a{file_path}
+++ b{file_path}
@@ -1,2 +1,2 @@
 def foo() -> None:
-    pass
\\ No newline at end of file
+    print('this is new!')
\\ No newline at end of file"""
    )


def test_compute_diff_after_edit_to_new_file(
    environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    environment, _ = environment_and_initial_repo_commit_hash
    diff_tracker = DiffTracker(
        environment=environment,
    )
    file_path = str(environment.get_working_directory() / "blah.py")
    environment.write_file(file_path, _NEW_FILE_CONTENTS)
    diff = diff_tracker._compute_diff_for_file_path(file_path=file_path)
    assert diff is not None
    assert (
        "\n".join(diff.splitlines()[3:])
        == f"""--- /dev/null
+++ b{file_path}
@@ -0,0 +1,2 @@
+def foo() -> None:
+    print('this is new!')
\\ No newline at end of file"""
    )


def test_get_file_contents_preserves_trailing_newline(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """Committed file content with a trailing newline must round-trip exactly.

    Regression: _get_file_contents_at_commit_hash used to call stdout.strip(),
    which silently dropped the trailing newline. That caused _compute_diff_for_file_path
    to report a spurious "\\ No newline at end of file" hunk against an unchanged
    file, which surfaced in the UI as a file chip with a diff that only added a
    final newline.
    """
    environment = _create_agent_execution_environment(tmp_path, test_root_concurrency_group)
    working_dir = environment.get_working_directory()
    file_path = str(working_dir / "with_newline.py")
    original_contents = "print('hello')\n"
    environment.write_file(file_path, original_contents)
    run_git_command_in_environment(environment=environment, command=["git", "init"])
    run_git_command_in_environment(environment=environment, command=["git", "add", "."])
    run_git_command_in_environment(environment=environment, command=["git", "commit", "-am", "initial commit"])
    _, commit_hash, _ = run_git_command_in_environment(environment=environment, command=["git", "rev-parse", "HEAD"])

    file_contents = _get_file_contents_at_commit_hash(
        environment=environment, commit_hash=commit_hash.strip(), relative_file_path=Path("with_newline.py")
    )
    assert file_contents == original_contents


def test_compute_diff_for_unchanged_file_with_trailing_newline(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """An unchanged file that ends in a newline must produce no diff.

    Regression: stripping the trailing newline from the git-tree snapshot made
    the snapshot differ from the on-disk content, producing a bogus "no newline
    at end of file" diff against a file that nothing had touched.
    """
    environment = _create_agent_execution_environment(tmp_path, test_root_concurrency_group)
    working_dir = environment.get_working_directory()
    file_path = str(working_dir / "with_newline.py")
    environment.write_file(file_path, "print('hello')\n")
    run_git_command_in_environment(environment=environment, command=["git", "init"])
    run_git_command_in_environment(environment=environment, command=["git", "add", "."])
    run_git_command_in_environment(environment=environment, command=["git", "commit", "-am", "initial commit"])

    diff_tracker = DiffTracker(environment=environment)
    diff = diff_tracker._compute_diff_for_file_path(file_path=file_path)
    assert diff is None or diff == "", f"Expected no diff for unchanged file, got:\n{diff}"


def test_attempt_to_compute_diff_for_non_existent_file(
    environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    environment, _ = environment_and_initial_repo_commit_hash
    diff_tracker = DiffTracker(
        environment=environment,
    )
    file_path = str(environment.get_working_directory() / "does_not_exist.py")
    assert diff_tracker._compute_diff_for_file_path(file_path=file_path) is None


def normalize_diff(diff: str | None) -> str | None:
    """Normalize git diff output by replacing index hashes with zeros."""
    if not diff:
        return diff

    # Replace index hashes with normalized format
    # Matches patterns like "index 6ad36e52f0..2c3562bdb8 100644"
    # and replaces with "index 0000000..0000000 100644"
    diff = re.sub(r"index [0-9a-f]+\.\.[0-9a-f]+", "index 0000000..0000000", diff)

    # For new files: "index 0000000000..b47864eced" -> "index 0000000..0000000"
    diff = re.sub(r"index [0-9a-f]+\.\.[0-9a-f]+", "index 0000000..0000000", diff)

    return diff


def test_no_change_returns_empty_string(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test that identical content returns empty string."""
    assert create_unified_diff("test.txt", "hello world", "hello world", test_root_concurrency_group) == ""
    assert create_unified_diff("test.bin", b"hello world", b"hello world", test_root_concurrency_group) == ""


def test_regular_text_diff(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test diff for modified text file."""
    old_content = "Line 1\nLine 2\nLine 3\n"
    new_content = "Line 1\nLine 2 modified\nLine 3\nLine 4\n"

    result = create_unified_diff("test.txt", old_content, new_content, test_root_concurrency_group)
    result = normalize_diff(result)

    expected = """diff --git a/test.txt b/test.txt
index 0000000..0000000 100644
--- a/test.txt
+++ b/test.txt
@@ -1,3 +1,4 @@
 Line 1
-Line 2
+Line 2 modified
 Line 3
+Line 4
"""
    assert result == expected


def test_file_creation(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test diff for newly created file."""
    result = create_unified_diff("new_file.txt", None, "Hello, world!\nThis is new.\n", test_root_concurrency_group)
    result = normalize_diff(result)

    expected = """diff --git a/new_file.txt b/new_file.txt
new file mode 100644
index 0000000..0000000
--- /dev/null
+++ b/new_file.txt
@@ -0,0 +1,2 @@
+Hello, world!
+This is new.
"""
    assert result == expected


def test_no_newline_at_end_of_file(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test handling files without newline at end."""
    # Adding newline to file without one
    result = create_unified_diff(
        "no_newline.txt", "Line without newline", "Line without newline\n", test_root_concurrency_group
    )
    result = normalize_diff(result)

    expected = """diff --git a/no_newline.txt b/no_newline.txt
index 0000000..0000000 100644
--- a/no_newline.txt
+++ b/no_newline.txt
@@ -1 +1 @@
-Line without newline
\\ No newline at end of file
+Line without newline
"""
    assert result == expected


def test_binary_file_modification(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test diff for binary files shows binary diff marker."""
    old_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    new_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x02"

    result = create_unified_diff("image.png", old_content, new_content, test_root_concurrency_group)

    assert result is not None
    # Binary files produce different output depending on git version
    assert "Binary files a/image.png and b/image.png differ" in result or "GIT binary patch" in result


def test_empty_file_to_content(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test diff from empty file to file with content."""
    result = create_unified_diff("empty.txt", "", "Now has content\n", test_root_concurrency_group)
    result = normalize_diff(result)

    expected = """diff --git a/empty.txt b/empty.txt
index 0000000..0000000 100644
--- a/empty.txt
+++ b/empty.txt
@@ -0,0 +1 @@
+Now has content
"""
    assert result == expected


def test_unicode_content(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test diff with unicode content."""
    old_content = "Hello 世界\n"
    new_content = "Hello 世界! 🎉\n"

    result = create_unified_diff("unicode.txt", old_content, new_content, test_root_concurrency_group)
    result = normalize_diff(result)

    expected = """diff --git a/unicode.txt b/unicode.txt
index 0000000..0000000 100644
--- a/unicode.txt
+++ b/unicode.txt
@@ -1 +1 @@
-Hello 世界
+Hello 世界! 🎉
"""
    assert result == expected


def test_nested_file_path(test_root_concurrency_group: ConcurrencyGroup) -> None:
    """Test diff with nested directory structure in filepath."""
    result = create_unified_diff(
        "src/components/Button.tsx",
        "export const Button = () => <button>Click</button>\n",
        "export const Button = () => <button>Click me!</button>\n",
        test_root_concurrency_group,
    )
    result = normalize_diff(result)

    expected = """diff --git a/src/components/Button.tsx b/src/components/Button.tsx
index 0000000..0000000 100644
--- a/src/components/Button.tsx
+++ b/src/components/Button.tsx
@@ -1 +1 @@
-export const Button = () => <button>Click</button>
+export const Button = () => <button>Click me!</button>
"""
    assert result == expected


def test_clone_mode_diff_shows_only_changed_lines(
    clone_mode_environment_and_initial_repo_commit_hash: tuple[AgentExecutionEnvironment, str],
) -> None:
    """Test that diffs in clone mode show only changed lines, not the full file.

    Regression test: DiffTracker.workspace_path was set to the task root
    (get_workspace_path()) instead of the git working directory
    (get_working_directory()). In clone mode these differ — the task root is
    the parent of the code/ directory. This caused _get_file_from_git_tree to
    compute a relative path with a spurious "code/" prefix (e.g.
    "code/main.py" instead of "main.py"), so git ls-tree couldn't find the
    file, old_content was None, and the diff showed the entire file as a new
    file creation instead of just the changed lines.
    """
    environment, _ = clone_mode_environment_and_initial_repo_commit_hash
    diff_tracker = DiffTracker(environment=environment)
    file_path = str(environment.get_working_directory() / _FILE_PATH)
    environment.write_file(file_path, _NEW_FILE_CONTENTS)
    diff = diff_tracker._compute_diff_for_file_path(file_path=file_path)
    assert diff is not None
    # The diff must show a modification (--- a/..., +++ b/...) not a new file
    # creation (--- /dev/null). If the bug is present, old_content is None and
    # create_unified_diff produces a "new file" diff starting from /dev/null.
    assert "/dev/null" not in diff, (
        "Diff shows full file as new creation instead of just the changed lines."
        + " This means _get_file_from_git_tree failed to find the file at the initial tree SHA."
    )
    assert "-    pass" in diff
    assert "+    print('this is new!')" in diff
