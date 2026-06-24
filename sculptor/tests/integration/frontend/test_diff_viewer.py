"""Integration tests for the shared, embeddable per-panel DiffViewer (FCC-02/06/07).

Every Files / Changes / Commits panel embeds its OWN DiffViewer instance (FCC-02)
rather than reaching for a single page-wide "active diff" panel. This file
exercises that shared viewer ONCE — via whichever panel is convenient — so the
per-panel content files (`test_files_panel.py` etc.) only assert their own
list/sidebar behavior.

These cases are MIGRATED, not rewritten, from the pre-rewrite diff/markdown tests
(see `e2e_test_plan.md` §1). The proven content assertions carry over unchanged;
only the *surface* moved:

* a panel is opened through the section `+` add-panel dropdown (the 3.6a
  ``open_panel`` helper) instead of clicking File-Browser tabs;
* a file is opened into the panel's embedded viewer via the panel POM;
* the view toggles (split/unified, line wrap, render-markdown, find-in-file)
  re-anchored under the header's single triple-dot menu (FCC-07), reached via
  ``toggle_view_option_via_menu``;
* the empty/loading state asserts FCC-06 (the viewer is always visible with an
  empty body when nothing is selected; the loading bar shows only when a file is
  open).

The diff-specific fullscreen/expand surface is deprecated (section maximize
replaces it), so no expand/fullscreen assertions are migrated. The old multi-tab
diff surface ("Close other tabs") is likewise gone — each panel now hosts a
single-selection viewer with no diff tabs — so that test's tab-close kernel is
replaced by its FCC-02 analog (selecting a different file swaps the one viewer).

Migrated from:
* `test_diff_refresh_on_branch_change.py`
* `test_diff_tab_close_others.py`
* `test_diff_loading_bar_no_file.py`
* `test_markdown_render_toggle.py`
* `test_markdown_gfm.py`
* `test_open_in_viewer.py`
"""

import re
import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import open_panel
from sculptor.testing.elements.changes_panel import get_changes_panel_in
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.diff_viewer import PlaywrightDiffViewerElement
from sculptor.testing.elements.files_panel import get_files_panel_in
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# --------------------------------------------------------------------------- #
# FakeClaude prompts (migrated verbatim from the source tests).
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

WRITE_FILE_PROMPT = """\
fake_claude:write_file `{
  "file_path": "greeting.txt",
  "content": "Hello, world!\\nThis is a new file.\\n"
}`"""

EDIT_FILE_PROMPT = """\
fake_claude:edit_file `{
  "file_path": "greeting.txt",
  "old_string": "Hello, world!",
  "new_string": "Hi, everyone!"
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


def _set_rich_markdown_rendering_via_settings(page: Page, *, enabled: bool) -> None:
    """Set the experimental rich-markdown-rendering toggle in Settings →
    Experimental.

    The flag is server-persisted, so a previous test in the same browser
    context could leave it in either state — the POM helper reads the toggle's
    data-state and clicks only if needed. Call this *before*
    ``start_task_and_wait_for_ready``; that helper navigates back to the
    workspace flow on its own.
    """
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.set_rich_markdown_rendering(enabled=enabled)


def _ensure_render_mode(viewer: PlaywrightDiffViewerElement, page: Page, mode: str) -> None:
    """Drive the render-markdown toggle (now a checkbox item in the triple-dot
    menu, FCC-07) to ``mode`` (``rendered`` / ``source``).

    Effective mode is read from CONTENT — the rendered markdown wrapper is mounted
    only in rendered mode — rather than the menu checkbox's ``data-state`` (which is
    only in the DOM while the menu is open and tracks the preference, not the
    effective view). Idempotent — only toggles when the current view differs.
    """
    want_rendered = mode == "rendered"
    expect(viewer.get_read_only_preview()).to_be_visible()
    markdown = viewer.get_read_only_preview_markdown()
    # Settle before sampling: a fresh markdown file renders by default, but the
    # wrapper mounts a beat after the preview. Wait for it so a not-yet-mounted
    # wrapper isn't misread as "source" (which would toggle the wrong way).
    try:
        expect(markdown).to_be_visible(timeout=5_000)
        currently_rendered = True
    except AssertionError:
        currently_rendered = False
    if currently_rendered != want_rendered:
        viewer.toggle_view_option_via_menu("render")
    if want_rendered:
        expect(viewer.get_read_only_preview_markdown()).to_be_visible()
    else:
        expect(viewer.get_read_only_preview_markdown()).not_to_be_attached()


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


# --------------------------------------------------------------------------- #
# Migrated: test_diff_refresh_on_branch_change.py
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

    # Step 3: The Changes list should no longer show hello.py.
    # Allow up to 15 seconds for the branch polling (3s interval) to detect
    # the change and the frontend to clear + refetch the diff.
    expect(hello_row).to_be_hidden(timeout=15_000)


# --------------------------------------------------------------------------- #
# Migrated: test_diff_tab_close_others.py
#
# The pre-rewrite "Close other tabs" assertion exercised the multi-tab diff
# surface, which is deprecated in the FCC model: each panel now embeds ONE
# single-selection viewer with no diff tabs (FCC-02). The surviving behavioral
# kernel — selecting a different file replaces the single viewer's content —
# is migrated below; the tab-close context-menu assertion is dropped along with
# the deprecated surface (mirroring the dropped expand/fullscreen assertions).
# --------------------------------------------------------------------------- #


@user_story("to open each changed file into the same panel's embedded viewer")
def test_selecting_files_swaps_the_single_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Selecting different changed files swaps the one embedded viewer (FCC-02).

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

    # Selecting each file drives the SAME embedded viewer (FCC-02): the viewer
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
# Migrated: test_diff_loading_bar_no_file.py
#
# The FCC viewer is always visible with an empty body when nothing is selected
# (FCC-06), and the loading bar shows ONLY when a file is open and its diff is in
# flight. The pre-rewrite route-hold / close-tab dance targeted the OLD panel's
# workspace-level ``isFetching`` gating (SCU-1329) and the multi-tab surface,
# neither of which exists in the new single-viewer model. The surviving contract
# — no loading bar over the empty placeholder — is asserted directly.
# --------------------------------------------------------------------------- #


@user_story("to not see the diff loading bar when no file is open")
def test_diff_loading_bar_hidden_when_no_file_open(sculptor_instance_: SculptorInstance) -> None:
    """With a file written but nothing selected, the panel's viewer renders its
    empty body and shows NO loading bar (FCC-06)."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_HELLO_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Open the Changes panel; nothing is selected yet, so the viewer is in its
    # always-visible empty state (FCC-06).
    section_root = open_panel(page, "changes", sub_section="center")
    changes_panel = get_changes_panel_in(section_root, page)
    viewer = changes_panel.get_diff_viewer()

    # The viewer body is visible (empty placeholder), and there is NO loading
    # bar — even though opening the panel kicks off a background diff fetch.
    expect(viewer).to_be_visible()
    expect(viewer.get_loading_bar()).to_have_count(0)


# --------------------------------------------------------------------------- #
# Migrated: test_markdown_render_toggle.py
# --------------------------------------------------------------------------- #


@user_story("to toggle a markdown file between rendered and source views")
def test_markdown_toggle_switches_views(sculptor_instance_: SculptorInstance) -> None:
    """The render-markdown menu option should appear for `.md` files, default to
    rendered, and switch the visible view when clicked."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("notes.md")

    preview = viewer.get_read_only_preview()
    expect(preview).to_be_visible()

    # The render toggle (now a checkbox in the triple-dot menu, FCC-07) is present.
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
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

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


@user_story("to see a hint that rendered markdown is experimental when the flag is off")
def test_markdown_toggle_disabled_when_flag_off(sculptor_instance_: SculptorInstance) -> None:
    """When the `enable_rich_markdown_rendering` flag is off, the render-markdown
    toggle is rendered disabled (so the experimental feature is discoverable but
    unusable), the rendered DOM is not mounted, and the source view is shown
    instead — even when the persisted preference is "rendered"."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=False)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.open_file("notes.md")

    preview = viewer.get_read_only_preview()
    expect(preview).to_be_visible()

    # Toggle is mounted but disabled — discoverability for the experimental
    # opt-in. The persisted "rendered" preference is ignored: the effective view
    # is source (verified by content below), not the checkbox preference.
    viewer.open_menu()
    toggle = viewer.get_menu_option("render")
    expect(toggle).to_be_visible()
    expect(toggle).to_be_disabled()
    page.keyboard.press("Escape")

    # Source view is mounted; the rendered wrapper is not.
    expect(viewer.get_read_only_preview_markdown()).not_to_be_attached()
    expect(preview).to_contain_text("# Hello, World!")


# --------------------------------------------------------------------------- #
# Migrated: test_markdown_gfm.py
# --------------------------------------------------------------------------- #


@user_story("to see GFM tables, strikethrough, task lists, and autolinks rendered in the file viewer")
def test_gfm_features_render_in_read_only_preview(sculptor_instance_: SculptorInstance) -> None:
    """A `.md` file containing each GFM feature renders as the right
    semantic HTML in ``ReadOnlyPreview``."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

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
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

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
# Migrated: test_open_in_viewer.py
# --------------------------------------------------------------------------- #


@pytest.mark.skip(
    reason="open-from-chat → new FCC-panel routing not yet wired (no global diff panel target in the new shell). Follow-up."
)
@user_story("to open a created repo file in the diff viewer from the chat panel")
def test_open_created_file_in_diff_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Clicking 'View full diff' on a Write tool result opens the file's content
    in the viewer (not 'Could not load file content')."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_FILE_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Opening the chat chip's full diff brings the Files panel's viewer on screen
    # with the file selected. Open the panel via the harness so its embedded
    # viewer is in the DOM, then trigger the open-from-chat flow.
    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.get_diff_viewer()

    _open_diff_via_alpha_chip(chat_panel, "greeting.txt")

    # The viewer shows the file (not the load-failure placeholder).
    viewer.assert_diff_shows("greeting.txt")


@pytest.mark.skip(
    reason="open-from-chat → new FCC-panel routing not yet wired (see test_open_created_file_in_diff_viewer). Follow-up."
)
@user_story("to open an edited repo file in the diff viewer from the chat panel")
def test_open_edited_file_in_diff_viewer(sculptor_instance_: SculptorInstance) -> None:
    """Clicking 'View full diff' on an Edit tool result opens an actual diff view
    showing the changes (not a read-only full-file preview)."""
    page = sculptor_instance_.page

    # Step 1: Create the file.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=WRITE_FILE_PROMPT,
        wait_for_agent_to_finish=True,
    )
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Step 2: Edit the file in a follow-up turn.
    send_chat_message(chat_panel=chat_panel, message=EDIT_FILE_PROMPT)
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    # Step 3: Open the Files panel viewer and trigger the open-from-chat flow.
    section_root = open_panel(page, "files", sub_section="center")
    files_panel = get_files_panel_in(section_root, page)
    viewer = files_panel.get_diff_viewer()

    _open_diff_via_alpha_chip(chat_panel, "greeting.txt")

    # The viewer shows an actual diff view (unified or split), not a read-only
    # full-file preview.
    viewer.assert_diff_shows("greeting.txt")
    unified = viewer.get_unified_diff_views()
    split = viewer.get_split_view()
    expect(unified.or_(split)).to_be_visible(timeout=30_000)
    expect(viewer.get_read_only_preview()).to_have_count(0)
