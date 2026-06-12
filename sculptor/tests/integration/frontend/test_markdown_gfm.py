"""Integration tests for GFM rendering in `.md` files (SCU-522).

`ReadOnlyPreview` enables `remark-gfm` for `.md` content via the shared
plugin policy in `sculptor/frontend/src/components/MarkdownDiff/`. These
tests pin two contracts:

* GFM features (tables, strikethrough, task lists, autolinks, fenced code
  blocks) render as the right semantic HTML.
* Hostile markdown (raw `<script>`, `javascript:` hrefs, raw `<img
  onerror>`) is neutralised before it reaches the DOM.

We assert against the rendered HTML via ``inner_html()`` / ``text_content()``
because the markdown body has a single test ID; the elements *inside* it are
generic semantic HTML emitted by react-markdown and don't carry per-element
test IDs.
"""

import re

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# Markdown content exercising every GFM feature called out in SCU-522,
# plus a fenced code block (regression for the global `code { … }` rule in
# src/index.css that previously made multi-line fences look like inline
# pills), plus fragment + relative links (regression for the anchor click
# handling — fragment / relative clicks must not hijack the app router).
_GFM_FILE_CONTENT = """\
# GFM showcase

[Jump to install](#install) or read the [neighbor doc](./other.md).

This paragraph has ~~struck-through~~ words.

Visit https://example.com for details. See also [the docs](https://example.org/docs).

| Name | Score |
| ---- | ----- |
| Ada  | 9     |
| Bob  | 7     |

- [ ] open task
- [x] done task

```python
def hello():
    print("hi")
    return 1
```

## Install
"""

# Hostile content: a `<script>` tag (must not execute and must not appear in
# DOM as a script element), a `javascript:` link (href must be neutralised),
# and an `<img onerror=...>` (must not get an event handler attached).
_UNSAFE_FILE_CONTENT = """\
# Untrusted file

<script>window.__sculptor_pwn = 1;</script>

[Click me](javascript:alert('xss'))

<img src="x" onerror="window.__sculptor_pwn = 2">
"""


def _write_file_via_fake_claude(file_path: str, content: str) -> str:
    """Build a fake_claude prompt that writes ``content`` to ``file_path``.

    The harness sends the prompt verbatim and parses the backtick-delimited
    body as JSON, so backslashes, double quotes, and newlines in ``content``
    have to be escaped to the JSON encoding before the prompt goes out."""
    escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'fake_claude:multi_step `{{"steps": [{{"command": "write_file", "args": {{"file_path": "{file_path}", "content": "{escaped}"}}}}]}}`'


def _set_rich_markdown_rendering_via_settings(page: Page, *, enabled: bool) -> None:
    """Toggle the rich-markdown-rendering experimental flag in Settings →
    Experimental, matching the helper in ``test_markdown_render_toggle.py``."""
    settings_page = navigate_to_settings_page(page=page)
    settings_page.get_by_test_id(ElementIDs.SETTINGS_NAV_EXPERIMENTAL).click()
    toggle = settings_page.get_by_test_id(ElementIDs.SETTINGS_ENABLE_RICH_MARKDOWN_RENDERING_TOGGLE)
    expect(toggle).to_be_visible()
    target_state = "checked" if enabled else "unchecked"
    if toggle.get_attribute("data-state") != target_state:
        toggle.click()
    expect(toggle).to_have_attribute("data-state", target_state)


def _ensure_file_browser_visible(page: Page) -> None:
    file_browser = page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
    if not file_browser.is_visible():
        page.get_by_test_id(ElementIDs.PANEL_ICON_FILES).click()
        expect(file_browser).to_be_visible()


def _open_via_browse_tab(page: Page, file_name: str) -> None:
    """Click a file in the Browse tab to open the read-only preview."""
    _ensure_file_browser_visible(page)
    page.get_by_test_id(ElementIDs.FILE_BROWSER_TAB_ALL).click()
    file_browser = page.get_by_test_id(ElementIDs.FILE_BROWSER_PANEL)
    file_browser.get_by_test_id(ElementIDs.FILE_BROWSER_TREE_ROW).filter(has_text=file_name).click()
    expect(page.get_by_test_id(ElementIDs.DIFF_PANEL)).to_be_visible()


def _ensure_render_mode(page: Page, mode: str) -> None:
    toggle = page.get_by_test_id(ElementIDs.DIFF_RENDER_TOGGLE)
    expect(toggle).to_be_visible()
    if toggle.get_attribute("data-state") != mode:
        toggle.click()
    expect(toggle).to_have_attribute("data-state", mode)


def _assert_gfm_features_present(body: Locator) -> None:
    """Assert every GFM feature in ``_GFM_FILE_CONTENT`` rendered correctly.

    Reads ``inner_html()`` once and runs substring / regex checks because
    the rendered elements (table cells, ``<del>``, checkbox ``<input>``,
    autolink ``<a>``) don't carry test IDs — they're plain semantic HTML
    emitted by react-markdown."""
    html = (body.inner_html() or "").lower()
    text = body.text_content() or ""

    # Heading consumed → "# GFM showcase" never leaks into rendered text.
    assert "GFM showcase" in text, f"heading missing from text: {text!r}"
    assert "# GFM showcase" not in text, "heading marker leaked into rendered text"

    # Table cell content rendered as actual cells.
    assert "<table>" in html or "<table " in html, f"<table> missing: {html[:600]!r}"
    assert "<th>name</th>" in html, "table header cell missing"
    assert "<th>score</th>" in html, "table header cell missing"
    assert "<td>ada" in html, "table body cell missing"
    assert "<td>bob" in html, "table body cell missing"
    assert "| Name | Score |" not in text, "table source leaked into rendered text"

    # Strikethrough → real <del>.
    assert "<del>struck-through</del>" in html or "<del>struck-through<" in html, (
        f"strikethrough not rendered as <del>: {html[:600]!r}"
    )
    assert "~~struck-through~~" not in text, "strikethrough source leaked into rendered text"

    # Task list: two checkboxes, the second one checked.
    checkbox_count = html.count('type="checkbox"')
    assert checkbox_count == 2, f"expected 2 checkboxes, got {checkbox_count}: {html[:600]!r}"
    # `checked=""` is what mdast-util-to-hast emits for a checked input.
    checked_count = html.count('checked=""') + html.count(" checked>") + html.count(" checked ")
    assert checked_count == 1, f"expected exactly one checked task box, got {checked_count}: {html[:800]!r}"

    # Autolink → <a href="https://example.com">.
    assert 'href="https://example.com"' in html, f"autolink href missing: {html[:600]!r}"

    # Multi-line code fence → one <pre><code> with all three lines preserved
    # (not split into per-line inline pills by the global `code { … }` rule).
    assert "<pre>" in html, f"<pre> wrapper missing: {html[:800]!r}"
    pre_count = html.count("<pre>")
    assert pre_count == 1, f"expected exactly one <pre>, got {pre_count}"
    assert "def hello():" in text and 'print("hi")' in text and "return 1" in text, (
        f"code fence body missing from rendered text: {text!r}"
    )

    # Link-safety regression. Three contracts (matching anchorBehavior.ts):
    #   1. External anchors (URL has a scheme) MUST carry `target="_blank"`
    #      + `rel="noopener noreferrer"`. Sculptor's `setWindowOpenHandler`
    #      (src/electron/main.ts) only intercepts target=_blank new-window
    #      requests; without them the click navigates the Electron
    #      BrowserWindow away from the React app.
    #   2. Fragment-only anchors (TOC links like `#install`) MUST NOT carry
    #      target=_blank. Sculptor's own router uses URL fragments, so a
    #      bare `<a href="#install">` click would change `location.hash`
    #      and eject the user from the current view. The override calls
    #      `preventDefault()`.
    #   3. Relative-path anchors (`./other.md`) MUST NOT carry target=_blank
    #      either — that would route the click to `shell.openExternal`,
    #      which would fail to resolve a relative path against the
    #      dev-server URL. Same `preventDefault()` keeps them inert.
    anchor_tags = re.findall(r"<a [^>]*>", html)
    fragment_tags = [t for t in anchor_tags if 'data-link-kind="fragment"' in t]
    relative_tags = [t for t in anchor_tags if 'data-link-kind="relative"' in t]
    external_tags = [t for t in anchor_tags if 'data-link-kind="external"' in t]
    # Every anchor in file-markdown must be tagged by MarkdownAnchor — the
    # CSS hooks that differentiate the three kinds (external icon, fragment
    # icon, dashed underline) all key off `data-link-kind`.
    assert len(anchor_tags) == len(fragment_tags) + len(relative_tags) + len(external_tags), (
        f"every anchor must carry data-link-kind; missing on {anchor_tags!r}"
    )
    assert len(fragment_tags) == 1, (
        f"expected exactly one fragment anchor (#install), got {len(fragment_tags)}: {anchor_tags!r}"
    )
    assert len(relative_tags) == 1, (
        f"expected exactly one relative-path anchor (./other.md), got {len(relative_tags)}: {anchor_tags!r}"
    )
    assert len(external_tags) >= 2, (
        f"expected at least 2 external anchors (autolink + markdown link), got {len(external_tags)}: {anchor_tags!r}"
    )
    for tag in fragment_tags + relative_tags:
        assert "target=" not in tag and "rel=" not in tag, (
            f"internal anchor must not carry target/rel attributes (would hijack the app shell): {tag!r}"
        )
        # The two unsupported kinds carry a default `title` tooltip
        # explaining the limitation — caller-provided titles would
        # override, but the GFM fixture doesn't set any.
        assert "title=" in tag, f"unsupported anchor must carry a 'not supported yet' title: {tag!r}"
    for tag in external_tags:
        assert 'target="_blank"' in tag, f"external anchor missing target=_blank: {tag!r}"
        assert 'rel="noopener noreferrer"' in tag, f"external anchor missing rel=noopener noreferrer: {tag!r}"


@user_story("to see GFM tables, strikethrough, task lists, and autolinks rendered in the file viewer")
def test_gfm_features_render_in_read_only_preview(sculptor_instance_: SculptorInstance) -> None:
    """A `.md` file containing each GFM feature renders as the right
    semantic HTML in ``ReadOnlyPreview``."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

    task_page = start_task_and_wait_for_ready(page, prompt=_write_file_via_fake_claude("gfm.md", _GFM_FILE_CONTENT))
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(page, "gfm.md")
    _ensure_render_mode(page, "rendered")

    body = page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)
    expect(body).to_be_visible()
    _assert_gfm_features_present(body)


@user_story("to keep raw HTML, javascript: links, and inline event handlers out of rendered markdown")
def test_unsafe_markdown_is_neutralised_in_read_only_preview(
    sculptor_instance_: SculptorInstance,
) -> None:
    """Hostile `.md` content must not execute scripts, navigate to
    ``javascript:`` URLs, or inject DOM nodes outside the markdown
    sandbox."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

    task_page = start_task_and_wait_for_ready(
        page, prompt=_write_file_via_fake_claude("unsafe.md", _UNSAFE_FILE_CONTENT)
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(page, "unsafe.md")
    _ensure_render_mode(page, "rendered")

    body = page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)
    expect(body).to_be_visible()
    html = (body.inner_html() or "").lower()

    # `react-markdown` renders raw HTML as escaped text (`&lt;script&gt;…`),
    # so the literal substrings `onerror=` and `<script>` show up in the
    # *text* but not as real tags or attributes. The checks below match on
    # real-tag shape (unescaped `<…>`) rather than on substrings.
    assert re.search(r"<script\b", html) is None, f"raw <script> reached the DOM as an element: {html[:600]!r}"
    # `safeUrlTransform` returns "" for `javascript:`, so the anchor renders
    # with no href. The literal substring can't appear anywhere because raw
    # HTML is entity-encoded.
    assert "javascript:" not in html, f"javascript: URL leaked: {html[:600]!r}"
    # No real `<img …>` element gets created (the hostile fixture only has
    # raw HTML, which gets escaped to `&lt;img&gt;` text).
    assert re.search(r"<img\b", html) is None, f"raw <img> reached the DOM as an element: {html[:600]!r}"
    # No real element should carry an `onerror=` attribute.
    assert re.search(r"<[^<>]*\bonerror\s*=", html) is None, f"onerror attribute is on a real element: {html[:600]!r}"
