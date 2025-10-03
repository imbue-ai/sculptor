from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.committed_diff import PlaywrightCommittedDiffElement
from sculptor.testing.elements.uncommitted_diff import PlaywrightUncommittedDiffElement


class PlaywrightDiffArtifactElement(PlaywrightIntegrationTestElement):
    def get_uncommitted_section(self) -> PlaywrightUncommittedDiffElement:
        """Get the uncommitted changes section element."""
        locator = self.get_by_test_id(ElementIDs.ARTIFACT_UNCOMMITTED_SECTION)
        return PlaywrightUncommittedDiffElement(locator, self._page)

    def get_committed_section(self) -> PlaywrightCommittedDiffElement:
        """Get the committed changes section element."""
        locator = self.get_by_test_id(ElementIDs.ARTIFACT_COMMITTED_SECTION)
        return PlaywrightCommittedDiffElement(locator, self._page)
