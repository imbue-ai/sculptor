from playwright.sync_api import Locator

from sculptor.constants import ElementIDs


def get_plan_checkmark(plan_item: Locator) -> Locator:
    """Get the checkmark element for a specific plan item."""
    return plan_item.get_by_test_id(ElementIDs.ARTIFACT_PLAN_CHECKMARK)
