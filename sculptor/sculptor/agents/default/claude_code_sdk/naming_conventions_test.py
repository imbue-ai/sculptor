from pathlib import Path
from unittest.mock import MagicMock

from sculptor.agents.default.claude_code_sdk.naming_conventions import NAMING_CONVENTIONS_FILENAME
from sculptor.agents.default.claude_code_sdk.naming_conventions import NAMING_CONVENTIONS_LOCAL_FILENAME
from sculptor.agents.default.claude_code_sdk.naming_conventions import _MAX_TIER_CHARS
from sculptor.agents.default.claude_code_sdk.naming_conventions import resolve_naming_conventions
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.primitives.ids import ProjectID
from sculptor.primitives.ids import TaskID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment

# Human-readable fragments of each tier's section header; used to assert ordering.
_USER_LABEL = "your personal conventions"
_PROJECT_LABEL = "this repo's shared conventions"
_LOCAL_LABEL = "your local overrides"


def _make_environment(repo_path: Path, concurrency_group: ConcurrencyGroup) -> LocalAgentExecutionEnvironment:
    """Build a real local environment whose working directory is ``repo_path``."""
    local_env = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(repo_path)),
        project_id=ProjectID(),
        concurrency_group=concurrency_group,
        repo_host_path=repo_path,
    )
    dep_service = DependencyManagementService.model_construct(concurrency_group=MagicMock(spec=ConcurrencyGroup))
    return LocalAgentExecutionEnvironment(local_env, TaskID(), dep_service)


def _write_repo_doc(repo_path: Path, filename: str, content: str) -> None:
    doc = repo_path / ".sculptor" / filename
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(content, encoding="utf-8")


def test_returns_none_when_no_tier_present(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    assert resolve_naming_conventions(environment, sculptor_folder=tmp_path / "empty_home") is None


def test_project_tier_alone(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_FILENAME, "Prefix workspaces with the ticket id.")

    result = resolve_naming_conventions(environment, sculptor_folder=tmp_path / "empty_home")

    assert result is not None
    assert _PROJECT_LABEL in result
    assert "Prefix workspaces with the ticket id." in result
    assert _USER_LABEL not in result
    assert _LOCAL_LABEL not in result


def test_user_tier_read_from_sculptor_folder(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    user_folder = tmp_path / "home_sculptor"
    user_folder.mkdir()
    (user_folder / NAMING_CONVENTIONS_FILENAME).write_text("Use my initials as a prefix.", encoding="utf-8")

    result = resolve_naming_conventions(environment, sculptor_folder=user_folder)

    assert result is not None
    assert _USER_LABEL in result
    assert "Use my initials as a prefix." in result


def test_all_three_tiers_ordered_least_to_most_specific(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    user_folder = tmp_path / "home_sculptor"
    user_folder.mkdir()
    (user_folder / NAMING_CONVENTIONS_FILENAME).write_text("USER TIER", encoding="utf-8")
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_FILENAME, "PROJECT TIER")
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_LOCAL_FILENAME, "LOCAL TIER")

    result = resolve_naming_conventions(environment, sculptor_folder=user_folder)

    assert result is not None
    # Least-specific first so the reminder's "later wins" rule gives Local the final say.
    assert result.index(_USER_LABEL) < result.index(_PROJECT_LABEL) < result.index(_LOCAL_LABEL)
    assert result.index("USER TIER") < result.index("PROJECT TIER") < result.index("LOCAL TIER")


def test_local_tier_can_stand_alone_as_personal_override(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_LOCAL_FILENAME, "Just my personal repo override.")

    result = resolve_naming_conventions(environment, sculptor_folder=tmp_path / "empty_home")

    assert result is not None
    assert _LOCAL_LABEL in result
    assert "Just my personal repo override." in result
    assert _PROJECT_LABEL not in result


def test_whitespace_only_doc_is_treated_as_absent(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_FILENAME, "   \n\t\n")

    assert resolve_naming_conventions(environment, sculptor_folder=tmp_path / "empty_home") is None


def test_oversized_doc_is_truncated(tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_FILENAME, "x" * (_MAX_TIER_CHARS + 500))

    result = resolve_naming_conventions(environment, sculptor_folder=tmp_path / "empty_home")

    assert result is not None
    assert "…(truncated)" in result
    # The clipped body cannot exceed the cap (plus the short truncation marker + header).
    assert result.count("x") <= _MAX_TIER_CHARS


def test_missing_sculptor_folder_is_handled_gracefully(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    environment = _make_environment(tmp_path, test_root_concurrency_group)
    _write_repo_doc(tmp_path, NAMING_CONVENTIONS_FILENAME, "PROJECT TIER")

    # A nonexistent user folder must not raise; only the project tier survives.
    result = resolve_naming_conventions(environment, sculptor_folder=tmp_path / "does" / "not" / "exist")

    assert result is not None
    assert _PROJECT_LABEL in result
    assert _USER_LABEL not in result
