import re

from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightCompactionBarElement(PlaywrightIntegrationTestElement):
    def get_context_remaining(self) -> int:
        compaction_text = self.text_content()
        remaining_percentage = re.search(r"(\d+)% Context Remaining", compaction_text)
        return int(remaining_percentage.group(1))
