"""Integration test for the in-app TanStack Query devtools panel.

Regression test for SCU-1322. The default `@tanstack/react-query-devtools`
entry replaces `ReactQueryDevtoolsPanel` with `() => null` whenever
`process.env.NODE_ENV !== "development"`. Integration tests serve the
production bundle (Vite's `npm run build` defaults to NODE_ENV=production),
so the bug reproduces here unless we import from the package's explicit
`/production` entry.
"""

from __future__ import annotations

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


@user_story("to use the in-app TanStack Query devtools panel from the version popover")
def test_tanstack_devtools_panel_mounts_with_content(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page

    page.get_by_test_id(ElementIDs.VERSION).click()
    expect(page.get_by_test_id(ElementIDs.VERSION_POPOVER_CONTENT)).to_be_visible()

    page.get_by_test_id(ElementIDs.VERSION_POPOVER_TANSTACK_DEVTOOLS_SWITCH).click()

    # Our wrapper renders unconditionally once the toggle is on — that alone
    # only proves our chrome mounted, not that the package's panel did.
    panel_host = page.get_by_test_id(ElementIDs.TANSTACK_DEVTOOLS_PANEL_HOST)
    expect(panel_host).to_be_visible()

    # The "TANSTACK" brand text is rendered by the package's devtools header
    # whenever the real `<ReactQueryDevtoolsPanel>` mounts. The production-build
    # no-op shim returns `null`, so the brand text is never present — making it
    # the most direct signal that distinguishes the bug from the fix.
    expect(panel_host).to_contain_text("TANSTACK")
