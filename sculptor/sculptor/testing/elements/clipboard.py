"""Clipboard interception helpers for integration tests.

Playwright does not provide a native API for reading clipboard content in
Electron apps.  These helpers use page.evaluate() to mock the clipboard API
and retrieve what was written — the only viable approach for testing copy
functionality in our desktop app context.

NOTE: These functions use page.evaluate(), which is an exception to our rule
against using page.evaluate() in integration tests.  Playwright has no native
API for reading the clipboard in Electron, so we must inject a mock.
"""

from playwright.sync_api import Page


def install_clipboard_interceptor(page: Page) -> None:
    """Install a mock ``clipboard.writeText()`` that captures written text.

    After calling this, any code that calls ``navigator.clipboard.writeText()``
    will store the text in ``window.__clipboardWritten`` instead of writing to
    the system clipboard.  Use :func:`read_intercepted_clipboard` to retrieve
    the value.
    """
    page.evaluate("""() => {
        window.__clipboardWritten = null;
        navigator.clipboard.writeText = (text) => {
            window.__clipboardWritten = text;
            return Promise.resolve();
        };
    }""")


def reset_intercepted_clipboard(page: Page) -> None:
    """Reset the captured clipboard value so the next write can be detected.

    Call this before triggering a copy action when a previous copy may have
    already populated ``window.__clipboardWritten``.  After reset, you can
    use ``page.wait_for_function("() => window.__clipboardWritten !== null")``
    to wait for the new write to land.
    """
    page.evaluate("() => { window.__clipboardWritten = null; }")


def read_intercepted_clipboard(page: Page) -> str | None:
    """Read the value captured by the clipboard interceptor.

    Returns the text that was last written via ``navigator.clipboard.writeText()``,
    or ``None`` if nothing has been written since the interceptor was installed.
    """
    return page.evaluate("() => window.__clipboardWritten")
