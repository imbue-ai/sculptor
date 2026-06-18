"""Real pi integration test: skills end-to-end.

Seeds a custom skill into the workspace's ``.claude/skills/``, invokes it
through the slash-picker path (the SkillsPanel chip), and verifies the real
``pi --mode rpc`` subprocess + real upstream model *follows the SKILL.md*:
the skill instructs pi to emit a sentinel string, and we assert it appears in
the reply. This exercises the whole supports_skills mechanism — ``--skill``
launch flags (``agent_wrapper._build_skill_launch_args``), the slash-picker
list, and the ``/name`` → ``/skill:<name>`` rewrite
(``agent_wrapper._rewrite_skill_invocation``).
"""

import subprocess
from pathlib import Path

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from tests.integration.real_pi.helpers import RESPONSE_TIMEOUT_MS
from tests.integration.real_pi.helpers import real_pi

# A fixed sentinel the skill tells pi to emit. Narrow skill description +
# explicit body so progressive disclosure can't auto-fire the skill un-invoked.
_SENTINEL = "SKILL-OK-73194"
_SKILL_NAME = "pi-skills-sentinel"
_SKILL_DESCRIPTION = "Internal Sculptor integration-test sentinel; only run when explicitly invoked by name."
_SKILL_BODY = f"When this skill is invoked, reply with exactly the text {_SENTINEL} and nothing else."


def _commit_sentinel_skill(project_path: Path) -> None:
    """Commit the sentinel skill to .claude/skills/ so the workspace checkout
    (and pi's --skill flags) include it."""
    skill_dir = project_path / ".claude" / "skills" / _SKILL_NAME
    skill_dir.mkdir(parents=True, exist_ok=True)
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {_SKILL_NAME}\ndescription: {_SKILL_DESCRIPTION}\n---\n{_SKILL_BODY}\n"
    )
    subprocess.run(["git", "add", str(skill_dir)], cwd=project_path, check=True)
    subprocess.run(["git", "commit", "-m", f"Add skill {_SKILL_NAME}"], cwd=project_path, check=True)


@real_pi
@pytest.mark.timeout(300)
def test_pi_follows_invoked_skill(sculptor_instance_: SculptorInstance) -> None:
    """A skill picked from the SkillsPanel is followed by real pi end-to-end."""
    _commit_sentinel_skill(sculptor_instance_.project_path)

    task_page = start_task_and_wait_for_ready(
        sculptor_page=sculptor_instance_.page,
        workspace_name="Real Pi Skills",
        model_name=None,
        agent_type="pi",
    )

    # Invoke via the picker path: open the SkillsPanel and click the skill chip,
    # which inserts a `/pi-skills-sentinel` mention into the editor. PiAgent
    # rewrites the leading `/name` to pi's `/skill:<name>` form before sending.
    skills_panel = task_page.open_skills_panel()
    chip = skills_panel.get_skill_chip(_SKILL_NAME)
    expect(chip).to_be_visible(timeout=30_000)
    chip.click()

    chat_panel = task_page.get_chat_panel()
    expect(chat_panel.get_mention_spans()).to_contain_text(_SKILL_NAME)
    send_button = chat_panel.get_send_button()
    expect(send_button).to_be_enabled()
    send_button.click()

    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2, timeout=RESPONSE_TIMEOUT_MS)
    expect(chat_panel.get_assistant_messages().last).to_contain_text(_SENTINEL)
    expect(chat_panel.get_error_block()).to_have_count(0)
