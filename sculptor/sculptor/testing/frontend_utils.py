from playwright.sync_api import Page
from playwright.sync_api import expect

# Single source of truth for the browser viewport used by all integration tests.
# Also applied by _reset_browser_state between tests to undo any per-test resize
# that leaked out without being restored.
DEFAULT_TEST_VIEWPORT: dict[str, int] = {"width": 1600, "height": 1000}

# Pinned at the context level so navigator.language is a valid BCP 47 tag for
# every test. In production, real users always see a valid tag: Electron reads
# the OS locale (macOS NSLocale, Linux LANG/LC_ALL, Windows regional settings)
# and Chromium feeds it to navigator.language — no app code involved. CI
# offload sandboxes are minimal Linux containers with no LANG/LC_ALL set, so
# headless Chromium hands the renderer "" instead, and libraries that call
# `new Intl.Locale(navigator.language)` at module load (e.g.
# @tanstack/query-devtools via @kobalte/core) throw RangeError. Pinning here
# matches real-user behavior and inoculates the suite against the next library
# that does the same.
DEFAULT_TEST_LOCALE: str = "en-US"

# Default Playwright action/navigation timeout for integration tests, in milliseconds.
DEFAULT_TEST_TIMEOUT_MS: int = 30 * 1000


def configure_page(page: Page, timeout_ms: int = DEFAULT_TEST_TIMEOUT_MS) -> None:
    page.set_default_timeout(timeout_ms)
    page.set_default_navigation_timeout(timeout_ms)
    expect.set_options(timeout=timeout_ms)
