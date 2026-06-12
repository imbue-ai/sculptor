"""Regression test: Terminal links should open the actual URL, not about:blank.

Bug: The xterm.js WebLinksAddon default handler calls ``window.open()`` with no
URL (opens about:blank), then sets ``location.href`` on the new window.  In
Electron, ``setWindowOpenHandler`` intercepts the initial ``window.open()`` call,
sees "about:blank", passes it to ``shell.openExternal``, and denies the window
creation — so the real URL never opens.

Root cause: WebLinksAddon's default handler uses a two-step open pattern for
reverse-tabnapping prevention (open blank window, null opener, then navigate).
This is incompatible with Electron's ``setWindowOpenHandler``.

Fix: Provide a custom handler to ``WebLinksAddon`` that passes the URL directly
to ``window.open(url, '_blank')``.

NOTE: This test uses JS evaluation because xterm.js renders to a canvas
(no DOM elements to query) and we need to intercept ``window.open`` calls.
We replace ``window.open`` with ``console.log()`` so Playwright's console
event listener can capture the URL without timeouts.  We use console.log
instead of alert() because Electron shows native OS dialogs for alert()
which Playwright cannot intercept via CDP.
"""

import pytest

from sculptor.testing.elements.base import type_with_delay
from sculptor.testing.elements.terminal import get_terminal_textarea
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@pytest.mark.electron
@user_story("to click a URL in the terminal and have it open in my browser")
def test_terminal_link_opens_correct_url(sculptor_instance_: SculptorInstance) -> None:
    """Clicking a URL in the terminal should call window.open with the actual URL.

    Steps:
    1. Create a workspace and open the terminal panel
    2. Echo a URL into the terminal so xterm detects it as a link
    3. Replace window.open with alert(), register a Playwright dialog handler,
       find the URL position, and click it
    4. Assert the dialog fired with the actual URL (not about:blank)
    """
    page = sculptor_instance_.page
    test_url = "https://example.com/test-link"

    # Step 1: Create workspace and open terminal
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    # Step 2: Echo a URL into the terminal and wait for it to appear in the buffer
    terminal_textarea = get_terminal_textarea(page)
    terminal_textarea.focus()
    type_with_delay(terminal_textarea, f"echo {test_url}", 30)
    terminal_textarea.press("Enter")

    page.wait_for_function(
        """(testUrl) => {
            const b = window.__xterm?.buffer.active;
            if (!b) return false;
            for (let i = b.baseY + b.cursorY; i >= 0; i--) {
                const l = b.getLine(i);
                if (!l) continue;
                const t = l.translateToString(true);
                if (t.includes(testUrl) && !t.includes('echo ' + testUrl)) return true;
            }
            return false;
        }""",
        arg=test_url,
    )

    # Step 3: Replace window.open with console.log so Playwright's console
    # event listener can capture the URL — no timeouts needed.  We use
    # console.log instead of alert() because Electron shows native OS dialogs
    # for alert() which Playwright cannot intercept via CDP.
    click_info = page.evaluate(  # noqa: E501
        """(testUrl) => {
        // Replace window.open with console.log so Playwright can intercept it
        const MARKER = "__TERMINAL_LINK_OPENED__:";
        window.open = function(url) { console.log(MARKER + url); return null; };

        const xterm = window.__xterm;
        if (!xterm) return null;

        const buffer = xterm.buffer.active;

        // Find the row containing the echoed URL output (not the command line).
        let targetRow = -1;
        let colStart = -1;
        for (let i = buffer.baseY + buffer.cursorY; i >= 0; i--) {
            const line = buffer.getLine(i);
            if (!line) continue;
            const text = line.translateToString(true);
            const idx = text.indexOf(testUrl);
            if (idx !== -1 && !text.includes("echo " + testUrl)) {
                targetRow = i;
                colStart = idx;
                break;
            }
        }

        if (targetRow === -1 || colStart === -1) return null;

        // Get cell dimensions from xterm's render service
        const dims = xterm._core._renderService.dimensions;
        const cellWidth = dims.css.cell.width;
        const cellHeight = dims.css.cell.height;

        // Calculate the viewport-relative row
        const viewportRow = targetRow - buffer.viewportY;

        // Get the terminal container's position on the page
        const container = xterm.element;
        if (!container) return null;
        const rect = container.getBoundingClientRect();

        // Click position: middle of the URL text, vertically centered in the row
        const urlMidCol = colStart + testUrl.length / 2;
        const x = rect.left + urlMidCol * cellWidth;
        const y = rect.top + (viewportRow + 0.5) * cellHeight;

        return { x: Math.round(x), y: Math.round(y) };
    }""",
        test_url,
    )

    assert click_info is not None, "Could not find URL position in terminal buffer"

    # Step 4: Listen for the console message, click the link, and assert the URL.
    marker = "__TERMINAL_LINK_OPENED__:"
    with page.expect_event(
        "console",
        predicate=lambda msg: msg.text.startswith(marker),
    ) as console_info:
        page.mouse.click(click_info["x"], click_info["y"])

    opened_url = console_info.value.text.removeprefix(marker)
    assert opened_url == test_url, (
        f"window.open was called with {opened_url!r} instead of {test_url!r}."
        + " The WebLinksAddon handler is not passing the URL to window.open()."
    )
