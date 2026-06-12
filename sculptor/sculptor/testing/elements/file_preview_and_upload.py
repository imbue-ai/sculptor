from typing import Callable
from typing import Sequence

from playwright.sync_api import Locator
from playwright.sync_api import expect

from sculptor.constants import ElementIDs


class PlaywrightFilePreviewAndUploadMixin:
    get_by_test_id: Callable[[ElementIDs], Locator]

    def attach_files(self, files: str | Sequence[str]) -> None:
        """Attach a file to the task starter form.

        Note: The file input is hidden and accessed directly rather than clicking the button.
        """
        file_input = self.get_by_test_id(ElementIDs.FILE_UPLOAD)
        file_input.set_input_files(files)

    def get_file_previews(self) -> Locator:
        """Get all file preview containers in the task starter."""
        return self.get_by_test_id(ElementIDs.FILE_PREVIEW)

    def get_preview_containers(self) -> Locator:
        """Get all preview containers in the task starter."""
        return self.get_by_test_id(ElementIDs.FILE_PREVIEW_CONTAINER)

    def remove_file(self, index: int) -> None:
        """Remove an image from the task starter form."""
        container = self.get_preview_containers().nth(index)
        container.hover()
        remove_button = container.get_by_test_id(ElementIDs.FILE_PREVIEW_REMOVE)
        expect(remove_button).to_be_visible()
        remove_button.click()
