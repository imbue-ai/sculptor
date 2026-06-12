import sys


def get_playwright_modifier_key() -> str:
    return "Meta" if sys.platform == "darwin" else "Control"
