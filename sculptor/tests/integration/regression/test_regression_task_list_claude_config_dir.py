"""Regression test for SCU-1295: agent todos disappear when CLAUDE_CONFIG_DIR is set.

Claude Code honors the ``CLAUDE_CONFIG_DIR`` environment variable as the base
for its on-disk state (sessions, projects, tasks). Sculptor's
``process_manager.ClaudeCodeProcessManager._spawn_claude_process`` forwards
every ``CLAUDE_*`` env var from the parent process into the Claude
subprocess, so when a user has ``CLAUDE_CONFIG_DIR`` set in their shell
Claude writes per-task JSON files under
``$CLAUDE_CONFIG_DIR/tasks/{session_id}/`` rather than
``$HOME/.claude/tasks/{session_id}/``.

The bug: Sculptor's ``get_claude_tasks_path`` hard-coded
``$HOME/.claude/tasks/...``, so when the env var was set Sculptor read from
the wrong directory, ``_read_task_list_artifact`` returned an empty
``TaskListArtifact``, and the StatusPill popover went empty even though the
agent was emitting TaskCreate / TaskUpdate calls.
"""

from pathlib import Path

from playwright.sync_api import expect

from sculptor.constants import ElementIDs
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_PARTIAL_PROGRESS_TASKS = """\
fake_claude:multi_step `{
  "steps": [
    {"command": "task_create", "args": {"id": "1", "subject": "Step 1", "status": "completed", "activeForm": "Working on Step 1"}},
    {"command": "task_create", "args": {"id": "2", "subject": "Step 2", "status": "in_progress", "activeForm": "Working on Step 2"}},
    {"command": "task_create", "args": {"id": "3", "subject": "Step 3", "status": "pending", "activeForm": "Working on Step 3"}}
  ]
}`"""


@user_story("to see the agent task list when CLAUDE_CONFIG_DIR points at a non-default location")
def test_task_list_shown_when_claude_config_dir_is_set(
    sculptor_instance_factory_: SculptorInstanceFactory,
    tmp_path: Path,
) -> None:
    """The task popover must populate when the Claude config dir is custom.

    Drives the standard TaskCreate flow under a Sculptor instance launched
    with ``CLAUDE_CONFIG_DIR=<tmpdir>``. FakeClaude writes the per-task
    JSON files under that directory (mirroring real Claude); the backend
    reads them via ``_read_task_list_artifact``. Before the fix the
    backend looked under ``$HOME/.claude`` regardless and the popover was
    empty; with the fix both sides agree on the path.
    """
    custom_claude_dir = tmp_path / "custom-claude"
    custom_claude_dir.mkdir(parents=True, exist_ok=True)
    sculptor_instance_factory_.update_environment(CLAUDE_CONFIG_DIR=str(custom_claude_dir))

    with sculptor_instance_factory_.spawn_instance() as instance:
        task_page = start_task_and_wait_for_ready(
            sculptor_page=instance.page,
            prompt=_PARTIAL_PROGRESS_TASKS,
            wait_for_agent_to_finish=False,
        )

        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        status_pill = instance.page.get_by_test_id(ElementIDs.STATUS_PILL)
        expect(status_pill).to_be_visible()
        label = instance.page.get_by_test_id(ElementIDs.STATUS_PILL_LABEL)
        # The post-turn count summary is the deterministic surface: it derives
        # straight from the artifact contents and survives the pill's
        # phase-machine timing. If the artifact were empty the pill itself
        # would hide.
        expect(label).to_contain_text("1 of 3 done")

        # Opening the popover should show all three rows fed from the custom
        # tasks directory.
        status_pill.click()
        rows = instance.page.get_by_test_id(ElementIDs.AGENT_TASKS_ROW)
        expect(rows).to_have_count(3)
        expect(rows.nth(0)).to_contain_text("Step 1")
        expect(rows.nth(1)).to_contain_text("Step 2")
        expect(rows.nth(2)).to_contain_text("Step 3")
