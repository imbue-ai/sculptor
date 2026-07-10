"""Real-Claude e2e for the bundled Claude Code terminal-agent sample.

Installs the shipped sample into the test instance's sculptor folder — with
the hooks path rewritten to that folder — creates the
registered agent, drives one trivial TUI turn, and asserts the hooks
reported state: session id persisted (SessionStart), busy during the turn
(UserPromptSubmit), idle after (Stop).

Kept deliberately minimal — it burns real tokens. files-changed and the
restart-resume mechanics are covered deterministically by the fake-program
integration tests; this test proves the REAL hooks JSON + TUI flags work.
"""

import json
import re
import sqlite3
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.add_panel_dropdown import PlaywrightAddPanelDropdownElement
from sculptor.testing.elements.panel_tab import PlaywrightPanelTabElement
from sculptor.testing.elements.terminal import get_agent_terminal_panel
from sculptor.testing.elements.terminal import get_agent_terminal_textarea
from sculptor.testing.elements.terminal import get_xterm_buffer_text
from sculptor.testing.elements.terminal import type_into_agent_terminal
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_claude.helpers import real_claude

_SAMPLE_DIR = Path(__file__).parents[4] / "samples" / "terminal_agents" / "claude-code"


def _install_sample(sculptor_folder: Path) -> None:
    """Install the shipped sample, pointing --settings at this instance's copy.

    Injects an extra SessionStart hook that records the hook execution
    environment (resolved sculpt path, SCULPT_* vars, PATH) to a diag file —
    the sample's hooks are fail-open (`|| true`), so without this a broken
    hook environment is indistinguishable from a hook that never fired.
    """
    registrations_dir = sculptor_folder / "terminal_agents"
    registrations_dir.mkdir(parents=True, exist_ok=True)
    hooks = json.loads((_SAMPLE_DIR / "claude-code-hooks.json").read_text())
    diag_file = _hook_diag_file(sculptor_folder)
    diag_program = (
        "import json,os,shutil,sys; d=json.load(sys.stdin); "
        + f"open('{diag_file}','a').write(json.dumps({{'sid': d.get('session_id'), "
        + "'which_sculpt': shutil.which('sculpt'), "
        + "'port': os.environ.get('SCULPT_API_PORT'), 'agent': os.environ.get('SCULPT_AGENT_ID'), "
        + "'path': os.environ.get('PATH')})+chr(10))"
    )
    diag_command = f'python3 -c "{diag_program}" || true'
    hooks["hooks"]["SessionStart"][0]["hooks"].append({"type": "command", "command": diag_command})
    hooks_path = registrations_dir / "claude-code-hooks.json"
    hooks_path.write_text(json.dumps(hooks))
    toml_body = (_SAMPLE_DIR / "claude-code.toml").read_text()
    toml_body = toml_body.replace("~/.sculptor/terminal_agents/claude-code-hooks.json", str(hooks_path))
    (registrations_dir / "claude-code.toml").write_text(toml_body)


def _hook_diag_file(sculptor_folder: Path) -> Path:
    return sculptor_folder / "terminal_agents" / "session_start_diag.jsonl"


def _read_hook_diag(sculptor_folder: Path) -> str:
    diag_file = _hook_diag_file(sculptor_folder)
    if diag_file.is_file():
        return diag_file.read_text()
    return "<SessionStart hook never ran: no diag file>"


def _read_terminal_session_id(sculptor_folder: Path, task_title: str) -> str | None:
    """Read the persisted terminal_session_id for the named task from the DB."""
    db_path = sculptor_folder / "sculptor.db"
    # The server opens this DB at startup, well before any agent exists — a
    # missing file here is a wrong path, not a not-yet-created DB.
    assert db_path.is_file(), f"Sculptor DB not found at {db_path}"
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rows = connection.execute("SELECT current_state FROM task_latest").fetchall()
    finally:
        connection.close()
    for (state_json,) in rows:
        if not state_json:
            continue
        state = json.loads(state_json)
        if state.get("title") == task_title:
            return state.get("terminal_session_id")
    return None


# Startup dialogs Claude Code may show before the prompt box, in any order.
# For each, Enter accepts the highlighted default, which is the choice we
# want: trust dialog (wording varies by CLI version) defaults to "Yes, I
# trust this folder"; the API-key dialog (the test harness's
# ANTHROPIC_API_KEY leaks into the PTY env) defaults to "No (recommended)",
# falling back to the logged-in subscription auth.
_STARTUP_DIALOG_MARKERS = (
    "trust the files",
    "trust this folder",
    "Do you want to use this API key",
)


def _dismiss_startup_dialogs(page) -> None:
    """Press Enter through Claude Code's startup dialogs until the prompt box renders.

    Keeps pressing Enter while any dialog is on screen: xterm.js can drop
    keystrokes on a freshly-mounted terminal, so a single Enter press is not
    reliable. The prompt-box check comes first because dismissed-dialog text
    stays in the scrollback.
    """
    deadline = time.monotonic() + 60.0
    while time.monotonic() < deadline:
        buffer_text = get_xterm_buffer_text(page)
        # Input-box-ready detection varies by CLI version: older releases
        # print a "? for shortcuts" hint; 2.1.x renders a bare "❯" caret as
        # the last line (dialog options always have text after the "❯").
        lines = [line.strip() for line in buffer_text.splitlines() if line.strip()]
        if "? for shortcuts" in buffer_text or (lines and lines[-1] == "❯"):
            return
        if any(marker in buffer_text for marker in _STARTUP_DIALOG_MARKERS):
            get_agent_terminal_textarea(page).focus()
            page.wait_for_timeout(300)
            page.keyboard.press("Enter")
        page.wait_for_timeout(500)
    raise AssertionError(f"Claude Code TUI never reached the prompt box. Buffer:\n{get_xterm_buffer_text(page)}")


@real_claude
@pytest.mark.timeout(600)
def test_claude_code_terminal_agent(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    start_task_and_wait_for_ready(page, prompt="", model_name=None, workspace_name="Claude Code TUI WS")
    _install_sample(sculptor_instance_.sculptor_folder)

    panel_tabs = PlaywrightPanelTabElement(page, sub_section="center")
    dropdown = PlaywrightAddPanelDropdownElement(page, sub_section="center")
    dropdown.open()
    dropdown.open_agent_type_submenu()
    registered_item = dropdown.get_agent_type_item_registered("claude-code")
    expect(registered_item).to_be_visible()
    registered_item.click()

    # The bundled registration and the SDK agent share the "Claude" naming
    # prefix, and the workspace's main (empty-prompt) SDK agent already claimed
    # "Claude 1" at creation — so the registered terminal agent is "Claude 2".
    claude_tab = panel_tabs.get_panel_tab_by_name("Claude 2").first
    expect(claude_tab).to_be_visible()
    expect(get_agent_terminal_panel(page)).to_be_visible()
    expect(get_agent_terminal_textarea(page)).to_be_attached()

    _dismiss_startup_dialogs(page)

    # Before any message exists, NO session id may be persisted: Claude has
    # no resumable transcript for a message-less session, so an id captured
    # at startup would make a post-restart `--resume` fail ("No conversation
    # found with session ID"). A message-less agent must instead restart via
    # the plain launch command.
    assert _read_terminal_session_id(sculptor_instance_.sculptor_folder, "Claude 2") is None, (
        "session id persisted before any message — startup-captured ids are not resumable"
    )

    # One trivial turn: UserPromptSubmit → busy spinner + session id reported
    # (the first moment a resumable conversation exists), Stop → idle/neutral.
    type_into_agent_terminal(page, "Reply with exactly the word PONG and nothing else.")

    deadline = time.monotonic() + 90.0
    session_id: str | None = None
    while time.monotonic() < deadline:
        session_id = _read_terminal_session_id(sculptor_instance_.sculptor_folder, "Claude 2")
        if session_id:
            break
        page.wait_for_timeout(1_000)
    failure_details = f"Hook diag: {_read_hook_diag(sculptor_instance_.sculptor_folder)}\nTerminal buffer:\n{get_xterm_buffer_text(page)}"
    assert session_id, f"UserPromptSubmit hook never persisted a session id.\n{failure_details}"

    expect(claude_tab).to_have_attribute("data-dot-status", "running", timeout=60_000)
    expect(claude_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"), timeout=180_000)

    # A genuine question drives the attention dot: PreToolUse on
    # AskUserQuestion signals waiting while the question UI is on screen.
    # (The Notification hook deliberately does NOT cover questions — it is
    # filtered to permission prompts so the TUI's ~60s idle_prompt reminder
    # cannot fake the dot.)
    type_into_agent_terminal(
        page,
        "Use the AskUserQuestion tool to ask me exactly one question with exactly two short options.",
    )
    expect(claude_tab).to_have_attribute("data-dot-status", "waiting", timeout=120_000)

    # Enter accepts the highlighted option; the answered question flips the
    # dot back (PostToolUse → busy) and the turn ends neutral.
    type_into_agent_terminal(page, "", press_enter=True)
    expect(claude_tab).to_have_attribute("data-dot-status", re.compile(r"^(read|unread)$"), timeout=180_000)
