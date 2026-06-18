import re

from sculptor.testing.elements.base import PlaywrightIntegrationTestElement


class PlaywrightCompactionBarElement(PlaywrightIntegrationTestElement):
    def get_context_remaining(self) -> int:
        """Parse the remaining context percentage from the button's aria-label.

        The context indicator is an SVG arc button with aria-label like "85% context remaining".
        """
        aria_label = self.get_attribute("aria-label") or ""
        match = re.search(r"(\d+)% context remaining", aria_label)
        if match is None:
            raise ValueError(f"Could not parse context remaining from aria-label: {aria_label!r}")
        return int(match.group(1))
