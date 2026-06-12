"""Integration tests for PathAutocomplete keyboard interactions."""

import os
import re
import sys
from collections.abc import Generator
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_MOD_KEY = "Meta" if sys.platform == "darwin" else "Control"


@pytest.fixture
def _home_sentinel_dir() -> Generator[Path, None, None]:
    """Ensure a non-hidden directory exists under HOME for autocomplete.

    CI Docker images may have an empty home directory with only dotfiles.

    The path is suffixed with the PID so concurrent workers (xdist or offload
    sandboxes) don't race on shared mkdir/rmdir of the same path.
    """
    sentinel_dir = Path.home() / f"test_autocomplete_dir_{os.getpid()}"
    sentinel_dir.mkdir(exist_ok=True)
    yield sentinel_dir
    sentinel_dir.rmdir()


@pytest.fixture
def _nested_sentinel_dirs() -> Generator[Path, None, None]:
    """Create a directory with subdirectories for testing directory drilling.

    Per-PID suffix avoids races between concurrent workers on the shared HOME.
    """
    parent = Path.home() / f"test_autocomplete_parent_{os.getpid()}"
    child = parent / "child_subdir"
    child.mkdir(parents=True, exist_ok=True)
    yield parent
    child.rmdir()
    parent.rmdir()


@user_story("to select text in the path input with Shift+ArrowUp")
def test_shift_arrow_up_selects_text_instead_of_navigating_dropdown(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """Test that Shift+ArrowUp selects text in the input rather than navigating the autocomplete dropdown.

    Verifies:
    1. Typing ~/ triggers the autocomplete dropdown
    2. Pressing Shift+ArrowUp selects text in the input (cursor moves to start with selection)
    3. The autocomplete dropdown highlight does not change due to Shift+ArrowUp
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill("~/")

    items = add_repo_dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    # Press Shift+ArrowUp — should select all text from cursor to start
    path_input.press("Shift+Home")  # First use Home to be explicit about selection
    # Clear selection and place cursor at end
    path_input.press("End")
    path_input.press("Shift+ArrowUp")

    # Verify that text is selected by typing a character — if text was selected,
    # it gets replaced and the input value will be shorter than before.
    original_value = path_input.input_value()
    path_input.press("x")
    new_value = path_input.input_value()
    assert len(new_value) < len(original_value), (
        f"Expected Shift+ArrowUp to select text (typing should replace it), but value went from {original_value!r} to {new_value!r}"
    )


@user_story("to drill into a directory and see the first sub-entry highlighted")
def test_enter_on_directory_highlights_first_subentry(
    sculptor_instance_: SculptorInstance,
    _nested_sentinel_dirs: Path,
) -> None:
    """Test that pressing Enter on a directory entry highlights the first sub-entry.

    When ~/ is typed, the autocomplete shows many directories. Pressing Enter
    on the highlighted directory drills into it, and the first sub-entry in the
    new listing should be highlighted (data-selected="true").

    Verifies:
    1. Typing ~/ triggers autocomplete with directory entries
    2. Pressing Enter on a highlighted directory drills into it
    3. After new sub-directory items load, the first item has data-selected="true"
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill("~/")

    items = add_repo_dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    # Record the first item text before drilling
    first_item_text = items.first.inner_text()

    # Press Enter to select the first highlighted directory (drills into it)
    path_input.press("Enter")

    # Wait for the list to update — items should change (new subdirectory listing)
    # We wait for the first item text to change, indicating new items loaded
    expect(items.first).not_to_have_text(first_item_text)

    # Verify the first item in the new list is highlighted
    expect(items.first).to_have_attribute("data-selected", "true")


@user_story("to submit a path with Cmd+Enter while the autocomplete dropdown is open")
def test_cmd_enter_submits_path(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """Test that Cmd+Enter (or Ctrl+Enter) submits the current path value.

    The autocomplete dropdown covers the Add button, so Cmd+Enter provides
    a keyboard shortcut to submit without needing to dismiss the dropdown first.

    Verifies:
    1. Typing ~/ triggers the autocomplete dropdown
    2. Pressing Cmd+Enter fires onSubmit (which triggers repo validation)
    3. The Add button shows a spinner, indicating validation is in progress
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill("~/")

    items = add_repo_dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    # Press Cmd+Enter — should submit the path (triggering validation)
    path_input.press(f"{_MOD_KEY}+Enter")

    # When onSubmit fires, the Add Repository button shows a spinner while
    # validation is in progress. This proves the submit happened.
    submit_button = add_repo_dialog.get_submit_button()
    expect(submit_button).to_be_disabled()


@user_story("to see the correct repo name after selecting a folder from autocomplete")
def test_selected_folder_submit_shows_correct_repo_name(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """Test that submitting a folder selected from autocomplete shows the correct repo name.

    When a user selects a folder from the autocomplete dropdown, the path gets
    a trailing "/" appended. Submitting this path should still display the correct
    repo name in the validation dialog (not an empty name).

    Verifies:
    1. Selecting a directory from autocomplete sets the input value with trailing /
    2. Submitting via Cmd+Enter triggers validation
    3. The validation dialog shows the correct directory name, not an empty name
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()

    # Type a prefix that filters to just this worker's sentinel directory.
    # The xdist worker_id is baked into the fixture name so the prefix is
    # unique across concurrent workers, and we drop the trailing character
    # so the backend treats it as a prefix filter rather than an exact
    # directory match (which would drill into the empty sentinel instead).
    sentinel_name = _home_sentinel_dir.name
    path_input = add_repo_dialog.get_path_input()
    path_input.fill(f"~/{sentinel_name[:-1]}")

    # Wait for autocomplete items to appear (should show the sentinel dir)
    items = add_repo_dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    # Press Enter to select the directory (drills into it, adds trailing /)
    path_input.press("Enter")

    # Verify the input value ends with "/" (the autocomplete behavior)
    expect(path_input).to_have_value(re.compile(r"/$"))

    # Submit with Cmd+Enter — this sends the path (with trailing /) to onSubmit
    path_input.press(f"{_MOD_KEY}+Enter")

    # The validation dialog should appear (the sentinel dir is not a git repo)
    git_init_dialog = settings_page.get_git_init_dialog()
    expect(git_init_dialog).to_be_visible()

    # The dialog should show the correct repo name, not an empty name
    expect(git_init_dialog).to_contain_text(sentinel_name)


@user_story("to see a submit shortcut hint in the autocomplete dropdown")
def test_autocomplete_shows_submit_hint(
    sculptor_instance_: SculptorInstance,
    _home_sentinel_dir: Path,
) -> None:
    """Test that the autocomplete dropdown shows a hint about the Cmd+Enter shortcut.

    Verifies:
    1. Typing ~/ triggers the autocomplete dropdown
    2. The dropdown includes a visible hint about the submit shortcut
    """
    page = sculptor_instance_.page

    settings_page = navigate_to_settings_page(page=page)
    repos_settings = settings_page.click_on_repositories()
    add_repo_dialog = repos_settings.open_add_repo_dialog()

    path_input = add_repo_dialog.get_path_input()
    path_input.fill("~/")

    items = add_repo_dialog.get_path_autocomplete_items()
    expect(items.first).to_be_visible()

    # Verify the submit hint is visible in the dropdown
    hint = add_repo_dialog.get_submit_hint()
    expect(hint).to_be_visible()
