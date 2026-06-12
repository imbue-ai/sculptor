"""Regression test for SCU-1298: arrow navigation must not open the skill menu.

The chat input's ``/`` skill picker is built on ``@tiptap/suggestion``, whose
plugin re-evaluates its trigger match on *every* transaction — including the
selection-only transactions produced by arrow-key navigation or a mouse click.
Because the leading ``/`` of a path such as ``/foo/bar`` is a valid trigger
(it sits at the start of the block, an allowed prefix), moving the caret into
that first ``/``-segment used to spring the skill-command popover open even
though the user never typed a command. From there an unsuspecting Enter would
"expand" the path into a slash-command chip.

The popover must only open in response to the user *typing* (a doc-changing
transaction); a pure cursor move must never open it. See ``SkillSuggestion``'s
``shouldShow`` guard and ``showSuggestionOnlyWhenTyping`` in ``SuggestionUtils``.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# A path whose first segment (``/foo``) is a valid skill trigger: the ``/`` is
# at the start of the block, and ``foo`` contains no whitespace. The second
# ``/`` is preceded by a non-space, so it is never a trigger on its own.
_PATH = "/foo/bar"


def _navigate_to_task_chat(sculptor_instance: SculptorInstance) -> PlaywrightTaskPage:
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance.page,
        prompt="Hello",
    )


@user_story("to move the caret through a path without the skill menu opening")
def test_arrow_navigation_into_path_does_not_open_skill_picker(sculptor_instance_: SculptorInstance) -> None:
    task_page = _navigate_to_task_chat(sculptor_instance_)

    chat_panel = task_page.get_chat_panel()
    chat_input = chat_panel.get_chat_input()
    mention_list = chat_panel.get_mention_list()

    # Positive control: typing "/" opens the skill picker (and warms the skill
    # cache so a later re-open would render without a network round-trip).
    type_trigger_char(chat_input, "/")
    expect(mention_list).to_be_visible()

    # Finish typing the path. The second "/" closes the picker, and typing the
    # remaining characters leaves the popover shut.
    chat_input.press_sequentially("foo/bar")
    expect(chat_input).to_contain_text(_PATH)
    expect(mention_list).not_to_be_visible()

    # Move the caret back into the leading "/foo" segment. Once the picker is
    # (wrongly) open it traps ArrowLeft, so pressing more times than needed is
    # harmless — the caret parks at the segment boundary either way.
    for _ in range(len(_PATH)):
        chat_input.press("ArrowLeft")

    # The regression: a pure cursor move must not reopen the skill picker.
    expect(mention_list).not_to_be_visible()
