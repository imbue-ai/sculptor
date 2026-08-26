"""Integration tests for ask_user_question calls made by SUBAGENTS.

When a subagent (Agent tool) calls ``mcp__sculptor__ask_user_question``, the
Claude CLI emits the MCP ``tools/call`` control_request BEFORE the sidechain
assistant message that carries the tool_use block — the inverse of the
main-agent ordering that Sculptor's MCP pairing was built around (observed on
Claude Code 2.1.170; freeze trace from 2026-07-01). These tests replay that
real ordering through FakeClaude and assert the user's answer still reaches
the subagent so the turn completes instead of freezing:

- ``test_subagent_ask_user_question_completes_turn``: the basic freeze — an
  unmatched tools/call must not be silently dropped.
- ``test_subagent_question_not_answered_from_stale_cache``: an
  already-answered main-agent question must not be replayed from the answer
  cache onto the subagent's different question.
- ``test_two_concurrent_subagent_questions_route_answers``: two subagents
  asking concurrently must each receive the answer to their own question.
"""

from playwright.sync_api import expect

from sculptor.testing.elements.ask_user_question import get_ask_user_question_panel
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_LANGUAGE_QUESTION_JSON = """\
{
  "question": "What language do you prefer?",
  "header": "Language",
  "options": [
    {"label": "Python", "description": "A versatile language"},
    {"label": "Rust", "description": "For systems programming"}
  ],
  "multiSelect": false
}"""

_EDITOR_QUESTION_JSON = """\
{
  "question": "What editor do you use?",
  "header": "Editor",
  "options": [
    {"label": "VS Code", "description": "Popular editor"},
    {"label": "Neovim", "description": "Terminal editor"}
  ],
  "multiSelect": false
}"""


@user_story("to answer a question asked by a subagent so the turn can finish")
def test_subagent_ask_user_question_completes_turn(sculptor_instance_: SculptorInstance) -> None:
    """A subagent's question is answered via the panel and the answer reaches
    the subagent, letting the whole turn complete.

    FakeClaude replays the real subagent event ordering: the MCP tools/call
    arrives before the sidechain assistant line. If Sculptor drops the
    unmatched tools/call, the answer never reaches the subagent and the
    summary message never appears (the turn freezes).
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"""\
fake_claude:subagent_ask_user_question `{{
  "questions": [{_LANGUAGE_QUESTION_JSON}]
}}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # The subagent's question panel appears (the sidechain assistant line
    # carrying the tool_use block still reaches the UI).
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    expect(auq_panel.get_question_text()).to_contain_text("What language do you prefer?")

    auq_panel.select_option("Python")
    auq_panel.submit()

    # The answer must reach the subagent: FakeClaude echoes it in the main
    # agent's summary message and the turn completes.
    expect(chat_panel.get_messages().last).to_contain_text("Subagent finished", timeout=60_000)
    expect(chat_panel.get_messages().last).to_contain_text("Python")
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30_000)


@user_story("to have a subagent's question answered by me, not by a stale cached answer")
def test_subagent_question_not_answered_from_stale_cache(sculptor_instance_: SculptorInstance) -> None:
    """After a main-agent question was answered in the same turn, a subagent's
    DIFFERENT question must still be shown to the user and receive the user's
    fresh answer — not the cached answer to the earlier question.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"""\
fake_claude:ask_user_question_then_subagent_ask `{{
  "first_questions": [{_LANGUAGE_QUESTION_JSON}],
  "second_questions": [{_EDITOR_QUESTION_JSON}]
}}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # First (main-agent) question — answer "Python".
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    expect(auq_panel.get_question_text()).to_contain_text("What language do you prefer?")
    auq_panel.select_option("Python")
    auq_panel.submit()

    # Second (subagent) question — must surface and wait for the user rather
    # than being auto-answered from the first answer's cache.
    expect(auq_panel).to_be_visible(timeout=30_000)
    expect(auq_panel.get_question_text()).to_contain_text("What editor do you use?")
    auq_panel.select_option("Neovim")
    auq_panel.submit()

    # The subagent must receive the ANSWER TO ITS QUESTION (Neovim), not the
    # stale first answer (Python).
    expect(chat_panel.get_messages().last).to_contain_text("Subagent received answer:", timeout=60_000)
    expect(chat_panel.get_messages().last).to_contain_text("Neovim")
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30_000)


@user_story("to answer questions from two concurrent subagents and have each get its own answer")
def test_two_concurrent_subagent_questions_route_answers(sculptor_instance_: SculptorInstance) -> None:
    """Two subagents ask different questions concurrently (interleaved with
    the inverted subagent event ordering). Each answer must be routed to the
    subagent that asked — single-slot pairing crosses the wires.
    """
    page = sculptor_instance_.page

    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt=f"""\
fake_claude:two_subagents_ask_user_question `{{
  "first_questions": [{_LANGUAGE_QUESTION_JSON}],
  "second_questions": [{_EDITOR_QUESTION_JSON}]
}}`""",
        wait_for_agent_to_finish=False,
    )
    chat_panel = task_page.get_chat_panel()

    # Both questions are pending; the panel shows the most recent one first
    # (subagent B's editor question), then re-pends subagent A's.
    auq_panel = get_ask_user_question_panel(page)
    expect(auq_panel).to_be_visible(timeout=30_000)
    expect(auq_panel.get_question_text()).to_contain_text("What editor do you use?")
    auq_panel.select_option("Neovim")
    auq_panel.submit()

    expect(auq_panel).to_be_visible(timeout=30_000)
    expect(auq_panel.get_question_text()).to_contain_text("What language do you prefer?")
    auq_panel.select_option("Python")
    auq_panel.submit()

    # Each subagent must echo the answer to ITS OWN question.
    summary = chat_panel.get_messages().last
    expect(summary).to_contain_text("Subagent A received answer:", timeout=60_000)
    expect(summary).to_contain_text('"What language do you prefer?"="Python"')
    expect(summary).to_contain_text('"What editor do you use?"="Neovim"')
    expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=30_000)
