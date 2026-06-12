"""Per-capability UI gating, parametrized over Claude and pi.

Each test parametrizes the ``harness`` fixture across the two harnesses and
asserts that a capability-gated affordance renders when the harness supports
it and is suppressed when it does not. Most affordances here are still
Claude-only under FakePi; the interactive-backchannel surfaces (plan-mode
toggle) now render under pi too, since pi gained that capability via the
pinned backchannel extension.

The end-to-end backchannel flow itself (ask-user-question round-trip,
plan-mode enter/approve) is exercised in ``test_pi_backchannel.py``; this
file covers only the per-capability gate state.
"""

import tempfile
import uuid
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.interfaces.agents.agent import HarnessName
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from tests.integration.frontend.conftest import HarnessTestConfig  # noqa: F401

# Mirror of the frontend's CAPABILITY_UNSUPPORTED_COPY (components/useCapabilityGate.ts).
# Kept in sync by hand — these tests assert the visible gated-off copy.
_CAPABILITY_UNSUPPORTED_COPY = "Not supported by this agent harness"


def _create_workspace_for_harness(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig, workspace_name: str
) -> PlaywrightTaskPage:
    """Create a workspace for the parametrized harness, installing FakePi when needed.

    The Claude path selects Fake Claude in the chat panel so existing
    deterministic behavior holds. The pi path skips model selection — no
    "Fake Pi" entry is registered in the LLMModel enum.
    """
    if harness.workspace_harness == HarnessName.PI:
        install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
        model_name = None
    else:
        model_name = FAKE_CLAUDE_MODEL_NAME
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        model_name=model_name,
        harness=harness.workspace_harness,
    )


def _start_busy_workspace_for_harness(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig, workspace_name: str, release_path: Path
) -> PlaywrightTaskPage:
    """Create a workspace whose first turn blocks on a sentinel file.

    The agent stays busy (cancellable) until ``release_path`` is touched — a
    deterministic busy window (no wall-clock) in which the Stop button and the
    queued-message interrupt affordance are present.
    """
    if harness.workspace_harness == HarnessName.PI:
        install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
        model_name = None
        prompt = f'fake_pi:wait_for_file `{{"path": "{release_path}"}}`'
    else:
        model_name = FAKE_CLAUDE_MODEL_NAME
        prompt = f'fake_claude:wait_for_file `{{"path": "{release_path}"}}`'
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        model_name=model_name,
        harness=harness.workspace_harness,
        prompt=prompt,
        wait_for_agent_to_finish=False,
    )


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to use the plan-mode toggle on every harness that supports the interactive backchannel")
def test_plan_mode_toggle_enabled_on_interactive_backchannel(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    # Both Claude and pi now support the interactive backchannel (pi via the
    # pinned backchannel extension), so the live plan-mode toggle renders and
    # the disabled-with-tooltip placeholder never appears — for either harness.
    _create_workspace_for_harness(sculptor_instance_, harness, "Plan Mode Toggle Gate")
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.PLAN_MODE_TOGGLE)).to_be_visible()
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_PLAN_MODE)).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to hide the fast-mode toggle in harnesses without fast-mode support")
def test_fast_mode_toggle_gated(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    _create_workspace_for_harness(sculptor_instance_, harness, "Fast Mode Gate")
    # Fast-mode toggle is AND-gated against model capability too. We only
    # assert pi-side suppression here because the Fake Claude model the test
    # picks does not necessarily advertise fast-mode, so a Claude-side
    # `to_be_visible` assertion would be model-dependent rather than gate-
    # dependent.
    if harness.workspace_harness == HarnessName.PI:
        expect(sculptor_instance_.page.get_by_test_id(ElementIDs.FAST_MODE_TOGGLE)).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to suppress the sub-agent pill render path in harnesses without sub-agent support")
def test_sub_agent_pill_render_path_gated(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    _create_workspace_for_harness(sculptor_instance_, harness, "Sub-Agent Gate")
    # Neither fake binary emits sub-agent tool blocks by default, so the
    # rendered count is 0 in both branches. The assertion still has value as a
    # regression guard against the pill leaking under pi if a future change
    # accidentally seeds metadata for it.
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL)).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to see a scripted tool call render as a completed tool block under both harnesses")
def test_tool_call_renders_under_both_harnesses(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    """Tool-use rendering is now a shared capability: a scripted Bash tool call
    renders as a completed tool block (name + result) under Claude AND pi.

    This is the two-sided rendering assertion for `supports_tool_use_rendering`
    (REQ-TEST-4): the flag has no disabled-affordance surface — flipping it to
    True for pi simply makes pi's tool-execution lane render the same way
    Claude's tool calls do. Pi's `fake_pi:tool_call` directive scripts the
    tool-execution lane (toolCall block + start/end events); FakeClaude's
    `bash` directive runs the real tool. Both surface a completed Bash block.
    """
    task_page = _create_workspace_for_harness(sculptor_instance_, harness, "Tool Render")
    chat_panel = task_page.get_chat_panel()
    if harness.workspace_harness == HarnessName.PI:
        prompt = 'fake_pi:tool_call `{"tool": "bash", "args": {"command": "echo TOOL-OK"}, "result": "TOOL-OK"}`'
    else:
        prompt = 'fake_claude:bash `{"command": "echo TOOL-OK"}`'
    send_chat_message(chat_panel=chat_panel, message=prompt)

    # The Bash tool call renders and reaches the completed state (its result
    # arrived) under both harnesses, and no tool call is left stuck in-progress.
    expect(chat_panel.get_completed_tool_calls().first).to_be_visible(timeout=15000)
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)


@user_story("to see pi file-mutating tool calls render as completed file chips")
def test_pi_write_and_edit_render_completed_file_chips(sculptor_instance_: SculptorInstance) -> None:
    """A pi write/edit renders as a COMPLETED file chip (regression: a file
    chip is skipped unless its result carries a file path, so file-mutating
    tools must emit diff content — a generic result made the chip vanish)."""
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi File Chips",
        model_name=None,
        harness=HarnessName.PI,
    )
    chat_panel = task_page.get_chat_panel()
    prompt = (
        'fake_pi:tool_call `{"tool": "write", "args": {"path": "out.txt", "content": "alpha\\nbeta"}, "result": "wrote"}` '
        + 'fake_pi:tool_call `{"tool": "edit", "args": {"path": "out.txt", "edits": [{"oldText": "beta", "newText": "BETA"}]},'
        + ' "result": "edited", "details": {"patch": "--- out.txt\\n+++ out.txt\\n@@ -1,2 +1,2 @@\\n alpha\\n-beta\\n+BETA\\n"}}`'
    )
    send_chat_message(chat_panel=chat_panel, message=prompt)

    # Both file-mutating tools render as COMPLETED file chips (the Write and the
    # Edit), and none is left stuck in-progress.
    expect(chat_panel.get_completed_file_chips().first).to_be_visible(timeout=15000)
    expect(chat_panel.get_in_progress_tool_calls()).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to keep the chat input usable when the file-upload path is gated off")
def test_chat_remains_usable_when_uploads_gated(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    _create_workspace_for_harness(sculptor_instance_, harness, "File Upload Gate")
    # FileUpload's hidden input is always in the DOM. The gate manifests as the
    # `disabled` flag on the wrapping component, which forwards to the
    # imperative handle (so paste / drop / +menu Images becomes a no-op).
    # The chat input remains visible — only the upload paths are inert.
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_be_visible()
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.FILE_UPLOAD)).to_be_attached()


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to render the skills panel empty under harnesses without skills support")
def test_skills_panel_empty_under_pi(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    _create_workspace_for_harness(sculptor_instance_, harness, "Skills Panel Gate")
    # SkillChip count is 0 under pi regardless of the panel's visibility.
    # Under Claude the panel may or may not contain user-defined skills in
    # this test repo, so the Claude branch is left unasserted.
    if harness.workspace_harness == HarnessName.PI:
        expect(sculptor_instance_.page.get_by_test_id(ElementIDs.SKILL_CHIP)).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to disable the Stop button with a tooltip in harnesses that cannot interrupt a turn")
def test_stop_button_gated_on_interruption(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    """While the agent is busy: Claude shows the live Stop button; pi shows the
    disabled-with-tooltip placeholder (the Stop control is never hidden)."""
    page = sculptor_instance_.page
    release_path = Path(tempfile.gettempdir()) / f"pi_cap_stop_{uuid.uuid4().hex}"
    try:
        _start_busy_workspace_for_harness(sculptor_instance_, harness, "Stop Button Gate", release_path)
        # The pill is only up while the agent is in a cancellable (busy) state.
        expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_be_visible(timeout=15000)
        if harness.workspace_harness == HarnessName.CLAUDE:
            expect(page.get_by_test_id(ElementIDs.STATUS_PILL_STOP)).to_be_visible()
            expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_STOP)).to_have_count(0)
        else:
            # The disabled-with-tooltip placeholder replaces the live Stop
            # button (the placeholder's button is asserted disabled by the
            # CapabilityGate unit test).
            expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_STOP)).to_be_visible()
            expect(page.get_by_test_id(ElementIDs.STATUS_PILL_STOP)).to_have_count(0)
    finally:
        # Let the blocked turn finish so the shared instance tears down cleanly.
        release_path.touch()


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to disable the queued-message interrupt-and-send button in harnesses that cannot interrupt")
def test_queued_interrupt_gated_on_interruption(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    """A message queued while the agent is busy shows an interrupt-and-send
    button — live for Claude, disabled-with-tooltip for pi."""
    page = sculptor_instance_.page
    # Queuing only happens with always-interrupt-and-send OFF; disable it
    # defensively in case a sibling test left it on the shared instance.
    settings_page = navigate_to_settings_page(page=page)
    settings_page.click_on_experimental().disable_always_interrupt()
    page.go_back()

    release_path = Path(tempfile.gettempdir()) / f"pi_cap_queued_{uuid.uuid4().hex}"
    try:
        task_page = _start_busy_workspace_for_harness(
            sculptor_instance_, harness, "Queued Interrupt Gate", release_path
        )
        chat_panel = task_page.get_chat_panel()
        expect(chat_panel.get_thinking_indicator()).to_be_visible(timeout=15000)
        # Queue a second message while the agent is blocked on the sentinel.
        send_chat_message(chat_panel=chat_panel, message="queued while running")
        expect(chat_panel.get_queued_message_bar()).to_have_count(1)
        if harness.workspace_harness == HarnessName.CLAUDE:
            expect(page.get_by_test_id(ElementIDs.QUEUED_MESSAGE_SEND_BUTTON)).to_be_visible()
            expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_QUEUED_INTERRUPT)).to_have_count(0)
        else:
            # The disabled-with-tooltip placeholder replaces the live
            # interrupt-and-send button (disabled state covered by the
            # CapabilityGate unit test).
            expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_QUEUED_INTERRUPT)).to_be_visible()
            expect(page.get_by_test_id(ElementIDs.QUEUED_MESSAGE_SEND_BUTTON)).to_have_count(0)
    finally:
        release_path.touch()


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to refuse /clear in harnesses without context reset, visibly, instead of silently failing")
def test_clear_pseudo_skill_gated_on_context_reset(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    """Typing /clear under pi (no context-reset) is refused frontend-side with
    the standard copy and never calls the clear endpoint; under Claude it is
    accepted (no refusal copy)."""
    page = sculptor_instance_.page
    task_page = _create_workspace_for_harness(sculptor_instance_, harness, "Clear Gate")
    send_chat_message(chat_panel=task_page.get_chat_panel(), message="/clear")
    refusal_toast = page.get_by_test_id(ElementIDs.TOAST).filter(has_text=_CAPABILITY_UNSUPPORTED_COPY)
    if harness.workspace_harness == HarnessName.PI:
        expect(refusal_toast).to_be_visible()
        # The chat input stays usable — the workspace is intact, just the reset declined.
        expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_be_visible()
    else:
        # Claude supports context reset: no refusal copy is shown.
        expect(refusal_toast).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to keep compaction chrome absent for harnesses that do not compact context")
def test_compaction_chrome_absent_under_pi(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    """Compaction is status-only chrome (no disabled-with-tooltip treatment); for
    pi the compaction bar/button are absent."""
    _create_workspace_for_harness(sculptor_instance_, harness, "Compaction Chrome Gate")
    if harness.workspace_harness == HarnessName.PI:
        expect(sculptor_instance_.page.get_by_test_id(ElementIDs.COMPACTION_BAR)).to_have_count(0)
        expect(sculptor_instance_.page.get_by_test_id(ElementIDs.COMPACTION_BUTTON)).to_have_count(0)
