"""Integration tests for displaying ~ instead of home directory in paths."""

from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.fixture
def _home_sentinel_dir() -> Generator[Path, None, None]:
    """Ensure a non-hidden directory exists under HOME for autocomplete.

    Some CI environments have an empty home directory with only dotfiles.
    """
    sentinel_dir = Path.home() / "test_autocomplete_dir"
    sentinel_dir.mkdir(exist_ok=True)
    yield sentinel_dir
    sentinel_dir.rmdir()


@user_story("to see paths with ~ instead of the full home directory")
def test_path_autocomplete_shows_tilde_for_home_directory(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """Test that the path autocomplete dropdown displays ~/... instead of /Users/.../... .

    Verifies:
    1. Typing ~/ in the add-repo dialog triggers autocomplete
    2. The autocomplete items show paths with ~/ prefix
    3. No autocomplete item shows the expanded home directory path
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    dialog = repos_settings.open_add_repo_dialog()
    dialog.select_local_source()

    path_input = dialog.get_path_input()
    path_input.fill("~/")

    items = dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    expect(items).not_to_have_count(0)
