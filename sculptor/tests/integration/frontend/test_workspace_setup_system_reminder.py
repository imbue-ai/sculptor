"""Integration tests for the workspace setup system reminder.

Each test boots a Sculptor backend, configures a workspace setup
command, creates a task, and inspects the user_instructions_*.txt
file Sculptor writes for the first message handed to the SDK
(see ClaudeProcessManager._process_single_message).
"""

import re
from pathlib import Path

from playwright.sync_api import Page
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.setup_status import PlaywrightSetupStatusElement
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.user_stories import user_story

_SETUP_RUNNING_PREAMBLE = "A workspace setup command is currently running."
_SETUP_FAILED_PREAMBLE = "The workspace setup command exited non-zero."


def _snapshot_workspace_dirs(sculptor_folder: Path) -> set[Path]:
    workspaces_dir = sculptor_folder / "workspaces"
    if not workspaces_dir.exists():
        return set()
    return set(workspaces_dir.glob("*"))


def _read_user_instructions_files(sculptor_folder: Path, baseline_workspace_dirs: set[Path]) -> list[tuple[Path, str]]:
    workspaces_dir = sculptor_folder / "workspaces"
    new_dirs = sorted(set(workspaces_dir.glob("*")) - baseline_workspace_dirs)
    paths: list[Path] = []
    for workspace_dir in new_dirs:
        paths.extend(workspace_dir.glob("state/tasks/*/user_instructions_*.txt"))
    paths.sort(key=lambda p: p.stat().st_mtime)
    return [(p, p.read_text()) for p in paths]


def _cancel_running_setup(page: Page) -> None:
    """Click the setup card's Cancel button to terminate a long-running setup.

    Tests that configure ``sleep 60`` must call this before letting the test
    end; otherwise the lingering bash process can race the Playwright trace
    teardown and produce an ENOENT on the trace artifact.
    """
    setup_status = PlaywrightSetupStatusElement(page)
    cancel_button = setup_status.get_cancel_button()
    expect(cancel_button).to_be_visible()
    cancel_button.click()
    rerun_button = setup_status.get_rerun_button()
    expect(rerun_button).to_be_visible()


def _configure_setup_command(page: Page, command: str) -> None:
    settings_page = navigate_to_settings_page(page=page)
    repos = settings_page.click_on_repositories()
    repos.expand_repo_config()
    repos.set_setup_command(command)


@user_story("to see a reminder that workspace setup is still running on the first message")
def test_setup_running_reminder_emitted_on_first_message(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "sleep 60")

    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 1, f"Expected exactly one user_instructions file, got {len(files)}"
    _, contents = files[0]
    assert contents.startswith("<system-reminder>")
    assert _SETUP_RUNNING_PREAMBLE in contents
    assert "Command: sleep 60" in contents
    pid_match = re.search(r"Bash PID: (\d+)", contents)
    assert pid_match is not None, f"Expected a 'Bash PID: <n>' line in {contents!r}"
    assert int(pid_match.group(1)) > 0
    log_match = re.search(r"Log file: (\S+)", contents)
    assert log_match is not None
    assert log_match.group(1).endswith("setup_log.txt")
    assert log_match.group(1).startswith("/")

    # Cancel the still-running setup so teardown does not race the long-lived bash.
    _cancel_running_setup(page)


@user_story("to see a reminder that workspace setup failed on the first message")
def test_setup_failed_reminder_emitted_on_first_message(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "exit 2")

    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 1, f"Expected exactly one user_instructions file, got {len(files)}"
    _, contents = files[0]
    assert contents.startswith("<system-reminder>")
    assert _SETUP_FAILED_PREAMBLE in contents
    assert "Command: exit 2" in contents
    assert "Exit code: 2" in contents
    log_match = re.search(r"Log file: (\S+)", contents)
    assert log_match is not None
    assert log_match.group(1).endswith("setup_log.txt")
    assert log_match.group(1).startswith("/")


@user_story("to not see a setup reminder when the setup command succeeded")
def test_no_setup_reminder_when_setup_succeeded(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "true")

    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 1
    _, contents = files[0]
    assert _SETUP_RUNNING_PREAMBLE not in contents
    assert _SETUP_FAILED_PREAMBLE not in contents


@user_story("to not see a setup reminder when no setup command is configured")
def test_no_setup_reminder_when_no_command_configured(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "")

    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 1
    _, contents = files[0]
    assert _SETUP_RUNNING_PREAMBLE not in contents
    assert _SETUP_FAILED_PREAMBLE not in contents


@user_story("to not see the setup reminder repeated on later messages in the same conversation")
def test_setup_reminder_not_re_emitted_on_second_message(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "sleep 60")

    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    send_chat_message(chat_panel, "Second message")
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 2, f"Expected two user_instructions files, got {len(files)}"
    _, first_contents = files[0]
    _, second_contents = files[1]
    assert _SETUP_RUNNING_PREAMBLE in first_contents
    assert _SETUP_RUNNING_PREAMBLE not in second_contents
    assert _SETUP_FAILED_PREAMBLE not in second_contents

    # Cancel the still-running setup so teardown does not race the long-lived bash.
    _cancel_running_setup(page)


@user_story("to have no setup reminder or pid-wait when I've explicitly cleared the setup command")
def test_no_setup_reminder_when_setup_command_cleared(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    _configure_setup_command(page, "")

    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 1
    _, contents = files[0]
    assert _SETUP_RUNNING_PREAMBLE not in contents
    assert _SETUP_FAILED_PREAMBLE not in contents

    # The runner was never started for this workspace, so no setup_log.txt
    # exists. This proves the provider's wait_for_pid path was never entered
    # (the workspace state dir contains no setup-log file at all).
    workspaces_dir = sculptor_instance_.sculptor_folder / "workspaces"
    new_dirs = set(workspaces_dir.glob("*")) - baseline
    setup_logs = [p for workspace_dir in new_dirs for p in workspace_dir.glob("state/setup_log.txt")]
    assert setup_logs == [], f"Expected no setup_log.txt; found {setup_logs}"
