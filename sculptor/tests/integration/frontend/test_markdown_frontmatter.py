"""Integration tests for YAML/TOML frontmatter rendering in `.md` files (SCU-951).

`ReadOnlyPreview` strips a leading frontmatter block before handing the
content to `react-markdown` and renders it as a styled metadata table
(`FrontmatterBlock`). Without this, the closing `---` underlines the
`key: value` lines into a setext `<h2>` — a visually-broken blob. These
tests pin two contracts:

* A `.md` file that opens with YAML frontmatter shows a metadata table with
  key/value rows, and the document body's own headings are untouched (the
  frontmatter never leaks in as a giant heading).
* The frontmatter block is a rendered-view affordance only — flipping the
  eye-toggle back to source removes it, so the raw `.md` (frontmatter and
  all) still shows verbatim.
"""

import re

from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# YAML frontmatter exercising the shapes a metadata table must handle: plain
# scalars, a boolean, a block-sequence (`tags`), and a nested mapping (`meta`).
# The body has exactly one heading so we can assert the frontmatter never
# becomes a heading of its own.
_FRONTMATTER_FILE_CONTENT = """\
---
title: Frontmatter Demo
author: Example Author
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


def _open_via_browse_tab(task_page: PlaywrightTaskPage, file_name: str) -> None:
    """Click a file in the Browse tab to open the read-only preview."""
    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    file_browser.get_tab_all().click()
    file_browser.get_tree_rows().filter(has_text=file_name).click()


@user_story("to see YAML frontmatter rendered as a styled metadata table instead of a broken heading")
def test_yaml_frontmatter_renders_as_metadata_block(sculptor_instance_: SculptorInstance) -> None:
    """A `.md` file that opens with YAML frontmatter shows a metadata table
    with key/value rows, and the body's own heading is the only heading."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        page, prompt=_write_file_via_fake_claude("frontmatter.md", _FRONTMATTER_FILE_CONTENT)
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(task_page, "frontmatter.md")
    diff_panel = task_page.get_diff_panel()
    diff_panel.ensure_render_mode("rendered")

    body = diff_panel.get_read_only_preview_markdown()
    expect(body).to_be_visible()

    # The metadata table renders the parsed key/value pairs. Block-sequence
    # values collapse to a comma-joined list; nested mappings fall back to
    # compact JSON.
    block = diff_panel.get_read_only_preview_frontmatter()
    expect(block).to_be_visible()
    for fragment in ("title", "Frontmatter Demo", "author", "Example Author", "draft", "false", "docs, internal"):
        expect(block).to_contain_text(fragment)
    expect(block).to_contain_text('{"level":2}')

    # The raw frontmatter lines never leak into the body as text; the body
    # paragraph does render.
    expect(body).not_to_contain_text("title: Frontmatter Demo")
    expect(body).to_contain_text("Body paragraph.")

    # Structural regression guard: the body's own heading rendered, and it is
    # the *only* heading — the frontmatter never became a setext `<h2>` and
    # never emitted a thematic rule. Read the HTML off the test-id'd body
    # because per-tag CSS selectors are banned in integration tests by the
    # `no-integration-css-locators` ratchet; the `<th>` cells in the metadata
    # table are not `<h1>`–`<h6>`.
    html = (body.inner_html() or "").lower()
    assert "<h1>real heading</h1>" in html, f"body heading missing: {html[:600]!r}"
    assert len(re.findall(r"<h[1-6]\b", html)) == 1, f"expected exactly one heading: {html[:800]!r}"
    assert "<hr" not in html, f"frontmatter rendered a thematic break: {html[:600]!r}"


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

    _open_via_browse_tab(task_page, "frontmatter.md")
    diff_panel = task_page.get_diff_panel()
    diff_panel.ensure_render_mode("rendered")
    expect(diff_panel.get_read_only_preview_frontmatter()).to_be_visible()

    diff_panel.ensure_render_mode("source")
    # Rendered-only affordances are gone; the source view (Pierre) is showing
    # the file verbatim, frontmatter and all.
    expect(diff_panel.get_read_only_preview_markdown()).to_have_count(0)
    expect(diff_panel.get_read_only_preview_frontmatter()).to_have_count(0)
    expect(diff_panel.get_read_only_preview()).to_be_visible()


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

    _open_via_browse_tab(task_page, "toml.md")
    diff_panel = task_page.get_diff_panel()
    diff_panel.ensure_render_mode("rendered")

    body = diff_panel.get_read_only_preview_markdown()
    expect(body).to_be_visible()
    block = diff_panel.get_read_only_preview_frontmatter()
    expect(block).to_be_visible()
    expect(block).to_contain_text('title = "Toml Demo"')

    # Body heading rendered and is the only heading (see the ratchet note in
    # the YAML test for why this reads HTML instead of CSS locators).
    html = (body.inner_html() or "").lower()
    assert "<h1>toml heading</h1>" in html, f"body heading missing: {html[:600]!r}"
    assert len(re.findall(r"<h[1-6]\b", html)) == 1, f"expected exactly one heading: {html[:800]!r}"
