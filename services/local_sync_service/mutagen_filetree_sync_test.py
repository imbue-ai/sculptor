import tempfile
from pathlib import Path
from typing import Generator

import pytest
from pydantic import ValidationError

from sculptor.services.local_sync_service.mutagen_filetree_sync import MultiRootFiletreeSubPathReconciler


class _MultiRootFiletreeSubPathReconciler(MultiRootFiletreeSubPathReconciler):
    test_root_paths: tuple[Path, ...]

    @property
    def root_paths(self) -> tuple[Path, ...]:
        return self.test_root_paths


def _dir_structure_for_testing(dir: Path, relative_contents: dict[Path, str]) -> None:
    dir.mkdir(parents=True, exist_ok=True)
    for rel_path, content in relative_contents.items():
        (dir / rel_path).parent.mkdir(parents=True, exist_ok=True)
        (dir / rel_path).write_text(content)


@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


def test_multiroot_reconciler_exclusions(temp_dir: Path) -> None:
    # Create foo directory structure
    foo_dir = temp_dir / "foo"
    included_name = Path("included.txt")
    excluded_name = Path(".git/excluded.txt")
    dir_structure = {included_name: "test", excluded_name: "test"}
    _dir_structure_for_testing(foo_dir, dir_structure)

    bar_dir = temp_dir / "bar"
    _dir_structure_for_testing(bar_dir, dir_structure)

    reconciler = _MultiRootFiletreeSubPathReconciler(tag="test", test_root_paths=(foo_dir, bar_dir))

    assert reconciler.is_relevant_subpath(foo_dir / included_name)
    assert not reconciler.is_relevant_subpath(foo_dir / excluded_name)
    assert reconciler.is_relevant_subpath(bar_dir / included_name)
    assert not reconciler.is_relevant_subpath(bar_dir / excluded_name)
    assert not reconciler.is_relevant_subpath(foo_dir), "Root path should not be relevant due to bubble up"
    assert reconciler.dirs_to_watch == (foo_dir, bar_dir)
    assert not reconciler.is_relevant_subpath(temp_dir), "Parent directory should not be relevant"

    # Test that absolute paths in excluded_relative_subpaths raise an error
    with pytest.raises(ValidationError, match="must be relative"):
        _MultiRootFiletreeSubPathReconciler(
            tag="test", test_root_paths=(temp_dir,), excluded_relative_subpaths=(Path("/absolute/path"),)
        )

    assert Path(".git/") in reconciler.excluded_relative_subpaths, "Default exclusions should include .git/"
    assert Path("node_modules/") in reconciler.excluded_relative_subpaths, (
        "Default exclusions should include node_modules/"
    )
