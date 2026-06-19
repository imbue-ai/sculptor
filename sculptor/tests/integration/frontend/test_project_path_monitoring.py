"""Integration tests for project path monitoring functionality."""

import shutil

import pytest
from playwright.sync_api import expect

from sculptor.foundation.common import get_temp_dir
from sculptor.foundation.test_utils import create_temp_dir
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.mark.release
@pytest.mark.skip(reason="Flakey (PROD-2871) + workspace tabs migration (get_task_starter removed)")
@user_story("to be notified when the project directory is moved or deleted")
def test_project_path_monitoring(sculptor_instance_: SculptorInstance) -> None:
    home_page = sculptor_instance_

    # NOTE: this is necessary to ensure the project is activated
    # otherwise, there might be a race condition where the project activation fails because we move the project path
    # TODO: Replace with API-based workspace creation after workspace tabs migration
    task_starter = home_page.get_task_starter()  # type: ignore[attr-defined]
    task_starter.get_task_input().fill("Hello, world!")

    original_path = sculptor_instance_.repo.base_path

    with create_temp_dir(root_dir=get_temp_dir()) as temp_dir:
        moved_path = temp_dir / original_path.name
        shutil.move(str(original_path), str(moved_path))

        warning_banner_element = home_page.get_warning_banner()
        expect(warning_banner_element).to_be_visible()

        warning_banner_element.click_link()

        dialog = home_page.get_project_path_dialog()
        expect(dialog).to_be_visible()

        dialog.close()
        expect(dialog).not_to_be_visible()

        shutil.move(str(moved_path), str(original_path))

        expect(warning_banner_element).not_to_be_visible()
