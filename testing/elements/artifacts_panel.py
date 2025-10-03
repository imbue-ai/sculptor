from playwright.sync_api import Locator

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import PlaywrightIntegrationTestElement
from sculptor.testing.elements.diff_artifact import PlaywrightDiffArtifactElement
from sculptor.testing.elements.plan_artifact import PlaywrightPlanArtifactElement


class PlaywrightArtifactsPanelElement(PlaywrightIntegrationTestElement):
    def get_combined_diff_tab(self) -> Locator:
        """Get the combined diff tab in the artifacts panel."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_COMBINEDDIFF_TAB)

    def get_combined_diff_section(self) -> PlaywrightDiffArtifactElement:
        """Get the combined diff artifact section element."""
        diff_section = self.get_by_test_id(ElementIDs.ARTIFACT_COMBINEDDIFF_SECTION)
        return PlaywrightDiffArtifactElement(locator=diff_section, page=self._page)

    def get_plan_tab(self) -> Locator:
        """Get the plan tab in the artifacts panel."""
        return self.get_by_test_id(ElementIDs.ARTIFACT_PLAN_TAB)

    def get_plan_section(self) -> PlaywrightPlanArtifactElement:
        """Get the plan artifact section element."""
        plan_section = self.get_by_test_id(ElementIDs.ARTIFACT_PLAN_SECTION)
        return PlaywrightPlanArtifactElement(locator=plan_section, page=self._page)
