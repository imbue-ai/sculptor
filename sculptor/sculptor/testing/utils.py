import sys

from playwright.sync_api import Page


def get_playwright_modifier_key() -> str:
    """Return the Playwright name for the platform's primary modifier key."""
    return "Meta" if sys.platform == "darwin" else "Control"


def wait_for_keyboard_drag_listeners(page: Page) -> None:
    """Wait until a dnd-kit keyboard drag that just started is listening for keys.

    dnd-kit's KeyboardSensor marks the drag active synchronously on Space, so drag flags
    such as ``data-sidebar-dragging`` appear at once, but it attaches the keydown listener
    that handles arrows, Space and Escape from a zero-delay ``setTimeout``. A key pressed
    in between is dropped: an arrow never moves the drag and an Escape leaves it stuck.
    Timers with equal delays run in the order they were set, so a zero-delay timer set
    now fires only after dnd-kit's, by which point the listener is attached.
    """
    page.evaluate("() => new Promise((resolve) => setTimeout(resolve))")
