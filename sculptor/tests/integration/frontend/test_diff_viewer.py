"""Integration tests for the shared, embeddable per-panel DiffViewer.

Every Files / Changes / Commits panel embeds its OWN DiffViewer instance
rather than reaching for a single page-wide "active diff" panel. This file
exercises that shared viewer ONCE — via whichever panel is convenient — so the
per-panel content files (`test_files_panel.py` etc.) only assert their own
list/sidebar behavior. A panel is opened through the section `+` add-panel
dropdown (the shared ``open_panel`` helper) and a file is opened into its
embedded viewer via the panel POM.

The view toggles (split/unified, line wrap, render-markdown, find-in-file) all
live under the header's single triple-dot menu, reached via
``toggle_view_option_via_menu``. The viewer is a single-selection surface: it
has no diff tabs and no expand/fullscreen affordance (section maximize covers
that), so selecting a different file swaps the one viewer's content in place.
When nothing is selected the viewer stays visible with an empty body and no
loading bar; the loading bar shows only while an open file's diff is in flight.

Coverage: branch-change diff refresh, single-viewer file swapping, the
empty/loading state, the markdown render toggle and its GFM / link-safety /
frontmatter rendering, opening a file's diff from a chat chip, the split/unified and
line-wrap toggles with persistence, find-in-file, copy-file-path for
outside-repo files, and the Shiki-decoration / Pierre ``renderHunks`` /
expansion-line-number guards.
"""

import re
import subprocess
from pathlib import Path
from uuid import uuid4

from playwright.sync_api import ConsoleMessage
from playwright.sync_api import Error
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.add_panel_dropdown import close_seeded_panel
from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.changes_panel import PlaywrightChangesPanelElement
from sculptor.testing.elements.changes_panel import get_changes_panel_in
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.clipboard import install_clipboard_interceptor
from sculptor.testing.elements.clipboard import read_intercepted_clipboard
from sculptor.testing.elements.clipboard import reset_intercepted_clipboard
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.diff_viewer import ensure_unified_view
from sculptor.testing.elements.diff_viewer import wait_for_full_content_diff_render
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.elements.workspace_section import PlaywrightWorkspaceSection
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# --------------------------------------------------------------------------- #
# FakeClaude prompts.
# --------------------------------------------------------------------------- #

_WRITE_HELLO_PROMPT = """\
fake_claude:write_file `{
  "file_path": "hello.py",
  "content": "print('hello')\\n"
}`"""

_THREE_FILES_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "alpha.py",
        "content": "a = 1\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "beta.py",
        "content": "b = 2\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "gamma.py",
        "content": "c = 3\\n"
      }
    }
  ]
}`"""

# Setup: write a markdown file plus a python file. The markdown file uses an
# H1 header so we can distinguish raw ("# Hello, World!") from rendered
# (an actual <h1> element with no leading "#").
_WRITE_MD_AND_PY_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "notes.md",
        "content": "# Hello, World!\\n\\nThis is a paragraph.\\n"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "main.py",
        "content": "print('hi')\\n"
      }
    }
  ]
}`"""

# Markdown content exercising every GFM feature called out in SCU-522,
# plus a fenced code block (guards the global `code { … }` rule in
# src/index.css from styling multi-line fences as inline pills), plus
# fragment + relative links (regression for the anchor click handling —
# fragment / relative clicks must not hijack the app router).
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

# YAML frontmatter exercising the shapes the metadata table must handle: plain
# scalars, a boolean, a block-sequence (`tags`), and a nested mapping (`meta`).
# The body has exactly one heading so tests can assert the frontmatter never
# becomes a heading of its own (SCU-951: without the frontmatter split, the
# closing `---` underlines the `key: value` lines into a setext `<h2>` — a
# visually-broken blob).
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

# TOML frontmatter (`+++` fences). It is detected and stripped so it never
# mis-renders, but not parsed into rows yet — it shows verbatim in the
# block as a raw fallback.
_TOML_FRONTMATTER_FILE_CONTENT = """\
+++
title = "Toml Demo"
draft = false
+++

# Toml heading

Body.
"""

_WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "greeting.txt",
  "content": "Hello, world!\\nThis is a new file.\\n"
}`"""

_EDIT_FILE_PROMPT = """\
fake_claude:edit_file `{
  "file_path": "greeting.txt",
  "old_string": "Hello, world!",
  "new_string": "Hi, everyone!"
}`"""

# Commit a file on a feature branch then edit it, so the Uncommitted scope shows
# a MODIFICATION diff. Split view only applies to modifications — added/deleted
# files always render unified (there is no "before"/"after" pair to compare).
_COMMIT_THEN_EDIT_MOD_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "mod.py",
        "content": "print('hello')\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add mod.py'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "mod.py",
        "old_string": "print('hello')",
        "new_string": "print('goodbye')"
      }
    }
  ]
}`"""

# A 200-line python file for the Shiki decoration regression. JSON newlines are
# represented as \\n in the prompt string.
_LONG_FILE_CONTENT = "\\n".join(f"x{i} = {i}" for i in range(200))

# Strategy: commit a 3-line file and a 200-line file, then edit one line of the
# short file and three widely-spaced lines of the long one. The uncommitted
# diffs are then a small single-hunk M and a multi-hunk M where Pierre must use
# oldLines/newLines to reconstruct unchanged regions between hunks for syntax
# highlighting. When the stale oldLines/newLines from the short file (~3 lines)
# are applied to the 200-line file, Shiki throws "Invalid decoration position"
# because decoration positions reference lines beyond the code length.
_SHIKI_REGRESSION_PROMPT = f"""\
fake_claude:multi_step `{{
  "steps": [
    {{
      "command": "bash",
      "args": {{
        "command": "git checkout -b feature"
      }}
    }},
    {{
      "command": "write_file",
      "args": {{
        "file_path": "short.py",
        "content": "a = 1\\nb = 2\\nc = 3\\n"
      }}
    }},
    {{
      "command": "write_file",
      "args": {{
        "file_path": "long.py",
        "content": "{_LONG_FILE_CONTENT}\\n"
      }}
    }},
    {{
      "command": "bash",
      "args": {{
        "command": "git add -A && git commit -m 'Add short and long files'"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "short.py",
        "old_string": "b = 2",
        "new_string": "b = 222"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "long.py",
        "old_string": "x5 = 5",
        "new_string": "x5 = 999"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "long.py",
        "old_string": "x100 = 100",
        "new_string": "x100 = 999"
      }}
    }},
    {{
      "command": "edit_file",
      "args": {{
        "file_path": "long.py",
        "old_string": "x195 = 195",
        "new_string": "x195 = 999"
      }}
    }}
  ]
}}`"""

# Setup: multi-line file with a unique marker on line 11. Line 7 is edited so
# the hunk covers lines 4-10 (3 context lines on each side). Lines 11+ lie
# outside the hunk and are rendered as Pierre expansion lines. When the
# frontend strips the trailing '\n' from the diff string, Pierre concatenates
# the last hunk line (line 10) directly with expansion line 11, causing Shiki
# to treat them as a single line; every subsequent line number is then off by
# one.
_LINE_NUMBER_REGRESSION_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "bash",
      "args": {
        "command": "git checkout -b feature"
      }
    },
    {
      "command": "write_file",
      "args": {
        "file_path": "multiline.py",
        "content": "line_01\\nline_02\\nline_03\\nline_04\\nline_05\\nline_06\\nline_07\\nline_08\\nline_09\\nline_10\\nafter_hunk_line_eleven\\nline_12\\nline_13\\nline_14\\nline_15\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Add multiline.py'"
      }
    },
    {
      "command": "edit_file",
      "args": {
        "file_path": "multiline.py",
        "old_string": "line_07",
        "new_string": "line_07_edited"
      }
    }
  ]
}`"""

# The mock repo's src/helpers.py is a 75-line module on main. Rewriting it to
# only the middle function group and committing produces a two-hunk
# vs-target-branch diff:
#   Hunk 1  @@ -1,32 +1,6 @@   — removes the add/subtract/.../cube group
#   Hunk 2  @@ -49,27 +23,3 @@ — removes the unique/chunk/format_name/truncate group
# with a 16-line gap (main lines 33-48) between the hunks. Pierre's
# context-expansion loop accesses oldLines[32]..oldLines[47] to fill that gap;
# when oldLines is incorrectly fetched from HEAD (25 lines) rather than from
# the target branch (75 lines), those accesses return undefined and Pierre
# crashes with "renderHunks: oldLine and newLine are null, something is wrong".
_SHORTEN_HELPERS_FILE_PROMPT = """\
fake_claude:multi_step `{
  "steps": [
    {
      "command": "write_file",
      "args": {
        "file_path": "src/helpers.py",
        "content": "# Helper utilities for the project.\\n\\n\\ndef is_even(n):\\n    return n % 2 == 0\\n\\n\\ndef is_odd(n):\\n    return n % 2 != 0\\n\\n\\ndef clamp(value, min_val, max_val):\\n    return max(min_val, min(max_val, value))\\n\\n\\ndef reverse_string(s):\\n    return s[::-1]\\n\\n\\ndef count_vowels(s):\\n    return sum(1 for c in s.lower() if c in 'aeiou')\\n\\n\\ndef flatten(nested):\\n    return [item for sublist in nested for item in sublist]\\n"
      }
    },
    {
      "command": "bash",
      "args": {
        "command": "git add -A && git commit -m 'Remove first and last function groups from helpers'"
      }
    }
  ]
}`"""

# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _get_workspace_working_dir(sculptor_instance: SculptorInstance) -> Path:
    """Find the clone workspace's working directory.

    After a workspace is created via the UI (clone mode), the clone lives at
    ``sculptor_folder / "workspaces" / env_id / "code"``.
    """
    workspaces_dir = sculptor_instance.sculptor_folder / "workspaces"
    code_dirs = sorted(workspaces_dir.glob("*/code"), key=lambda p: p.stat().st_mtime, reverse=True)
    assert code_dirs, f"No workspace clone found under {workspaces_dir}"
    return code_dirs[0]


def _write_file_via_fake_claude(file_path: str, content: str) -> str:
    """Build a fake_claude prompt that writes ``content`` to ``file_path``.

    The harness sends the prompt verbatim and parses the backtick-delimited
    body as JSON, so backslashes, double quotes, and newlines in ``content``
    have to be escaped to the JSON encoding before the prompt goes out."""
    escaped = content.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
    return f'fake_claude:multi_step `{{"steps": [{{"command": "write_file", "args": {{"file_path": "{file_path}", "content": "{escaped}"}}}}]}}`'


def _ensure_render_mode(viewer: PlaywrightDiffViewerElement, page: Page, mode: str) -> None:
    """Drive the render-markdown toggle (a flipping item in the triple-dot
    menu) to ``mode`` (``rendered`` / ``source``).

    Effective mode is read from CONTENT — the rendered markdown wrapper is mounted
    only in rendered mode — rather than the menu item's label (which is only in
    the DOM while the menu is open and tracks the preference, not the effective
    view). Idempotent — only toggles when the current view differs.
    """
    want_rendered = mode == "rendered"
    # Anchor on a deterministic baseline first: confirm the preview wrapper is
    # mounted with the default 30s timeout, so a slow mount is never misread.
    expect(viewer.get_read_only_preview()).to_be_visible()
    markdown = viewer.get_read_only_preview_markdown()
    # The markdown body and the source view are mutually exclusive branches of
    # the SAME render commit (ReadOnlyPreview's `shouldRenderMarkdown` gate), so
    # once the preview wrapper is visible the body's presence is already settled.
    # Read it as a stable attachment count rather than a shortened visibility
    # probe — the latter could mis-time a slow mount as "source" and toggle the
    # wrong way.
    currently_rendered = markdown.count() > 0
    if currently_rendered != want_rendered:
        viewer.toggle_view_option_via_menu("render")
    if want_rendered:
        expect(viewer.get_read_only_preview_markdown()).to_be_visible()
    else:
        expect(viewer.get_read_only_preview_markdown()).not_to_be_attached()


def _open_markdown_file_in_files_panel(page: Page, file_name: str, content: str) -> PlaywrightDiffViewerElement:
    """Create a workspace whose agent writes ``file_name``, open it via the Files
    panel, and return the panel's embedded viewer in rendered mode.

    Rendered markdown is the default view for ``.md`` files, so ``_ensure_render_mode``
    only has to confirm (and, after a prior test's toggle, restore) the rendered view.
    """
    task_page = start_task_and_wait_for_ready(page, prompt=_write_file_via_fake_claude(file_name, content))
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file(file_name)
    _ensure_render_mode(viewer, page, "rendered")
    return viewer


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


def _open_diff_via_alpha_chip(chat_panel: PlaywrightChatPanelElement, file_path: str) -> None:
    """Click the most-recent alpha file chip for `file_path` and open its full diff."""
    file_chip = chat_panel.get_file_chips().filter(has_text=file_path)
    expect(file_chip.last).to_be_visible()
    file_chip.last.click()

    popover = chat_panel.get_chip_popover()
    expect(popover).to_be_visible()
    chat_panel.get_chip_view_full_diff_button().click()


def _get_left_section_root(page: Page) -> Locator:
    """The left section's root, once the open-from-chat flow has revealed it.

    The chip's "View full diff" routes through ``setActiveDiffTabAtom``, which
    opens + expands the diff's HOST panel (Changes for repo diffs, Files for
    outside-repo file views) in the left section on its own — no ``open_panel``
    call is needed first.
    """
    section_root = PlaywrightWorkspaceSection(page, "left").get_section()
    expect(section_root).to_be_visible()
    return section_root


def _open_changes_panel_with(page: Page, prompt: str) -> PlaywrightChangesPanelElement:
    """Run a FakeClaude prompt, wait for it, then open the Changes panel."""
    task_page = start_task_and_wait_for_ready(page, prompt=prompt)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)
    section_root = open_panel(page, "changes", sub_section="center")
    return get_changes_panel_in(section_root, page)


def _select_uncommitted_scope(changes_panel: PlaywrightChangesPanelElement) -> None:
    """Switch the Changes scope picker to Uncommitted (the default is All)."""
    scope_uncommitted = changes_panel.get_scope_uncommitted()
    expect(scope_uncommitted).to_be_visible()
    scope_uncommitted.click()
    expect(scope_uncommitted).to_have_attribute("data-state", "on")


def _reopen_changes_panel_after_close(page: Page) -> PlaywrightChangesPanelElement:
    """Re-add the (closed) Changes panel from the left section's ``+`` dropdown.

    ``open_panel`` only REVEALS a seeded panel that is still open (it waits on
    the panel's tab), so re-adding after ``close_seeded_panel`` goes through the
    dropdown directly — a closed single-instance panel is back on its re-add list.
    """
    section = PlaywrightWorkspaceSection(page, "left")
    section.expand_section()
    dropdown = PlaywrightAddPanelDropdownElement(page, "left")
    dropdown.open()
    dropdown.select_panel("changes")
    expect(section.get_panel_tab("changes")).to_be_visible()
    section_root = section.get_section()
    expect(section_root).to_be_visible()
    return get_changes_panel_in(section_root, page)


def _ensure_line_wrap_enabled(viewer: PlaywrightDiffViewerElement, page: Page) -> None:
    """Drive the line-wrap preference to wrapping ON (the default).

    The preference is server-persisted, so a prior test can leave it either way.
    The menu item is a flipping label ("Wrap lines" while off / "Unwrap lines"
    while on), so the state is read from the label; clicking the item closes the
    menu, so the no-op branch dismisses it explicitly.
    """
    viewer.open_menu()
    wrap_item = viewer.get_menu_option("line_wrap")
    expect(wrap_item).to_be_visible()
    if "Wrap lines" in (wrap_item.text_content() or ""):
        wrap_item.click()
    else:
        page.keyboard.press("Escape")


def _get_copy_path_menu_item(page: Page) -> Locator:
    """The viewer header menu's "Copy file path" item.

    The per-file actions in the triple-dot menu carry their file-menu keys as
    raw testids (``copy-path`` etc.) rather than ``ElementIDs`` members, so the
    item is located page-wide by that key (the menu renders in a Radix portal
    and the viewer POM only maps the ``ElementIDs``-backed view options).
    """
    return page.get_by_test_id("copy-path")


def _wait_for_decorated_diff_line(page: Page, text: str) -> None:
    """Block until Pierre paints a decorated unified-diff line containing ``text``.

    Pierre paints the diff twice: first straight from the diff string, then again
    once ``useFileLines`` resolves and Shiki tokenises the file. Only that second
    pass emits ``div[data-line]`` nodes into the ``<diffs-container>`` shadow root,
    so a diff-string substring (an added/removed line) can already be on screen
    before the file-line fetch and decoration run. Poll the shadow root for a
    ``div[data-line]`` carrying ``text`` to wait past that decoration pass — the
    window in which stale line data surfaces as a Shiki error. The shadow root is
    pierced manually because ``data-line`` is a Pierre attribute with no
    Playwright locator equivalent.
    """
    page.wait_for_function(
        """({ testid, text }) => {
            const view = document.querySelector(`[data-testid="${testid}"]`);
            const shadow = view?.querySelector("diffs-container")?.shadowRoot;
            if (!shadow) return false;
            return [...shadow.querySelectorAll("div[data-line]")].some(
                (line) => line.textContent.includes(text)
            );
        }""",
        arg={"testid": ElementIDs.DIFF_VIEW_UNIFIED, "text": text},
    )


# --------------------------------------------------------------------------- #
# Branch-change diff refresh
# --------------------------------------------------------------------------- #


@user_story("to see the diff update when the current branch changes")
def test_diff_refreshes_when_current_branch_changes(sculptor_instance_: SculptorInstance) -> None:
    """The Changes list should update when the current branch changes.

    Steps:
    1. Agent writes hello.py — it appears in the Changes list.
    2. *Outside* the agent (directly on the filesystem), commit hello.py and
       check out a new branch at origin/main so the workspace has zero diff.
    3. The branch polling manager detects the branch change within 3 seconds
       and pushes a WebSocket update. The frontend should detect this, clear
       stale diff data, and refetch — making hello.py disappear from Changes.

    By performing the checkout outside the agent, ``on_diff_needed()`` does
    NOT fire, so the only path that can update the diff is the frontend
    detecting the branch change via the ``workspaceBranchAtomFamily`` atom.

    Opens the **Changes** panel because the assertion is scope-dependent: the
    file appears under the workspace diff and must disappear when the branch
    moves to a zero-diff checkout.
    """
    page = sculptor_instance_.page

    # Step 1: Create workspace (clone mode — the test relies on `origin/main`
    # being available in the workspace's checkout, which only exists in
    # clones) and have the agent write a file.
    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_HELLO_PROMPT, mode="CLONE")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes panel via the add-panel dropdown and verify hello.py is listed.
    section_root = open_panel(page, "changes", sub_section="center")
    changes_panel = get_changes_panel_in(section_root, page)
    hello_row = changes_panel.get_explorer_layout().get_tree_rows().filter(has_text="hello.py")
    expect(hello_row).to_be_visible()

    # Wait for branch polling to publish its baseline before changing the
    # branch externally. The polling callback's diff-refresh path only fires
    # on a branch *transition* (`repo_polling_manager.py` — requires
    # `_last_branch is not None`); the first poll fires 3s after the poller
    # starts, so without this wait, a fast checkout can beat the first poll
    # and set the baseline to the new branch — bypassing the refresh.
    task_page.get_branch_name_element()

    # Step 2: Commit and checkout *outside* the agent — no on_diff_needed().
    workspace_dir = _get_workspace_working_dir(sculptor_instance_)
    subprocess.run(
        ["git", "add", "hello.py"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-m", "Add hello"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "fresh-from-main", "origin/main"],
        cwd=workspace_dir,
        check=True,
        capture_output=True,
    )

    # Step 3: The Changes list should no longer show hello.py once the branch
    # polling (3s interval) detects the change and the frontend clears +
    # refetches the diff. This waits on an async WebSocket/poll-driven refresh,
    # not a performance bound, so rely on the default timeout (which already
    # budgets for the poll interval + WebSocket delivery + refetch).
    expect(hello_row).to_be_hidden()


# --------------------------------------------------------------------------- #
# Single-viewer file swapping
#
# Each panel embeds ONE single-selection viewer with no diff tabs: selecting a
# different file replaces the viewer's content in place rather than spawning a
# second viewer or a tab.
# --------------------------------------------------------------------------- #


@user_story("to open each changed file into the same panel's embedded viewer")
def test_selecting_files_swaps_the_single_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Selecting different changed files swaps the one embedded viewer.

    Steps:
    1. Create a workspace with 3 uncommitted files.
    2. Open the Changes panel.
    3. Click each file in turn; the panel's single viewer shows whichever file
       is selected (no second viewer / no diff tabs spawn).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_THREE_FILES_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "changes", sub_section="center")
    changes_panel = get_changes_panel_in(section_root, page)

    # Selecting each file drives the SAME embedded viewer: the viewer
    # header tracks whichever file is currently selected.
    viewer = changes_panel.open_file("alpha.py")
    viewer.assert_diff_shows("alpha.py")

    changes_panel.open_file("beta.py")
    viewer.assert_diff_shows("beta.py")

    changes_panel.open_file("gamma.py")
    viewer.assert_diff_shows("gamma.py")

    # There is exactly one embedded viewer for the panel — no diff tabs spawn.
    expect(viewer).to_have_count(1)


# --------------------------------------------------------------------------- #
# Empty / loading state
#
# The embedded viewer is always visible with an empty body when nothing is
# selected, and the loading bar shows ONLY when a file is open and its diff is
# in flight — never over the empty placeholder.
# --------------------------------------------------------------------------- #


@user_story("to not see the diff loading bar when no file is open")
def test_diff_loading_bar_hidden_when_no_file_open(sculptor_instance_: SculptorInstance) -> None:
    """With a file written but nothing selected, the panel's viewer renders its
    empty body and shows NO loading bar."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_HELLO_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes panel; nothing is selected yet, so the viewer is in its
    # always-visible empty state.
    section_root = open_panel(page, "changes", sub_section="center")
    changes_panel = get_changes_panel_in(section_root, page)
    viewer = changes_panel.get_diff_viewer()

    # The viewer body is visible (empty placeholder), and there is NO loading
    # bar — even though opening the panel kicks off a background diff fetch.
    expect(viewer).to_be_visible()
    # Wait for the empty-state body to actually render before the negative
    # check: the background diff fetch resolving into the empty placeholder is
    # the state under test, so the loading-bar assertion must run after it
    # settles rather than during the in-flight window.
    expect(viewer.get_empty_body()).to_be_visible()
    expect(viewer.get_loading_bar()).to_have_count(0)


# --------------------------------------------------------------------------- #
# Markdown render toggle
# --------------------------------------------------------------------------- #


@user_story("to toggle a markdown file between rendered and source views")
def test_markdown_toggle_switches_views(sculptor_instance_: SculptorInstance) -> None:
    """The render-markdown menu option should appear for `.md` files, default to
    rendered, and switch the visible view when clicked."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("notes.md")

    preview = viewer.get_read_only_preview()
    expect(preview).to_be_visible()

    # The render toggle (a checkbox in the triple-dot menu) is present.
    viewer.open_menu()
    expect(viewer.get_menu_option("render")).to_be_visible()
    page.keyboard.press("Escape")

    # Rendered view (the global default): the markdown wrapper is mounted and the
    # heading text is
    # present without its leading "#" (which proves react-markdown consumed
    # the "#" as an h1 marker rather than rendering it as literal text).
    markdown_wrapper = viewer.get_read_only_preview_markdown()
    expect(markdown_wrapper).to_be_visible()
    expect(markdown_wrapper).to_contain_text("Hello, World!")
    expect(preview).not_to_contain_text("# Hello, World!")

    # Toggle → source mode.
    viewer.toggle_view_option_via_menu("render")
    expect(markdown_wrapper).not_to_be_attached()
    # In source mode the literal source (including the "#") is shown via Pierre.
    expect(preview).to_contain_text("# Hello, World!")

    # Toggle → back to rendered.
    viewer.toggle_view_option_via_menu("render")
    expect(viewer.get_read_only_preview_markdown()).to_be_visible()
    expect(preview).not_to_contain_text("# Hello, World!")


@user_story("to not see the markdown toggle on non-markdown files")
def test_markdown_toggle_hidden_for_non_markdown_files(sculptor_instance_: SculptorInstance) -> None:
    """The render-markdown menu option must not appear when the active file is
    not markdown."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("main.py")

    expect(viewer.get_read_only_preview()).to_be_visible()
    viewer.open_menu()
    expect(viewer.get_menu_option("render")).not_to_be_attached()


@user_story("to not see the find-in-file option when viewing rendered markdown")
def test_find_in_file_option_hidden_in_rendered_markdown(sculptor_instance_: SculptorInstance) -> None:
    """Find-in-file walks the source DOM and can't see rendered markdown text;
    the menu option is hidden while rendered, then re-appears after switching to
    source."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("notes.md")

    _ensure_render_mode(viewer, page, "rendered")
    viewer.open_menu()
    expect(viewer.get_menu_option("find_in_file")).not_to_be_attached()
    page.keyboard.press("Escape")

    _ensure_render_mode(viewer, page, "source")
    viewer.open_menu()
    expect(viewer.get_menu_option("find_in_file")).to_be_visible()


# --------------------------------------------------------------------------- #
# Markdown GFM rendering + link safety
# --------------------------------------------------------------------------- #


@user_story("to see GFM tables, strikethrough, task lists, and autolinks rendered in the file viewer")
def test_gfm_features_render_in_read_only_preview(sculptor_instance_: SculptorInstance) -> None:
    """A `.md` file containing each GFM feature renders as the right
    semantic HTML in ``ReadOnlyPreview``."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_write_file_via_fake_claude("gfm.md", _GFM_FILE_CONTENT))
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("gfm.md")
    _ensure_render_mode(viewer, page, "rendered")

    body = viewer.get_read_only_preview_markdown()
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

    task_page = start_task_and_wait_for_ready(
        page, prompt=_write_file_via_fake_claude("unsafe.md", _UNSAFE_FILE_CONTENT)
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("unsafe.md")
    _ensure_render_mode(viewer, page, "rendered")

    body = viewer.get_read_only_preview_markdown()
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


# --------------------------------------------------------------------------- #
# Markdown frontmatter (SCU-951)
#
# `ReadOnlyPreview` strips a leading frontmatter block before handing the
# content to `react-markdown` and renders it as a styled metadata table.
# Without this, the closing `---` underlines the `key: value` lines into a
# setext `<h2>` — a visually-broken blob.
# --------------------------------------------------------------------------- #


@user_story("to see YAML frontmatter rendered as a styled metadata table instead of a broken heading")
def test_yaml_frontmatter_renders_as_metadata_block(sculptor_instance_: SculptorInstance) -> None:
    """A `.md` file that opens with YAML frontmatter shows a metadata table
    with key/value rows, and the body's own heading is the only heading."""
    page = sculptor_instance_.page
    viewer = _open_markdown_file_in_files_panel(page, "frontmatter.md", _FRONTMATTER_FILE_CONTENT)

    body = viewer.get_read_only_preview_markdown()
    expect(body).to_be_visible()

    # The metadata table renders the parsed key/value pairs. Block-sequence
    # values collapse to a comma-joined list; nested mappings fall back to
    # compact JSON.
    block = viewer.get_read_only_preview_frontmatter()
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
    viewer = _open_markdown_file_in_files_panel(page, "frontmatter.md", _FRONTMATTER_FILE_CONTENT)
    expect(viewer.get_read_only_preview_frontmatter()).to_be_visible()

    _ensure_render_mode(viewer, page, "source")
    # Rendered-only affordances are gone; the source view (Pierre) is showing
    # the file verbatim, frontmatter and all.
    expect(viewer.get_read_only_preview_markdown()).not_to_be_attached()
    expect(viewer.get_read_only_preview_frontmatter()).to_have_count(0)
    expect(viewer.get_read_only_preview()).to_be_visible()


@user_story("to see TOML frontmatter stripped to a tidy block instead of a broken heading")
def test_toml_frontmatter_renders_as_raw_block(sculptor_instance_: SculptorInstance) -> None:
    """TOML (`+++`) frontmatter is detected and stripped — it shows verbatim
    in the metadata block (no row parsing yet) and never leaks into the body
    as a heading."""
    page = sculptor_instance_.page
    viewer = _open_markdown_file_in_files_panel(page, "toml.md", _TOML_FRONTMATTER_FILE_CONTENT)

    body = viewer.get_read_only_preview_markdown()
    expect(body).to_be_visible()
    block = viewer.get_read_only_preview_frontmatter()
    expect(block).to_be_visible()
    expect(block).to_contain_text('title = "Toml Demo"')

    # Body heading rendered and is the only heading (see the ratchet note in
    # the YAML test for why this reads HTML instead of CSS locators).
    html = (body.inner_html() or "").lower()
    assert "<h1>toml heading</h1>" in html, f"body heading missing: {html[:600]!r}"
    assert len(re.findall(r"<h[1-6]\b", html)) == 1, f"expected exactly one heading: {html[:800]!r}"


# --------------------------------------------------------------------------- #
# Opening a file's diff from a chat chip
# --------------------------------------------------------------------------- #


@user_story("to open a created repo file in the diff viewer from the chat panel")
def test_open_created_file_in_diff_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Clicking 'View full diff' on a Write tool result reveals the Changes panel
    and opens the file's content in its embedded viewer (not 'Could not load
    file content')."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_WRITE_FILE_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_diff_via_alpha_chip(chat_panel, "greeting.txt")

    # A repo-file diff is hosted by the Changes panel: the open-from-chat flow
    # reveals it in the left section and its viewer shows the file (not the
    # load-failure placeholder).
    changes_panel = get_changes_panel_in(_get_left_section_root(page), page)
    viewer = changes_panel.get_diff_viewer()
    viewer.assert_diff_shows("greeting.txt")
    diff_body = viewer.get_unified_diff_views().or_(viewer.get_split_view())
    expect(diff_body).to_be_visible()
    expect(diff_body).to_contain_text("Hello, world!")


@user_story("to open an edited repo file in the diff viewer from the chat panel")
def test_open_edited_file_in_diff_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Clicking 'View full diff' on an Edit tool result opens an actual diff view
    showing the changes (not a read-only full-file preview)."""
    page = sculptor_instance_.page

    # Step 1: Create the file.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=_WRITE_FILE_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Step 2: Edit the file in a follow-up turn.
    send_chat_message(chat_panel=chat_panel, message=_EDIT_FILE_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Step 3: open the Edit chip's full diff; the flow reveals the Changes panel.
    _open_diff_via_alpha_chip(chat_panel, "greeting.txt")

    # The Changes panel's viewer shows an actual diff view (unified or split),
    # not a read-only full-file preview.
    changes_panel = get_changes_panel_in(_get_left_section_root(page), page)
    viewer = changes_panel.get_diff_viewer()
    viewer.assert_diff_shows("greeting.txt")
    unified = viewer.get_unified_diff_views()
    split = viewer.get_split_view()
    expect(unified.or_(split)).to_be_visible()
    expect(viewer.get_read_only_preview()).to_have_count(0)


# --------------------------------------------------------------------------- #
# Split/unified toggle + persistence
# --------------------------------------------------------------------------- #


@user_story("to compare files side-by-side")
def test_split_view_toggle(sculptor_instance_: SculptorInstance) -> None:
    """The split-view menu option switches a modification diff between unified
    and split views and back."""
    page = sculptor_instance_.page
    changes_panel = _open_changes_panel_with(page, _COMMIT_THEN_EDIT_MOD_PROMPT)

    _select_uncommitted_scope(changes_panel)
    viewer = changes_panel.open_file("mod.py")
    ensure_unified_view(viewer)

    # Toggle → split.
    viewer.toggle_view_option_via_menu("split_view")
    expect(viewer.get_split_view()).to_be_visible()
    expect(viewer.get_unified_diff_views()).to_have_count(0)

    # Toggle back → unified.
    viewer.toggle_view_option_via_menu("split_view")
    expect(viewer.get_unified_diff_views()).to_be_visible()
    expect(viewer.get_split_view()).to_have_count(0)


@user_story("to have my split view preference persist when closing and reopening the panel")
def test_split_view_toggle_persists_across_panel_reopen(sculptor_instance_: SculptorInstance) -> None:
    """The split/unified preference survives closing and reopening the host panel."""
    page = sculptor_instance_.page
    changes_panel = _open_changes_panel_with(page, _COMMIT_THEN_EDIT_MOD_PROMPT)

    _select_uncommitted_scope(changes_panel)
    viewer = changes_panel.open_file("mod.py")
    ensure_unified_view(viewer)

    viewer.toggle_view_option_via_menu("split_view")
    expect(viewer.get_split_view()).to_be_visible()

    # Close the Changes panel entirely, then re-add it and re-open the same file.
    close_seeded_panel(page, "changes")
    changes_panel = _reopen_changes_panel_after_close(page)
    _select_uncommitted_scope(changes_panel)
    viewer = changes_panel.open_file("mod.py")

    # Split mode persisted across the close/reopen.
    expect(viewer.get_split_view()).to_be_visible()
    expect(viewer.get_unified_diff_views()).to_have_count(0)

    # Restore unified — the preference is server-persisted, so leaving split on
    # would bleed into every later viewer test in this browser context.
    viewer.toggle_view_option_via_menu("split_view")
    expect(viewer.get_unified_diff_views()).to_be_visible()


# --------------------------------------------------------------------------- #
# Line-wrap toggle + persistence
# --------------------------------------------------------------------------- #


@user_story("to toggle line wrapping on and off in the diff view")
def test_line_wrap_toggle_flips_and_persists_across_panel_reopen(sculptor_instance_: SculptorInstance) -> None:
    """The line-wrap menu option flips the wrapping mode, and the mode survives
    closing and reopening the host panel.

    The menu item's flipping label is the observable state: it reads "Unwrap
    lines" while wrapping is on and "Wrap lines" while it is off.
    """
    page = sculptor_instance_.page
    changes_panel = _open_changes_panel_with(page, _WRITE_HELLO_PROMPT)

    viewer = changes_panel.open_file("hello.py")
    _ensure_line_wrap_enabled(viewer, page)

    # Toggle wrapping OFF; the label now offers to wrap again.
    viewer.toggle_view_option_via_menu("line_wrap")
    viewer.open_menu()
    expect(viewer.get_menu_option("line_wrap")).to_contain_text("Wrap lines")
    page.keyboard.press("Escape")

    # Close the Changes panel entirely, then re-add it and re-open the same
    # file: the scroll (no-wrap) mode persisted.
    close_seeded_panel(page, "changes")
    changes_panel = _reopen_changes_panel_after_close(page)
    viewer = changes_panel.open_file("hello.py")
    viewer.open_menu()
    wrap_item = viewer.get_menu_option("line_wrap")
    expect(wrap_item).to_contain_text("Wrap lines")

    # Restore wrapping (the default) so the server-persisted preference does not
    # bleed into later tests; the item click also closes the menu.
    wrap_item.click()
    viewer.open_menu()
    expect(viewer.get_menu_option("line_wrap")).to_contain_text("Unwrap lines")
    page.keyboard.press("Escape")


# --------------------------------------------------------------------------- #
# Find-in-file
# --------------------------------------------------------------------------- #


@user_story("to find text within an open file")
def test_find_in_file_finds_matches(sculptor_instance_: SculptorInstance) -> None:
    """The find-in-file menu option opens the search bar, reports matches from
    the diff content, and toggles back off."""
    page = sculptor_instance_.page
    changes_panel = _open_changes_panel_with(page, _WRITE_HELLO_PROMPT)

    viewer = changes_panel.open_file("hello.py")
    diff_body = viewer.get_unified_diff_views().or_(viewer.get_split_view())
    expect(diff_body).to_be_visible()

    # The search bar is hidden until requested.
    search_bar = viewer.get_search_bar()
    expect(search_bar).not_to_be_visible()

    viewer.toggle_view_option_via_menu("find_in_file")
    expect(search_bar).to_be_visible()

    # hello.py contains "hello" — the search reports "1 of N", not "No results".
    search_input = viewer.get_search_input()
    expect(search_input).to_be_visible()
    search_input.fill("hello")
    expect(search_bar).to_contain_text("1 of")

    # Toggling the option again closes the search bar.
    viewer.toggle_view_option_via_menu("find_in_file")
    expect(search_bar).not_to_be_visible()


# --------------------------------------------------------------------------- #
# Copy file path (absolute paths outside the repo)
# --------------------------------------------------------------------------- #


@user_story("to copy the correct path for a file outside the repo")
def test_copy_file_path_for_absolute_path_file(sculptor_instance_: SculptorInstance) -> None:
    """Copy file path returns the correct absolute path for files outside the repo.

    When the agent writes a file with an absolute path (outside the repo), the
    viewer's "Copy file path" must copy just that absolute path — not the repo
    path prepended to it.
    """
    page = sculptor_instance_.page

    # A per-test unique filename keeps concurrent xdist workers from sharing one
    # host /tmp path; the finally clause removes the file the agent writes there.
    outside_repo_path = f"/tmp/sculptor-test-outside-repo-{uuid4().hex}.txt"
    outside_repo_name = Path(outside_repo_path).name
    write_prompt = f"""\
fake_claude:write_file `{{
  "file_path": "{outside_repo_path}",
  "content": "This file lives outside the repo.\\n"
}}`"""

    try:
        task_page = start_task_and_wait_for_ready(page, prompt=write_prompt)
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        _open_diff_via_alpha_chip(chat_panel, outside_repo_name)

        # Outside-repo files route to a read-only file view hosted by the FILES
        # panel (there is no repo diff to show), revealed by the flow itself.
        files_panel = get_files_panel_in(_get_left_section_root(page), page)
        viewer = files_panel.get_diff_viewer()
        viewer.assert_diff_shows(outside_repo_name)

        install_clipboard_interceptor(page)
        viewer.open_menu()
        copy_path_item = _get_copy_path_menu_item(page)
        expect(copy_path_item).to_be_visible()
        reset_intercepted_clipboard(page)
        copy_path_item.click()

        page.wait_for_function("() => window.__clipboardWritten !== null")
        clipboard_value = read_intercepted_clipboard(page)
        assert clipboard_value == outside_repo_path, (
            f"Expected clipboard to contain {outside_repo_path!r}, got {clipboard_value!r}"
        )
    finally:
        Path(outside_repo_path).unlink(missing_ok=True)


# --------------------------------------------------------------------------- #
# Shiki decoration + Pierre renderHunks guards
# --------------------------------------------------------------------------- #


@user_story("to switch between diff files without seeing Shiki decoration errors")
def test_file_switch_no_shiki_decoration_error(sculptor_instance_: SculptorInstance) -> None:
    """Switching from a short modified file to a long multi-hunk one must not
    flash Shiki decoration errors.

    The bug only triggers for modified files (status "M") with multi-hunk diffs,
    where Pierre needs oldLines/newLines to reconstruct unchanged regions for
    syntax highlighting; stale lines from the previous (short) file make Shiki
    throw "Invalid decoration position".
    """
    page = sculptor_instance_.page

    console_errors: list[str] = []

    def _on_console(msg: ConsoleMessage) -> None:
        if msg.type == "error":
            console_errors.append(msg.text)

    page.on("console", _on_console)
    try:
        changes_panel = _open_changes_panel_with(page, _SHIKI_REGRESSION_PROMPT)
        _select_uncommitted_scope(changes_panel)

        # Open the short file first — this loads its oldLines/newLines (~3 lines).
        viewer = changes_panel.open_file("short.py")
        ensure_unified_view(viewer)
        viewer.assert_diff_shows("short.py")

        # The bug needs short.py's oldLines/newLines cached before the swap, so
        # wait for its decorated line to paint — the decoration pass is what
        # populates that line data. The diff header switching to "short.py" does
        # not prove the file-line fetch has resolved.
        _wait_for_decorated_diff_line(page, "b = 222")

        # Switch to the long file — the selection swap that triggers the bug.
        changes_panel.open_file("long.py")
        viewer.assert_diff_shows("long.py")

        # Applying the stale ~3-line short.py lines to the 200-line file is what
        # raises the Shiki error, so wait for the long file's last edited line to
        # finish its decoration pass before reading the captured errors.
        _wait_for_decorated_diff_line(page, "x195 = 999")

        # The bug: stale short.py lines (~3) + long.py diff (200 lines) →
        # ShikiError: Invalid decoration position.
        shiki_errors = [e for e in console_errors if "ShikiError" in e or "Invalid decoration" in e]
        assert shiki_errors == [], f"Shiki decoration errors during file switch: {shiki_errors}"
    finally:
        # The page is shared across the session; leave its listener set clean.
        page.remove_listener("console", _on_console)


@user_story("to view committed changes to an existing file in the All scope diff")
def test_all_scope_diff_renders_without_error_for_committed_file(sculptor_instance_: SculptorInstance) -> None:
    """Opening a committed file in the "All" scope renders without a Pierre crash.

    When the workspace branch has committed changes to a file that also exists
    in the target branch (main), opening that file in the All scope
    (vs-target-branch) must not crash Pierre with "renderHunks: oldLine and
    newLine are null, something is wrong". The crash requires a two-hunk diff
    with a context-expansion gap between the hunks AND a HEAD that has fewer
    lines than the merge-base-aligned indices the gap loop accesses — the shape
    ``_SHORTEN_HELPERS_FILE_PROMPT`` builds from the mock repo's 75-line
    src/helpers.py.
    """
    page = sculptor_instance_.page

    # Capture uncaught JS exceptions AND console errors — Pierre catches the
    # renderHunks crash internally and reports it as a console error.
    js_errors: list[str] = []

    def _on_page_error(error: Error) -> None:
        js_errors.append(error.message)

    def _on_console(msg: ConsoleMessage) -> None:
        if msg.type == "error":
            js_errors.append(msg.text)

    page.on("pageerror", _on_page_error)
    page.on("console", _on_console)
    try:
        changes_panel = _open_changes_panel_with(page, _SHORTEN_HELPERS_FILE_PROMPT)

        # The All scope (vs-target-branch) is the default; opening helpers.py — 25
        # lines on HEAD but 75 on main — takes the two-hunk render path that crashed.
        scope_all = changes_panel.get_scope_all()
        expect(scope_all).to_have_attribute("data-state", "on")

        viewer = changes_panel.open_file("src/helpers.py")
        ensure_unified_view(viewer)

        # The crash fires during Pierre's full-content render pass — once
        # oldLines/newLines arrive, its merge-base-aligned hunk indices can read
        # past a too-short array. The hunks' own lines paint from the diff
        # string alone (first pass) and would let the read fire too early, and
        # the 16-line gap between the hunks stays a COLLAPSED separator
        # (expandUnchanged is off), so gap-only text like count_vowels never
        # paints at all. Anchor instead on the full-content pass's signature —
        # an expandable separator — plus the last hunk's final deleted line, so
        # the whole risky pass has run before the captured errors are read.
        wait_for_full_content_diff_render(page, "return text[:max_length - 3]")

        # The crash message names Pierre's renderer: "renderHunks" in older
        # @pierre/diffs releases, "DiffHunksRenderer" in 1.2.x.
        render_hunks_errors = [e for e in js_errors if "renderHunks" in e or "DiffHunksRenderer" in e]
        assert not render_hunks_errors, f"Pierre renderHunks crash: {render_hunks_errors[0]}"
    finally:
        # The page is shared across the session; leave its listener set clean.
        page.remove_listener("pageerror", _on_page_error)
        page.remove_listener("console", _on_console)


# --------------------------------------------------------------------------- #
# Expansion-line numbering (data-line)
# --------------------------------------------------------------------------- #


@user_story("to see correct line numbers for expansion lines beyond the last diff hunk")
def test_diff_view_shows_correct_line_numbers(sculptor_instance_: SculptorInstance) -> None:
    """Lines after the last hunk's 3-context-line window render as Pierre
    expansion lines drawn from the full file content. Stripping the trailing
    newline from the diff string makes Pierre concatenate the last hunk line
    with the first expansion line; Shiki then treats the two as one line,
    shifting every subsequent line number by one. Every line must carry the
    correct number."""
    page = sculptor_instance_.page

    changes_panel = _open_changes_panel_with(page, _LINE_NUMBER_REGRESSION_PROMPT)
    _select_uncommitted_scope(changes_panel)

    viewer = changes_panel.open_file("multiline.py")
    ensure_unified_view(viewer)

    # "after_hunk_line_eleven" is on file line 11, just outside the hunk's
    # 3-line context window (the hunk covers lines 4-10). Pierre renders inside
    # a shadow DOM (<diffs-container>), so the per-line check pierces it via
    # page.evaluate — data-line is a Pierre attribute with no Playwright API
    # equivalent (read-only DOM inspection, not state manipulation). The
    # container can be visible before the shadow content finishes rendering
    # (Shiki tokenisation is async), so poll until a div[data-line] appears.
    testid = ElementIDs.DIFF_VIEW_UNIFIED
    page.wait_for_function(
        """(testid) => {
            const dv = document.querySelector(`[data-testid="${testid}"]`);
            const shadow = dv?.querySelector("diffs-container")?.shadowRoot;
            return shadow?.querySelectorAll("div[data-line]").length > 0;
        }""",
        arg=testid,
    )
    result = page.evaluate(
        """(testid) => {
            const diffView = document.querySelector(`[data-testid="${testid}"]`);
            if (!diffView) return { error: "no-diff-view" };
            const shadow = diffView.querySelector("diffs-container")?.shadowRoot;
            if (!shadow) return { error: "no-shadow-root" };
            const divs = shadow.querySelectorAll("div[data-line]");
            for (const div of divs) {
                if (div.textContent.includes("line_10")) {
                    return {
                        dataLine: div.getAttribute("data-line"),
                        merged: div.textContent.includes("after_hunk_line_eleven"),
                        text: div.textContent.substring(0, 200),
                    };
                }
            }
            return { error: "line_10-not-found", divCount: divs.length };
        }""",
        testid,
    )
    assert isinstance(result, dict) and "error" not in result, f"Could not locate line_10 in the diff view: {result}"
    assert not result["merged"], (
        f"Last hunk line (data-line={result['dataLine']}) merged with expansion line 11: {result['text']!r};"
        + " the trailing newline was likely stripped from the diff string."
    )
