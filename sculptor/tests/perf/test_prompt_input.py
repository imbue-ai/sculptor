"""Perf scenario: typing into the prompt input (the chat editor).

Unlike the switch/send scenarios, the measured action is *typing* — a burst
of individual keystrokes into the Tiptap editor. The invariant this guards is
that keystrokes cost ~O(1), not O(N): the input toolbar should not re-render
once per character. The optimization this guards makes ChatInput *write* the
draft atom without *subscribing* to it, so typing updates the draft without
re-rendering the toolbar — this scenario measures exactly that surface.

Pure frontend: no Fake Claude round-trip, no network in the window. Fast and
deterministic — a good candidate for a fast, run-on-every-PR lane.

Parametrized over blend only (no warm/cold: typing has no cache dimension):
  - empty:      type into an empty editor.
  - long_draft: type into an editor that already holds a long draft — catches
                per-keystroke work that scales with existing content
                (O(N^2)-ish reconciliation).
"""

from collections.abc import Callable

import pytest
from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.base import type_into_tiptap
from sculptor.testing.elements.chat_panel import PlaywrightChatPanelElement
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.perf.collector import MeasurementRecorder
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

# The burst typed inside the measurement window. Kept ASCII and free of Tiptap
# special chars (no ``/`` command trigger, no ``@`` mention, no markdown) so the
# scenario measures plain keystroke cost, not autocomplete/parsing surfaces
# (those get their own blends later). ~30 chars is enough to separate O(1) from
# O(N): an unmemoized toolbar commits ~once per char, a memoized one ~twice total.
_TYPE_TEXT = "the quick brown fox jumps over"

# Per-keystroke delay so each key's React commit flushes before the next — this
# is what makes per-character re-renders visible rather than batched away. Also
# closer to human typing than a zero-delay firehose.
_KEYSTROKE_DELAY_MS = 25

# A big pre-existing draft for the long_draft blend (typed fast, outside the
# window). Long enough that content-proportional per-keystroke work would show.
_LONG_DRAFT = "lorem ipsum dolor sit amet " * 40  # ~1080 chars


# ---- Blends ---------------------------------------------------------------
# Each blend returns the chat panel whose input the measurement types into,
# already in a stable state (agent idle, editor focused-able).


def blend_empty(page: Page) -> PlaywrightChatPanelElement:
    """One workspace, empty editor."""
    task_page: PlaywrightTaskPage = start_task_and_wait_for_ready(page, prompt="warmup", workspace_name="Perf Typing")
    return task_page.get_chat_panel()


def blend_long_draft(page: Page) -> PlaywrightChatPanelElement:
    """One workspace, editor pre-filled with a long draft (not yet sent)."""
    task_page: PlaywrightTaskPage = start_task_and_wait_for_ready(
        page, prompt="warmup", workspace_name="Perf Typing Long Draft"
    )
    chat_panel = task_page.get_chat_panel()
    # Seed the draft in one transaction, outside the measurement window.
    type_into_tiptap(page, chat_panel.get_chat_input(), _LONG_DRAFT)
    expect(chat_panel.get_chat_input()).to_contain_text("lorem ipsum")
    return chat_panel


# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "blend",
    [
        pytest.param(blend_empty, id="empty"),
        pytest.param(blend_long_draft, id="long_draft"),
    ],
)
@user_story("perf: typing into the prompt input should not re-render the toolbar per keystroke")
def test_prompt_input(
    sculptor_instance_: SculptorInstance,
    perf_recorder: MeasurementRecorder,
    blend: Callable[[Page], PlaywrightChatPanelElement],
    request: pytest.FixtureRequest,
) -> None:
    page = sculptor_instance_.page
    chat_panel = blend(page)
    chat_input = chat_panel.get_chat_input()
    # Focus outside the window so the click's own render isn't attributed to typing.
    chat_input.click()
    expect(chat_input).to_be_focused()

    variant = request.node.callspec.id
    with perf_recorder.window(scenario="prompt_input", variant=variant):
        # Real per-character key events (not a single insertText transaction),
        # so per-keystroke re-renders are actually exercised.
        chat_input.press_sequentially(_TYPE_TEXT, delay=_KEYSTROKE_DELAY_MS)
        # End-signal: the typed text is present in the editor.
        expect(chat_input).to_contain_text(_TYPE_TEXT.split()[-1])
