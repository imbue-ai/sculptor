"""TipTap's bullet-list shortcut must not fire on the ``+`` mention trigger.

TipTap's built-in BulletList extension treats ``+ ``, ``* ``, and ``- `` at
line start as a markdown shortcut to start a bullet list. The ``+`` mention
picker shares its trigger character with that shortcut, so without an
explicit fix the user would see a bullet list spawn under the cursor any
time they typed ``+`` followed by a space — and the picker would still try
to open against an editor that's now in list mode.

The fix in ``TipTapConfig.ts`` swaps the default ``BulletList`` for a
CustomBulletList that drops ``+`` from its input rule. This test guards that
fix from silently regressing if the BulletList extension ever changes its
trigger set or the custom override is removed.
"""

from playwright.sync_api import expect

from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to type '+ ' at the start of a chat input line without converting it to a bullet list")
def test_plus_space_at_line_start_does_not_create_bullet_list(
    sculptor_instance_: SculptorInstance,
) -> None:
    """``+ `` at line start must produce literal text, not a bullet list.

    The TipTap default BulletList input rule treats ``+ ``/``* ``/``- `` at
    line start as markdown shortcuts. Sculptor's CustomBulletList overrides
    that rule to drop ``+`` from the trigger set so it can be used as a
    mention trigger instead. A regression here would surprise users by
    spawning a list under the cursor every time they typed ``+`` for a
    mention, and the picker would open against an editor that's already
    been mutated into list mode.
    """
    task_page = _navigate_to_task_chat(sculptor_instance_)
    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    expect(chat_input).to_be_visible()

    # Type ``+`` to surface the picker, then dismiss it so the next keystroke
    # is processed by the editor (not consumed by the suggestion plugin).
    chat_input.press_sequentially("+")
    picker = chat_panel.get_mention_list()
    expect(picker).to_be_visible()
    chat_input.press("Escape")
    expect(picker).not_to_be_visible()

    # Type the space that would have completed the markdown shortcut. With
    # the default bullet-list rule, this would convert the ``+`` into a
    # ``<ul><li>`` and clear the cursor's leading character. With the fix,
    # the ``+ `` survives as plain text.
    chat_input.press_sequentially(" hello")

    # The chat input must still contain the literal ``+`` we typed; if the
    # bullet-list shortcut had fired, the ``+`` would have been replaced by
    # a list-item marker and the visible text would be ``hello`` only — the
    # ``+`` character would have been consumed by the input rule. The unit
    # test in ``TipTapMarkdown.test.ts`` ("CustomBulletList — bullet-list
    # shortcut on + is disabled") covers the JSON-shape side of this; this
    # assertion guards the user-visible text round-trip.
    expect(chat_input).to_contain_text("+ hello")
