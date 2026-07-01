"""Integration tests for YAML/TOML frontmatter rendering in `.md` files (SCU-951).

`ReadOnlyPreview` strips a leading frontmatter block before handing the
content to `react-markdown` and renders it as a styled metadata panel
(`FrontmatterBlock`). Without this, the closing `---` underlines the
`key: value` lines into a setext `<h2>` — a visually-broken blob. These
tests pin two contracts:

* A `.md` file that opens with YAML frontmatter shows a metadata block with
  key/value rows, and the document body's own headings are untouched (the
  frontmatter never leaks in as a giant heading).
* The frontmatter block is a rendered-view affordance only — flipping the
  eye-toggle back to source removes it, so the raw `.md` (frontmatter and
  all) still shows verbatim.
"""

import re

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# YAML frontmatter exercising the shapes a metadata block must handle: plain
# scalars, a boolean, a block-sequence (`tags`), and a nested mapping (`meta`).
# The body has exactly one heading so we can assert the frontmatter never
# becomes a heading of its own.
_FRONTMATTER_FILE_CONTENT = """\
---
title: Frontmatter Demo
author: Ada Lovelace
draft: false
tags:
  - docs
  - internal
meta:
  level: 2
---

# Real heading

Body paragraph.
"""

# TOML frontmatter (`+++` fences). We detect and strip it so it never
# mis-renders, but don't parse it into rows yet — it shows verbatim in the
# block as a raw fallback.
_TOML_FRONTMATTER_FILE_CONTENT = """\
+++
title = "Toml Demo"
draft = false
+++

# Toml heading

Body.
"""


def _write_file_via_fake_claude(file_path: str, content: str) -> str:
    """Build a fake_claude prompt that writes ``content`` to ``file_path``.

    The harness sends the prompt verbatim and parses the backtick-delimited
    body as JSON, so backslashes, double quotes, and newlines in ``content``
    have to be escaped to the JSON encoding before the prompt goes out."""
    escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'fake_claude:multi_step `{{"steps": [{{"command": "write_file", "args": {{"file_path": "{file_path}", "content": "{escaped}"}}}}]}}`'


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


@user_story("to see YAML frontmatter rendered as a styled metadata block instead of a broken heading")
def test_yaml_frontmatter_renders_as_metadata_block(sculptor_instance_: SculptorInstance) -> None:
    """A `.md` file that opens with YAML frontmatter shows a metadata block
    with key/value rows, and the body's own heading is the only heading."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_write_file_via_fake_claude("frontmatter.md", _FRONTMATTER_FILE_CONTENT)
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(page, "frontmatter.md")
    _ensure_render_mode(page, "rendered")

    body = page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)
    expect(body).to_be_visible()

    # The metadata block renders the parsed key/value pairs.
    block = page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_FRONTMATTER)
    expect(block).to_be_visible()
    block_text = block.text_content() or ""
    for fragment in ("title", "Frontmatter Demo", "author", "Ada Lovelace", "draft", "false"):
        assert fragment in block_text, f"metadata block missing {fragment!r}: {block_text!r}"
    # Block-sequence values collapse to a comma-joined list; nested mappings
    # fall back to compact JSON.
    assert "docs, internal" in block_text, f"list value not joined: {block_text!r}"
    assert '{"level":2}' in block_text, f"nested mapping not shown as JSON: {block_text!r}"

    html = (body.inner_html() or "").lower()
    text = body.text_content() or ""

    # The body's own heading rendered, and it is the *only* heading — the
    # frontmatter never became a setext `<h2>`.
    assert "<h1>real heading</h1>" in html, f"body heading missing: {html[:600]!r}"
    heading_count = len(re.findall(r"<h[1-6]\b", html))
    assert heading_count == 1, f"expected exactly one heading (the body's), got {heading_count}: {html[:800]!r}"
    # The raw frontmatter delimiters / lines never leak into the rendered
    # markdown body as a thematic rule + paragraph.
    assert "<hr" not in html, f"frontmatter rendered a thematic break: {html[:600]!r}"
    assert "title: Frontmatter Demo" not in text, f"raw frontmatter line leaked into body: {text!r}"
    assert "Body paragraph." in text, f"body paragraph missing: {text!r}"


@user_story("to keep the raw frontmatter visible when I switch the markdown file back to source view")
def test_frontmatter_block_is_rendered_view_only(sculptor_instance_: SculptorInstance) -> None:
    """The metadata block exists only in rendered view; flipping to source
    removes both it and the rendered markdown body, so the raw `.md`
    (frontmatter included) shows verbatim through the source renderer."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_write_file_via_fake_claude("frontmatter.md", _FRONTMATTER_FILE_CONTENT)
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(page, "frontmatter.md")
    _ensure_render_mode(page, "rendered")
    expect(page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_FRONTMATTER)).to_be_visible()

    _ensure_render_mode(page, "source")
    # Rendered-only affordances are gone; the source view (Pierre) is showing
    # the file verbatim, frontmatter and all.
    expect(page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_FRONTMATTER)).to_have_count(0)
    expect(page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW)).to_be_visible()


@user_story("to see TOML frontmatter stripped to a tidy block instead of a broken heading")
def test_toml_frontmatter_renders_as_raw_block(sculptor_instance_: SculptorInstance) -> None:
    """TOML (`+++`) frontmatter is detected and stripped — it shows verbatim
    in the metadata block (no row parsing yet) and never leaks into the body
    as a heading."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_write_file_via_fake_claude("toml.md", _TOML_FRONTMATTER_FILE_CONTENT)
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(page, "toml.md")
    _ensure_render_mode(page, "rendered")

    body = page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_MARKDOWN)
    expect(body).to_be_visible()
    block = page.get_by_test_id(ElementIDs.READ_ONLY_PREVIEW_FRONTMATTER)
    expect(block).to_be_visible()
    assert 'title = "Toml Demo"' in (block.text_content() or ""), "raw TOML not shown verbatim in block"

    html = (body.inner_html() or "").lower()
    assert "<h1>toml heading</h1>" in html, f"body heading missing: {html[:600]!r}"
    heading_count = len(re.findall(r"<h[1-6]\b", html))
    assert heading_count == 1, f"expected exactly one heading, got {heading_count}: {html[:800]!r}"
