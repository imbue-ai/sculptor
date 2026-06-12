"""Integration tests for the markdown render toggle in the read-only file preview.

The diff panel can show `.md` and `.markdown` files either as raw source (the
default Pierre/Shiki view) or as rendered HTML via react-markdown. The toggle
lives in the diff tab bar and is only visible when ReadOnlyPreview is the
active view (file-view tab or no-diff state) AND the active file is markdown.
"""

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

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


def _set_rich_markdown_rendering_via_settings(page: Page, *, enabled: bool) -> None:
    """Set the experimental rich-markdown-rendering toggle in Settings →
    Experimental.

    The flag is server-persisted, so a previous test in the same browser
    context could leave it in either state — read the toggle's data-state
    and click only if needed. Call this *before* ``start_task_and_wait_for_ready``;
    that helper navigates back to the workspace flow on its own.
    """
    settings_page = navigate_to_settings_page(page=page)
    experimental = settings_page.click_on_experimental()
    experimental.set_rich_markdown_rendering(enabled=enabled)


def _open_via_browse_tab(task_page: PlaywrightTaskPage, file_name: str) -> None:
    """Click a file in the Browse tab to open the read-only preview."""
    task_page.activate_file_browser()
    file_browser = task_page.get_file_browser()
    file_browser.get_tab_all().click()
    file_browser.get_tree_rows().filter(has_text=file_name).click()


@user_story("to toggle a markdown file between rendered and source views")
def test_markdown_toggle_switches_views(sculptor_instance_: SculptorInstance) -> None:
    """The eye toggle should appear for `.md` files in the read-only preview,
    default to rendered, and switch the visible view when clicked."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(task_page, "notes.md")

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    preview = diff_panel.get_read_only_preview()
    expect(preview).to_be_visible()

    # Toggle is visible and starts in "rendered" mode (the global default).
    toggle = diff_panel.get_render_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).to_have_attribute("data-state", "rendered")

    # Rendered view: the markdown wrapper is mounted and the heading text is
    # present without its leading "#" (which proves react-markdown consumed
    # the "#" as an h1 marker rather than rendering it as literal text).
    markdown_wrapper = diff_panel.get_read_only_preview_markdown()
    expect(markdown_wrapper).to_be_visible()
    expect(markdown_wrapper).to_contain_text("Hello, World!")
    expect(preview).not_to_contain_text("# Hello, World!")

    # Click toggle → source mode.
    toggle.click()
    expect(toggle).to_have_attribute("data-state", "source")
    expect(markdown_wrapper).not_to_be_attached()
    # In source mode the literal source (including the "#") is shown via Pierre.
    expect(preview).to_contain_text("# Hello, World!")

    # Click toggle → back to rendered.
    toggle.click()
    expect(toggle).to_have_attribute("data-state", "rendered")
    expect(diff_panel.get_read_only_preview_markdown()).to_be_visible()
    expect(preview).not_to_contain_text("# Hello, World!")


@user_story("to not see the markdown toggle on non-markdown files")
def test_markdown_toggle_hidden_for_non_markdown_files(sculptor_instance_: SculptorInstance) -> None:
    """The eye toggle must not appear when the active file is not markdown."""
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(task_page, "main.py")

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel.get_read_only_preview()).to_be_visible()
    expect(diff_panel.get_render_toggle()).not_to_be_attached()


@user_story("to not see the find-in-file button when viewing rendered markdown")
def test_find_in_file_button_hidden_in_rendered_markdown(sculptor_instance_: SculptorInstance) -> None:
    """Find-in-file walks the source DOM and can't see rendered markdown text;
    the button is hidden while rendered, then re-appears after switching to
    source."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=True)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(task_page, "notes.md")

    diff_panel = task_page.get_diff_panel()
    diff_panel.ensure_render_mode("rendered")
    expect(diff_panel.get_find_in_file_button()).not_to_be_attached()

    diff_panel.ensure_render_mode("source")
    expect(diff_panel.get_find_in_file_button()).to_be_visible()


@user_story("to see a hint that rendered markdown is experimental when the flag is off")
def test_markdown_toggle_disabled_when_flag_off(sculptor_instance_: SculptorInstance) -> None:
    """When the `enable_rich_markdown_rendering` flag is off, the eye toggle
    is rendered disabled (so the experimental feature is discoverable but
    unusable), the rendered DOM is not mounted, and the source view is
    shown instead — even when the persisted preference is "rendered"."""
    page = sculptor_instance_.page
    _set_rich_markdown_rendering_via_settings(page, enabled=False)

    task_page = start_task_and_wait_for_ready(page, prompt=_WRITE_MD_AND_PY_PROMPT)
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    _open_via_browse_tab(task_page, "notes.md")

    diff_panel = task_page.get_diff_panel()
    expect(diff_panel).to_be_visible()
    preview = diff_panel.get_read_only_preview()
    expect(preview).to_be_visible()

    # Toggle is mounted but disabled — discoverability for the experimental
    # opt-in. The persisted "rendered" preference is ignored, so data-state
    # reflects the effective (source) mode.
    toggle = diff_panel.get_render_toggle()
    expect(toggle).to_be_visible()
    expect(toggle).to_be_disabled()
    expect(toggle).to_have_attribute("data-state", "source")

    # Source view is mounted; the rendered wrapper is not.
    expect(diff_panel.get_read_only_preview_markdown()).not_to_be_attached()
    expect(preview).to_contain_text("# Hello, World!")
