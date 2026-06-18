import sys


def get_playwright_modifier_key() -> str:
    """Return the Playwright name for the platform's primary modifier key."""
    return "Meta" if sys.platform == "darwin" else "Control"
