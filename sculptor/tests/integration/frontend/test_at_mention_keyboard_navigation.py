"""Integration tests for arrow-key navigation in the @-mention suggestion popover.

The picker supports ArrowUp / ArrowDown to move the selection, and Enter to
commit the currently-selected row.  Without these assertions a regression
where the keyboard handler always committed the first item (or never fired
at all) would pass the other at-mention tests silently — each of them types
a query that is already narrow enough that the first match is the desired
one.
"""

from playwright.sync_api import Locator
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


def _clear_chat_input(page: Page, chat_input: Locator) -> None:
    """Select-all + Backspace via the platform's modifier key."""
    mod_key = get_playwright_modifier_key()
    chat_input.focus()
    page.keyboard.press(f"{mod_key}+a")
    page.keyboard.press("Backspace")


@user_story("to select a non-default file in the @-mention popover using arrow keys")
def test_arrow_down_changes_the_committed_item(sculptor_instance_: SculptorInstance) -> None:
    """Pressing ArrowDown before Enter commits a *different* chip than Enter alone.

    A regression where the keyboard handler silently always committed the
    first row (or ArrowDown was ignored) would pass every other at-mention
    test.  This test runs the picker twice from the same query:
    once with Enter only (default selection) and once with ArrowDown + Enter,
    then asserts the two editor states differ.
    """
    page = sculptor_instance_.page
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()
    mention_list = chat_panel.get_mention_list()

    # ``@src`` surfaces the ``src/`` folder and three files inside it. The
    # first item is the folder (exact filename match scores highest); the
    # second item is a file.  Enter on the folder drills into it; Enter on a
    # file commits the chip.  Two runs should produce different editor
    # outcomes.

    # Run 1: Enter only. Enter on the first item (src/ folder) rewrites the
    # query to ``@./src/`` and the popover stays open; dismiss with Escape
    # and capture the editor state.
    chat_input.press_sequentially("@src")
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().nth(1)).to_be_visible()
    chat_input.press("Enter")

    # After Enter-on-folder the query becomes "@./src/" (path mode). The
    # popover is still open. Escape it and record the editor text.
    page.keyboard.press("Escape")
    expect(mention_list).not_to_be_visible()
    run1_text = chat_input.inner_text()
    run1_has_chip = chat_panel.get_mention_spans().count() > 0

    _clear_chat_input(page, chat_input)
    expect(chat_input).to_have_text("")

    # Run 2: ArrowDown + Enter. ArrowDown advances to the second item (a file
    # inside src/), Enter commits it as a chip, and the popover closes.
    chat_input.press_sequentially("@src")
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().nth(1)).to_be_visible()
    chat_input.press("ArrowDown")
    chat_input.press("Enter")
    expect(mention_list).not_to_be_visible()

    run2_chip = chat_panel.get_mention_spans()
    expect(run2_chip).to_be_visible()
    expect(run2_chip.first).not_to_have_text("")
    run2_chip_text = run2_chip.first.inner_text()
    run2_text = chat_input.inner_text()

    # The two runs must produce different editor states. Concretely:
    #   - Run 1 ends with literal text "@./src/" (no chip), because Enter on
    #     the folder drilled in and we dismissed the popover.
    #   - Run 2 ends with a mention chip (a file inside src/).
    # If the keyboard handler was stuck on "first item always", run 2 would
    # also end at "@./src/" and no chip would exist.
    assert run1_text != run2_text, (
        "Enter-only and ArrowDown+Enter should differ."
        + f" run1={run1_text!r} (has chip: {run1_has_chip});"
        + f" run2={run2_text!r} (chip text: {run2_chip_text!r})"
    )


@user_story("to reset keyboard selection when the query changes")
def test_typing_additional_characters_resets_selection_to_first(sculptor_instance_: SculptorInstance) -> None:
    """Typing a character after moving selection resets it to the first row.

    The picker re-queries the items list on each keystroke, and
    ``SuggestionListContainer`` resets ``selectedIndex`` to the first
    selectable row when the items array identity changes.  Without the reset,
    Enter after narrowing the query could commit a stale row past the end of
    the new (shorter) list, or land on the wrong item.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    chat_input.press_sequentially("@s")
    expect(mention_list).to_be_visible()
    expect(chat_panel.get_mention_items().nth(2)).to_be_visible()

    # Move selection off the first row.
    chat_input.press("ArrowDown")
    chat_input.press("ArrowDown")

    # Narrow the query — the list now has far fewer matches, and selection
    # should reset to the first row.
    chat_input.press_sequentially("tuff")
    expect(chat_panel.get_mention_items().first).to_be_visible()
    # Wait for the narrowed list to render "stuff" as a match. This guards
    # against Enter firing before the items prop updates.
    expect(mention_list).to_contain_text("stuff")

    chat_input.press("Enter")
    expect(mention_list).not_to_be_visible()

    mention_span = chat_panel.get_mention_spans()
    expect(mention_span).to_be_visible()
    # After the selection reset, Enter commits the first row of the narrowed
    # list (``stuff.txt``).  Without the reset, the stale selectedIndex (2)
    # could land on an unrelated match.
    expect(mention_span).to_contain_text("stuff")
