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

import io
import subprocess
import tempfile
import uuid
from pathlib import Path

import pytest
from PIL import Image
from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.base import type_trigger_char
from sculptor.testing.elements.chat_panel import select_model_by_name
from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.task_starter import FAKE_CLAUDE_MODEL_NAME
from sculptor.testing.fake_pi import _FAKE_PI_MODELS
from sculptor.testing.fake_pi import install_fake_pi_binary
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import send_message_via_api
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.playwright_utils import upload_file_via_api
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story
from sculptor.testing.utils import get_playwright_modifier_key
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
    if harness.first_agent_type == "pi":
        install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
        model_name = None
    else:
        model_name = FAKE_CLAUDE_MODEL_NAME
    return start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name=workspace_name,
        model_name=model_name,
        agent_type=harness.first_agent_type,
    )


def _start_busy_workspace_for_harness(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig, workspace_name: str, release_path: Path
) -> PlaywrightTaskPage:
    """Create a workspace whose first turn blocks on a sentinel file.

    The agent stays busy (cancellable) until ``release_path`` is touched — a
    deterministic busy window (no wall-clock) in which the Stop button and the
    queued-message interrupt affordance are present.
    """
    if harness.first_agent_type == "pi":
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
        agent_type=harness.first_agent_type,
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
    if harness.first_agent_type == "pi":
        expect(sculptor_instance_.page.get_by_test_id(ElementIDs.FAST_MODE_TOGGLE)).to_have_count(0)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to see a sub-agent's activity render as a nested attributed pill under both harnesses")
def test_sub_agent_pill_renders_under_both_harnesses(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    """Sub-agents are now a shared capability: a scripted sub-agent call renders
    as the AlphaSubagentPill (the parent entry with nested, attributed child
    activity) under Claude AND pi.

    This is the two-sided assertion for `supports_sub_agents` (REQ-TEST-4): the
    render path was previously suppressed for pi (the gate hid the pill); pi now
    spawns sub-agents through the pinned `sculptor_subagent` extension, whose
    structured per-child progress the adapter maps onto the same
    `parent_tool_use_id` grouping Claude uses. Pi's `fake_pi:subagent` directive
    scripts the structured payload; FakeClaude's `subagent` directive scripts an
    Agent tool call. Both surface the pill.
    """
    task_page = _create_workspace_for_harness(sculptor_instance_, harness, "Sub-Agent Render")
    chat_panel = task_page.get_chat_panel()
    if harness.first_agent_type == "pi":
        prompt = 'fake_pi:subagent `{"children": [{"childId": "c0", "label": "scout", "task": "find files", "status": "done", "events": [{"seq": 0, "kind": "text", "text": "Found 10 files."}]}]}`'
    else:
        prompt = (
            'fake_claude:subagent `{"description": "Find files", "prompt": "List files", '
            + '"subagent_result": "Found 10 files.", "summary_text": "The sub-agent found 10 files."}`'
        )
    send_chat_message(chat_panel=chat_panel, message=prompt)

    # The sub-agent activity renders as the pill under both harnesses (the gate
    # no longer suppresses it for pi).
    expect(sculptor_instance_.page.get_by_test_id(ElementIDs.ALPHA_CHAT_SUBAGENT_PILL).first).to_be_visible(
        timeout=30000
    )


def _png_bytes(color: tuple[int, int, int] = (0, 0, 255)) -> bytes:
    """A small solid-color PNG, in memory."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color).save(buffer, format="PNG")
    return buffer.getvalue()


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
    if harness.first_agent_type == "pi":
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
        agent_type="pi",
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


# The model switcher under pi has no Claude analogue: Claude sources its list from
# the frontend's hardcoded PRODUCTION_MODELS, while pi alone populates a backend
# list. So this is a pi-only test, not parametrized over Claude — Claude's
# switcher being live is already exercised by the FAKE_CLAUDE_MODEL_NAME selection
# every sibling makes in _create_workspace_for_harness.
@user_story("to see pi's own models in the chat switcher and pick one without an error")
def test_pi_model_switcher_offers_pi_models_and_accepts_a_pick(sculptor_instance_: SculptorInstance) -> None:
    """Under pi the model switcher is enabled (not the disabled-with-tooltip
    placeholder), populated with pi's OWN models, shows pi's current model, and
    accepts selecting a different pi model without surfacing a failure.

    FakePi scripts a fixed catalog for `get_available_models` and a current model
    for `get_state`, so PiAgent surfaces them onto task state and the switcher
    renders pi's models — never Claude's hardcoded list. Selecting a different pi
    model POSTs the set-model endpoint, which FakePi's `set_model` accepts, so no
    error toast appears.

    The post-switch displayed-selection update is not asserted here — it is
    server-driven (the view's `selected_model_id`) and not deterministic within
    the test harness; the set_model round-trip (success persists `current_model`,
    failure surfaces an error) is covered at unit level in `agent_wrapper_test`
    (`test_set_model_*`) and `fake_pi_test`.
    """
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page
    # PiAgent fetches its model catalog at agent start, which only happens once a
    # turn runs — so send a trivial first prompt to start the agent (and surface
    # the catalog) rather than leaving the workspace in a prompt-less waiting state.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Pi Model Switcher",
        model_name=None,
        agent_type="pi",
        prompt='fake_pi:emit_text `{"text": "ready"}`',
    )
    chat_panel = task_page.get_chat_panel()

    default_model_name = _FAKE_PI_MODELS[0]["name"]
    default_model_id = _FAKE_PI_MODELS[0]["id"]
    other_model_name = _FAKE_PI_MODELS[2]["name"]
    other_model_id = _FAKE_PI_MODELS[2]["id"]

    # The switcher is live (the capability gate is open under pi), not the
    # disabled-with-tooltip placeholder.
    expect(chat_panel.get_model_selector()).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_MODEL_SELECTION)).to_have_count(0)

    # It shows pi's current model. The catalog is fetched at agent start and
    # persisted on the first message batch, so the selection may land just after
    # the panel mounts — auto-retried by expect under the default timeout.
    expect(chat_panel.get_model_selector()).to_contain_text(default_model_name)

    # Open the dropdown: it lists exactly pi's OWN models (targeted by per-model
    # testid), so a Claude-only entry from the hardcoded PRODUCTION_MODELS would
    # show up as an extra option. `expect` auto-retries until the options mount.
    chat_panel.get_model_selector().click()
    expect(chat_panel.get_model_options()).to_have_count(len(_FAKE_PI_MODELS))
    expect(chat_panel.get_model_option(default_model_id)).to_be_visible()
    expect(chat_panel.get_model_option(other_model_id)).to_be_visible()
    page.keyboard.press("Escape")

    # Picking a different pi model POSTs the set-model endpoint. FakePi accepts the
    # set_model, so the switch surfaces no failure toast and the switcher stays
    # live (the current model is still shown, not blanked).
    select_model_by_name(chat_panel=chat_panel, model_name=other_model_name)
    expect(page.get_by_test_id(ElementIDs.TOAST).filter(has_text="Failed to switch")).to_have_count(0)
    expect(chat_panel.get_model_selector()).to_be_visible()


@user_story("to see a freshly-created pi agent's switcher offer pi's own models before any message is sent")
def test_fresh_pi_agent_switcher_shows_pi_models_without_a_message(sculptor_instance_: SculptorInstance) -> None:
    """A freshly-created pi agent shows pi's OWN models in the switcher before any
    message is sent — never the built-in Claude list.

    pi's catalog is fetched when its environment is ready (not deferred to the
    first turn), so the switcher reflects pi's models as soon as the workspace is
    READY. FakePi scripts the catalog (`get_available_models` / `get_state`).
    """
    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    page = sculptor_instance_.page
    # No prompt: the bug is the pre-message state of a fresh pi agent, so the
    # switcher must already offer pi's models without a turn having run.
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        workspace_name="Fresh Pi Models",
        model_name=None,
        agent_type="pi",
    )
    chat_panel = task_page.get_chat_panel()
    default_model_name = _FAKE_PI_MODELS[0]["name"]
    default_model_id = _FAKE_PI_MODELS[0]["id"]

    # With no message sent, the switcher already shows pi's current model.
    expect(chat_panel.get_model_selector()).to_contain_text(default_model_name, timeout=30000)

    # Its dropdown lists exactly pi's models (targeted by per-model testid), so a
    # Claude-only entry from PRODUCTION_MODELS would show up as an extra option.
    # `expect` auto-retries until the options mount.
    chat_panel.get_model_selector().click()
    expect(chat_panel.get_model_options()).to_have_count(len(_FAKE_PI_MODELS))
    expect(chat_panel.get_model_option(default_model_id)).to_be_visible()
    page.keyboard.press("Escape")


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to attach files in a pi workspace and have images and paths reach the agent")
def test_uploads_usable_and_deliver_under_pi(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    task_page = _create_workspace_for_harness(sculptor_instance_, harness, "File Upload Gate")
    page = sculptor_instance_.page
    # Both harnesses keep a usable chat input with the upload input in the DOM.
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_be_visible()
    expect(page.get_by_test_id(ElementIDs.FILE_UPLOAD)).to_be_attached()
    if harness.first_agent_type != "pi":
        # Claude branch unchanged: the upload affordance has always been live.
        return
    # Flipped pi branch: attachments are no longer dropped. Deliver one image
    # and one non-image file through the upload transport, then assert FakePi
    # received the image on `images[]` (one image, image/png) and the text file
    # as a path in the prompt text — the exclusive split prompt assembly does.
    image_id = upload_file_via_api(page, name="pic.png", mime_type="image/png", content=_png_bytes())
    text_id = upload_file_via_api(page, name="notes.txt", mime_type="text/plain", content=b"sentinel-99")
    send_message_via_api(page, message="fake_pi:report_inputs", files=[image_id, text_id])

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=30_000)
    last = chat_panel.get_assistant_messages().last
    expect(last).to_contain_text("images=1")
    expect(last).to_contain_text("image/png")
    # The non-image attachment rides the prompt text as a path (its upload id is
    # preserved as the saved filename), not as a second image.
    expect(last).to_contain_text(text_id)


def _create_skill_in_directory(project_path: Path, skill_name: str, description: str) -> None:
    """Commit a custom skill to the project's .claude/skills/ so the workspace
    clone (and pi's --skill flags) include it."""
    skill_dir = project_path / ".claude" / "skills" / skill_name
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(f"---\nname: {skill_name}\ndescription: {description}\n---\nInstructions.\n")
    subprocess.run(["git", "add", str(skill_dir)], cwd=project_path, check=True)
    subprocess.run(["git", "commit", "-m", f"Add skill {skill_name}"], cwd=project_path, check=True)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to browse and pick the workspace's skills under any skills-supporting harness, including pi")
def test_skills_panel_and_picker_list_skills(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    """Pi reports supports_skills=True, so the skills panel and the slash picker
    list the workspace's skills under pi exactly as under Claude (the picker is
    harness-agnostic; PiAgent rewrites a picked /name into pi's /skill:<name>).

    The gated-off (supports_skills=False) state is covered at the component
    level by SkillsPanel.test.tsx, since no shipping harness reports False."""
    skill_name = "skills-gate-custom"
    _create_skill_in_directory(sculptor_instance_.project_path, skill_name, "Skill for the pi skills gate test")

    task_page = _create_workspace_for_harness(sculptor_instance_, harness, "Skills Panel Gate")

    # The side panel lists the seeded skill (this is the surface that reads the
    # supports_skills flag) for both Claude and pi.
    skills_panel = task_page.open_skills_panel()
    expect(skills_panel.get_skill_chip(skill_name)).to_be_visible()

    # The slash picker also surfaces it. The picker fetches the same
    # discover_skills list for every harness; on slow CI the workspace clone's
    # skills may not be discovered yet, so retry the trigger.
    page = sculptor_instance_.page
    chat_input = task_page.get_chat_panel().get_chat_input()
    mention_list = page.get_by_test_id(ElementIDs.MENTION_LIST)
    mod_key = get_playwright_modifier_key()
    for attempt in range(5):
        type_trigger_char(chat_input, "/")
        chat_input.press_sequentially(skill_name)
        try:
            expect(mention_list).to_be_visible(timeout=10_000)
            expect(mention_list).to_contain_text(skill_name, timeout=5_000)
            break
        except AssertionError:
            if attempt == 4:
                raise
            page.keyboard.press("Escape")
            page.keyboard.press(f"{mod_key}+a")
            page.keyboard.press("Backspace")
            page.wait_for_timeout(200)


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to stop an in-flight turn from the Stop button in every harness, including pi")
def test_stop_button_gated_on_interruption(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    """While the agent is busy, both Claude and pi show the live Stop button (no
    disabled-with-tooltip placeholder), and pressing it ends the in-flight turn."""
    page = sculptor_instance_.page
    release_path = Path(tempfile.gettempdir()) / f"pi_cap_stop_{uuid.uuid4().hex}"
    try:
        task_page = _start_busy_workspace_for_harness(sculptor_instance_, harness, "Stop Button Gate", release_path)
        chat_panel = task_page.get_chat_panel()
        # The pill is only up while the agent is in a cancellable (busy) state.
        expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_be_visible(timeout=15000)
        # The real Stop button renders for both harnesses; the gated-off
        # placeholder appears for neither.
        expect(page.get_by_test_id(ElementIDs.STATUS_PILL_STOP)).to_be_visible()
        expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_STOP)).to_have_count(0)
        # Pressing Stop ends the in-flight turn.
        chat_panel.get_stop_button().click()
        expect(chat_panel.get_thinking_indicator()).not_to_be_visible(timeout=15000)
    finally:
        # Harmless if the turn already ended via Stop; releases the blocked turn
        # if a Stop assertion failed before the click.
        release_path.touch()


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to interrupt-and-send a queued message in every harness, including pi")
def test_queued_interrupt_gated_on_interruption(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    """A message queued while the agent is busy shows an interrupt-and-send
    button — live for both Claude and pi (no disabled-with-tooltip placeholder)."""
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
        # The live interrupt-and-send button renders for both harnesses; the
        # gated-off placeholder for neither.
        expect(page.get_by_test_id(ElementIDs.QUEUED_MESSAGE_SEND_BUTTON)).to_be_visible()
        expect(page.get_by_test_id(ElementIDs.CAPABILITY_DISABLED_QUEUED_INTERRUPT)).to_have_count(0)
    finally:
        release_path.touch()


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to reset context with /clear under any harness that supports it, instead of being refused")
def test_clear_pseudo_skill_gated_on_context_reset(
    sculptor_instance_: SculptorInstance, harness: HarnessTestConfig
) -> None:
    """Typing /clear is accepted under both Claude and pi (no refusal copy) and the
    workspace stays usable. This asserts only the gate; the reset round-trip is covered
    by test_pi_basic.test_pi_clear_resets_conversation and the real_pi clear test."""
    page = sculptor_instance_.page
    task_page = _create_workspace_for_harness(sculptor_instance_, harness, "Clear Gate")
    send_chat_message(chat_panel=task_page.get_chat_panel(), message="/clear")
    # Both harnesses support context reset: no refusal copy, the endpoint is called.
    refusal_toast = page.get_by_test_id(ElementIDs.TOAST).filter(has_text=_CAPABILITY_UNSUPPORTED_COPY)
    expect(refusal_toast).to_have_count(0)
    # The chat input stays usable after the reset.
    expect(page.get_by_test_id(ElementIDs.CHAT_INPUT)).to_be_visible()


@pytest.mark.parametrize("harness", ["claude", "pi"], indirect=True)
@user_story("to show truthful compaction chrome under harnesses that compact context")
def test_compaction_chrome_truthful_under_pi(sculptor_instance_: SculptorInstance, harness: HarnessTestConfig) -> None:
    """Compaction is status-only chrome — the StatusPill "Compacting" state.

    Under pi, a scripted compaction held open shows the Compacting pill while
    active, and the pill clears once compaction ends and the turn finishes.
    Claude is unchanged: it has no manual /compact surface to script here (parity
    bar), so its branch only confirms the harness path is healthy — the pi branch
    carries this test's claim. (Pi's deterministic show-then-clear and the
    stuck-pill edges are covered at unit level in ``agent_wrapper_test``.)
    """
    page = sculptor_instance_.page
    if harness.first_agent_type != "pi":
        _create_workspace_for_harness(sculptor_instance_, harness, "Compaction Chrome")
        return

    install_fake_pi_binary(sculptor_instance_.fake_bin_dir)
    release_path = Path(tempfile.gettempdir()) / f"pi_compaction_{uuid.uuid4().hex}"
    label = page.get_by_test_id(ElementIDs.STATUS_PILL_LABEL)
    try:
        start_task_and_wait_for_ready(
            sculptor_page=page,
            workspace_name="Compaction Chrome",
            model_name=None,
            agent_type="pi",
            # The compaction is held open on the sentinel so the Compacting pill
            # state is observable deterministically (no wall-clock race).
            prompt=f'fake_pi:compaction `{{"reason": "threshold", "wait_path": "{release_path}"}}`',
            wait_for_agent_to_finish=False,
        )
        expect(label).to_contain_text("Compacting", timeout=15000)
    finally:
        release_path.touch()
    # Once compaction ends, the turn finishes and the Compacting chrome clears.
    expect(page.get_by_test_id(ElementIDs.STATUS_PILL)).to_have_count(0, timeout=15000)
