"""Integration tests for project environment variable loading.

Tests verify that variables from .sculptor/.env are available in:
- Agent subprocesses
- Terminal sessions
- Default override behavior
- Settings page display
"""

from pathlib import Path
from typing import Generator

import pytest
from playwright.sync_api import expect

from sculptor.testing.elements.chat_panel import send_chat_message
from sculptor.testing.elements.chat_panel import wait_for_completed_message_count
from sculptor.testing.elements.terminal import get_add_terminal_button
from sculptor.testing.elements.terminal import get_terminal_tabs
from sculptor.testing.elements.terminal import open_terminal_and_wait
from sculptor.testing.elements.terminal import run_command_in_active_terminal
from sculptor.testing.elements.terminal import wait_for_xterm_substring
from sculptor.testing.pages.project_layout import PlaywrightProjectLayoutPage
from sculptor.testing.pages.task_page import PlaywrightTaskPage
from sculptor.testing.playwright_utils import navigate_to_settings_page
from sculptor.testing.playwright_utils import start_task_and_wait_for_ready
from sculptor.testing.sculptor_instance import SculptorInstance
from sculptor.testing.sculptor_instance import SculptorInstanceFactory
from sculptor.testing.user_stories import user_story

_ENV_VAR_PREAMBLE = "The user has configured the following environment variables for this agent:"


def _snapshot_workspace_dirs(sculptor_folder: Path) -> set[Path]:
    """Snapshot the set of existing on-disk workspace dirs.

    Used to scope ``_read_user_instructions_files`` to only the workspaces
    created during the test, ignoring any leaked from a previous test. The
    workspace directory name is a fresh ``uuid4().hex`` (see
    ``DefaultEnvironmentManager._create_workspace_path``) and has no
    relationship to the ``WorkspaceID`` exposed in the URL or API, so we
    can't filter by ID — a baseline diff is the simplest reliable handle.
    """
    workspaces_dir = sculptor_folder / "workspaces"
    if not workspaces_dir.exists():
        return set()
    return set(workspaces_dir.glob("*"))


def _read_user_instructions_files(sculptor_folder: Path, baseline_workspace_dirs: set[Path]) -> list[tuple[Path, str]]:
    """Return ``user_instructions_*.txt`` files from workspaces created since
    ``baseline_workspace_dirs`` was captured, oldest first.

    The shared per-test cleanup deletes workspaces via API but the on-disk
    directory is removed asynchronously; under offload's slower I/O the
    orphan can persist into the next test. Globbing across all workspaces
    would pick it up, so we scope to dirs that didn't exist at baseline.
    """
    workspaces_dir = sculptor_folder / "workspaces"
    new_dirs = sorted(set(workspaces_dir.glob("*")) - baseline_workspace_dirs)
    paths: list[Path] = []
    for workspace_dir in new_dirs:
        paths.extend(workspace_dir.glob("state/tasks/*/user_instructions_*.txt"))
    paths.sort(key=lambda p: p.stat().st_mtime)
    return [(p, p.read_text()) for p in paths]


@pytest.fixture(autouse=True)
def _isolate_dotenv_files(request: pytest.FixtureRequest) -> Generator[None, None, None]:
    """Wipe both .env files before and after each shared-instance test.

    ``load_project_env_vars`` merges the global ``~/.sculptor/.env`` and
    project ``<repo>/.sculptor/.env``, so a stale file from either side
    injects env-var names into the first-message reminder and breaks
    ``test_env_var_reminder_omitted_when_no_dotenv``. The session-scoped
    ``sculptor_folder`` is never reset by ``_pre_test`` (only the project
    repo is, via ``_create_fresh_repo``), so the global ``.env`` is the
    actual leak source — but we handle both for symmetry.

    Factory tests are inherently isolated (fresh ``sculptor_folder`` and
    ``base_repo`` per test) and are skipped here.
    """
    if "sculptor_instance_" not in request.fixturenames:
        yield
        return

    instance = request.getfixturevalue("sculptor_instance_")
    global_env = instance.sculptor_folder / ".env"
    project_env = instance.project_path / ".sculptor" / ".env"

    global_env.unlink(missing_ok=True)
    project_env.unlink(missing_ok=True)
    try:
        yield
    finally:
        global_env.unlink(missing_ok=True)
        project_env.unlink(missing_ok=True)


@user_story("to have project env vars available in agent subprocesses")
def test_agent_subprocess_has_project_env_vars(sculptor_instance_: SculptorInstance) -> None:
    """Agent subprocesses should see env vars loaded from .sculptor/.env.

    Steps:
    1. Create .sculptor/.env in the project repo before workspace creation.
    2. Create a workspace with a FakeClaude bash command that echoes the env var.
    3. Verify the chat panel contains the echoed env var value.
    """
    env_dir = sculptor_instance_.project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("SCTEST_AGENT_VAR=hello_from_dotenv\n")

    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo AGENT_ENV_CHECK:$SCTEST_AGENT_VAR"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Expand the bash pill to reveal the command output
    bash_pill = chat_panel.get_bash_blocks().first
    expect(bash_pill).to_be_visible()
    bash_pill.click()

    bash_output = chat_panel.get_bash_output()
    expect(bash_output).to_contain_text("AGENT_ENV_CHECK:hello_from_dotenv")


@user_story("to have project env vars available in terminal sessions")
def test_terminal_has_project_env_vars(sculptor_instance_: SculptorInstance) -> None:
    """Terminal sessions should see env vars loaded from .sculptor/.env.

    Steps:
    1. Create .sculptor/.env in the project repo before workspace creation.
    2. Create a workspace and open the terminal.
    3. Echo the env var in the terminal and verify the output.
    """
    env_dir = sculptor_instance_.project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("SCTEST_TERMINAL_VAR=terminal_dotenv_value\n")

    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    run_command_in_active_terminal(page, 'echo "TERM_ENV_CHECK:${SCTEST_TERMINAL_VAR:-NOT_SET}"')
    wait_for_xterm_substring(page, "TERM_ENV_CHECK:terminal_dotenv_value")


@user_story("to have .env vars not override existing env vars by default")
def test_agent_subprocess_env_var_no_override_by_default(sculptor_instance_: SculptorInstance) -> None:
    """By default, .sculptor/.env values should NOT override existing environment variables.

    Steps:
    1. Create .sculptor/.env with PATH=/nonexistent and a unique test var.
    2. Create a workspace with a FakeClaude bash command that tests both variables.
    3. Verify the unique test var is injected, and PATH was NOT overridden (echo still works).
    """
    env_dir = sculptor_instance_.project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("PATH=/nonexistent\nSCTEST_UNIQUE_VAR=dotenv_present\n")

    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo OVERRIDE_CHECK:$SCTEST_UNIQUE_VAR && ls / >/dev/null 2>&1 && echo PATH_OK"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    # Expand the bash pill to reveal the command output
    bash_pill = chat_panel.get_bash_blocks().first
    expect(bash_pill).to_be_visible()
    bash_pill.click()

    bash_output = chat_panel.get_bash_output()
    # SCTEST_UNIQUE_VAR should be injected (it didn't exist before)
    expect(bash_output).to_contain_text("OVERRIDE_CHECK:dotenv_present")
    # PATH was NOT overridden, so `ls` (which requires PATH lookup) succeeded
    expect(bash_output).to_contain_text("PATH_OK")


@user_story("to have newly-added .env vars available to terminals opened later")
def test_terminal_picks_up_newly_added_env_var(sculptor_instance_: SculptorInstance) -> None:
    """A terminal opened after a global .env update should see the newly-added var.

    Regression test for the case where TerminalEnvironmentConfig.extra_env was
    snapshotted at workspace startup, so terminals created later still saw the
    stale env even after ~/.sculptor/.env was updated.

    The initial terminal at index 0 is created during workspace load (before the
    user has had a chance to update the .env file), so the test exercises the
    "open a new terminal tab" flow: writes the var to the global .env, then
    clicks the "+" button to create a second terminal (index > 0), which goes
    through the lazy create_terminal_for_environment path.
    """
    global_env_file = sculptor_instance_.sculptor_folder / ".env"
    if global_env_file.exists():
        global_env_file.unlink()

    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    open_terminal_and_wait(page)

    global_env_file.write_text("SCTEST_LATE_TERMINAL_VAR=terminal_loaded_after\n")

    get_add_terminal_button(page).click()
    expect(get_terminal_tabs(page)).to_have_count(2)
    expect(page.get_by_label("Terminal input")).to_have_count(2)

    run_command_in_active_terminal(page, 'echo "TERM_LATE_CHECK:${SCTEST_LATE_TERMINAL_VAR:-MISSING}"')
    wait_for_xterm_substring(page, "TERM_LATE_CHECK:terminal_loaded_after")


@user_story("to have newly-added .env vars available to existing agents")
def test_existing_agent_sees_newly_added_env_var(sculptor_instance_: SculptorInstance) -> None:
    """An existing agent should see env vars added to the global .env after the agent started.

    Regression test for the case where adding a variable to ~/.sculptor/.env was not
    visible to an in-progress agent's subsequent commands, because the env vars were
    cached on LocalEnvironment at workspace create/resume and never refreshed.

    Steps:
    1. Make sure the global .env file has no pre-defined SCTEST_LATE_VAR.
    2. Start a workspace and run a bash command that prints the var (should be MISSING).
    3. Write SCTEST_LATE_VAR=loaded_after_start to the global .env while the agent runs.
    4. Send a follow-up bash command and verify the agent's subprocess now sees the var.
    """
    global_env_file = sculptor_instance_.sculptor_folder / ".env"
    if global_env_file.exists():
        global_env_file.unlink()

    page = sculptor_instance_.page
    task_page = start_task_and_wait_for_ready(
        sculptor_page=page,
        prompt='fake_claude:bash `{"command": "echo BEFORE_ADD:[${SCTEST_LATE_VAR:-MISSING}]"}`',
    )

    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    bash_pills = chat_panel.get_bash_blocks()
    expect(bash_pills.first).to_be_visible()
    bash_pills.first.click()
    bash_output = chat_panel.get_bash_output()
    expect(bash_output).to_contain_text("BEFORE_ADD:[MISSING]")
    # Close the popover and confirm it dismissed before opening the next one.
    # Without the confirmation, the second pill click can race against a still-
    # mounted popover and land on the previous output instead.
    page.keyboard.press("Escape")
    expect(bash_output).not_to_be_visible()

    global_env_file.write_text("SCTEST_LATE_VAR=loaded_after_start\n")

    send_chat_message(
        chat_panel=chat_panel,
        message='fake_claude:bash `{"command": "echo AFTER_ADD:[${SCTEST_LATE_VAR:-MISSING}]"}`',
    )
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

    bash_pills = chat_panel.get_bash_blocks()
    expect(bash_pills).to_have_count(2)
    bash_pills.nth(1).click()
    bash_output = chat_panel.get_bash_output()
    expect(bash_output).to_contain_text("AFTER_ADD:[loaded_after_start]")


@user_story("to see loaded env var names in the settings page")
def test_env_var_names_shown_in_settings(sculptor_instance_: SculptorInstance) -> None:
    """After starting a workspace with .sculptor/.env, the settings page should display the loaded variable names.

    Steps:
    1. Create .sculptor/.env with two test variables.
    2. Start a task to create a workspace (which loads the .env).
    3. Navigate to the settings page and open the env vars section.
    4. Verify the variable names appear in the loaded names list.
    """
    env_dir = sculptor_instance_.project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("SCTEST_SETTING_A=value_a\nSCTEST_SETTING_B=value_b\n")

    page = sculptor_instance_.page
    start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")

    settings_page = navigate_to_settings_page(page=page)
    env_vars_section = settings_page.click_on_env_vars()

    names_list = env_vars_section.get_names_list()
    expect(names_list).to_contain_text("SCTEST_SETTING_A")
    expect(names_list).to_contain_text("SCTEST_SETTING_B")


@user_story("to see configured env var names in the agent's first message")
def test_env_var_reminder_emitted_on_first_message(sculptor_instance_: SculptorInstance) -> None:
    env_dir = sculptor_instance_.project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("SCTEST_REMINDER_VAR_A=value_a\nSCTEST_REMINDER_VAR_B=value_b\n")

    page = sculptor_instance_.page
    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) == 1, f"Expected exactly one user_instructions file, got {len(files)}"
    _, contents = files[0]
    assert "<system-reminder>" in contents
    assert _ENV_VAR_PREAMBLE in contents
    assert "SCTEST_REMINDER_VAR_A" in contents
    assert "SCTEST_REMINDER_VAR_B" in contents
    start = contents.index("<system-reminder>")
    end = contents.index("</system-reminder>") + len("</system-reminder>")
    reminder_block = contents[start:end]
    assert "=" not in reminder_block
    assert "value_a" not in reminder_block
    assert "value_b" not in reminder_block


@user_story("to not see the env-var reminder repeated on later messages in the same conversation")
def test_env_var_reminder_not_re_emitted_on_second_message(sculptor_instance_: SculptorInstance) -> None:
    env_dir = sculptor_instance_.project_path / ".sculptor"
    env_dir.mkdir(parents=True, exist_ok=True)
    (env_dir / ".env").write_text("SCTEST_REMINDER_VAR_A=value_a\nSCTEST_REMINDER_VAR_B=value_b\n")

    page = sculptor_instance_.page
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
    assert _ENV_VAR_PREAMBLE in first_contents
    assert _ENV_VAR_PREAMBLE not in second_contents


@user_story("to not see the env-var reminder repeated after restarting Sculptor mid-conversation")
def test_env_var_reminder_not_re_emitted_after_app_restart(
    sculptor_instance_factory_: SculptorInstanceFactory,
) -> None:
    # The factory reuses one ``sculptor_folder`` across spawn_instance() calls
    # (state must persist across the simulated app restart), so a baseline
    # captured in the first spawn — before the test creates its workspace —
    # is also valid in the second spawn: the workspace dir created in spawn 1
    # is reopened in spawn 2, not recreated, so it remains the only "new"
    # entry relative to that baseline.
    sculptor_folder: Path
    baseline: set[Path]

    with sculptor_instance_factory_.spawn_instance() as instance:
        sculptor_folder = instance.sculptor_folder

        env_dir = instance.project_path / ".sculptor"
        env_dir.mkdir(parents=True, exist_ok=True)
        (env_dir / ".env").write_text("SCTEST_RESUME_VAR_A=value_a\nSCTEST_RESUME_VAR_B=value_b\n")

        baseline = _snapshot_workspace_dirs(sculptor_folder)
        task_page = start_task_and_wait_for_ready(sculptor_page=instance.page, prompt="Hello")
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        files = _read_user_instructions_files(sculptor_folder, baseline)
        assert len(files) == 1
        assert _ENV_VAR_PREAMBLE in files[0][1]

    with sculptor_instance_factory_.spawn_instance() as instance:
        layout = PlaywrightProjectLayoutPage(page=instance.page)
        workspace_tab = layout.get_workspace_tabs().first
        expect(workspace_tab).to_be_visible()
        workspace_tab.click()

        task_page = PlaywrightTaskPage(page=instance.page)
        chat_panel = task_page.get_chat_panel()
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

        send_chat_message(chat_panel, "Post-restart message")
        wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=4)

        files = _read_user_instructions_files(sculptor_folder, baseline)
        assert len(files) == 2, f"Expected two user_instructions files after restart, got {len(files)}"
        _, post_restart_contents = files[1]
        assert _ENV_VAR_PREAMBLE not in post_restart_contents


@user_story("to not see the env-var reminder when no .env is configured")
def test_env_var_reminder_omitted_when_no_dotenv(sculptor_instance_: SculptorInstance) -> None:
    page = sculptor_instance_.page
    baseline = _snapshot_workspace_dirs(sculptor_instance_.sculptor_folder)
    task_page = start_task_and_wait_for_ready(sculptor_page=page, prompt="Hello")
    chat_panel = task_page.get_chat_panel()
    wait_for_completed_message_count(chat_panel=chat_panel, expected_message_count=2)

    files = _read_user_instructions_files(sculptor_instance_.sculptor_folder, baseline)
    assert len(files) >= 1
    for _, contents in files:
        assert _ENV_VAR_PREAMBLE not in contents
