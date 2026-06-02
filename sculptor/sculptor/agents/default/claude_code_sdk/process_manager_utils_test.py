import json
from pathlib import Path
from unittest.mock import MagicMock

from sculptor.foundation.agents.data_types.ids import AgentMessageID
from sculptor.foundation.agents.data_types.ids import ProjectID
from sculptor.foundation.agents.data_types.ids import TaskID
from sculptor.foundation.concurrency_group import ConcurrencyGroup
from sculptor.foundation.state.chat_state import AskUserQuestionData
from sculptor.foundation.state.chat_state import GenericToolContent
from sculptor.foundation.state.chat_state import QuestionOption
from sculptor.foundation.state.chat_state import UserQuestion
from sculptor.foundation.state.chat_state import make_plan_approval_question
from sculptor.foundation.state.claude_state import ParsedToolResultResponse
from sculptor.foundation.state.messages import ChatInputUserMessage
from sculptor.agents.default.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.agents.default.claude_code_sdk.harness import CLAUDE_CODE_HARNESS
from sculptor.agents.default.claude_code_sdk.process_manager_utils import get_claude_command
from sculptor.agents.default.claude_code_sdk.process_manager_utils import get_user_instructions
from sculptor.agents.default.claude_code_sdk.process_manager_utils import parse_claude_code_json_lines
from sculptor.agents.testing.fake_claude_jsonl import make_assistant_message
from sculptor.agents.testing.fake_claude_jsonl import make_tool_result_message
from sculptor.agents.testing.fake_claude_jsonl import make_tool_use_block
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.primitives.ids import LocalEnvironmentID
from sculptor.services.dependency_management_service import DependencyManagementService
from sculptor.services.workspace_service.environment_manager.environments.local_agent_execution_environment import (
    LocalAgentExecutionEnvironment,
)
from sculptor.services.workspace_service.environment_manager.environments.local_environment import LocalEnvironment
from sculptor.services.workspace_service.setup_command_runner import FailedSetup
from sculptor.services.workspace_service.setup_command_runner import RunningSetup
from sculptor.tasks.handlers.run_agent.git import run_git_command_in_environment


def test_get_user_instructions_enter_plan_mode_true() -> None:
    """When enter_plan_mode is True, the returned instructions should contain the plan-mode system instruction."""
    message = ChatInputUserMessage(text="Implement feature Y", enter_plan_mode=True)
    result = get_user_instructions(message, file_paths=())
    assert "<system-instructions>" in result
    assert "EnterPlanMode" in result
    assert "ExitPlanMode" in result
    assert "Implement feature Y" in result


def test_get_user_instructions_enter_plan_mode_false() -> None:
    """When enter_plan_mode is False (default), the instructions should NOT contain the plan-mode instruction."""
    message = ChatInputUserMessage(text="Implement feature Y", enter_plan_mode=False)
    result = get_user_instructions(message, file_paths=())
    assert "EnterPlanMode" not in result
    assert "Implement feature Y" in result


def test_get_user_instructions_enter_plan_mode_default() -> None:
    """By default, enter_plan_mode is False."""
    message = ChatInputUserMessage(text="Hello")
    result = get_user_instructions(message, file_paths=())
    assert "EnterPlanMode" not in result
    assert "Hello" in result


def test_get_user_instructions_exit_plan_mode() -> None:
    """When exit_plan_mode is True, the instructions should tell the agent to exit plan mode."""
    message = ChatInputUserMessage(text="Do something", exit_plan_mode=True)
    result = get_user_instructions(message, file_paths=())
    assert "ExitPlanMode" in result
    assert "disabled plan mode" in result
    assert "Do something" in result


def test_get_user_instructions_exit_plan_mode_not_sent_by_default() -> None:
    """By default, exit_plan_mode is False and no exit instruction is included."""
    message = ChatInputUserMessage(text="Hello")
    result = get_user_instructions(message, file_paths=())
    assert "disabled plan mode" not in result


_ENV_VAR_PREAMBLE = "The user has configured the following environment variables for this agent:"
_SKILL_INVOCATION_PREAMBLE = "The user invoked the "


def test_get_user_instructions_emits_skill_invocation_reminder() -> None:
    """When the user message starts with /<skill-name>, a system-reminder is prepended
    naming that skill and instructing the agent to invoke it via the Skill tool.

    Regression test for SCU-747: in stream-json mode the Claude Code TUI's
    slash-command auto-loader is bypassed, so the model never sees the SKILL.md
    content. For skills with disable-model-invocation: true, the skill is also
    hidden from the available-skills list, and the agent often replies "I don't
    see that skill" instead of invoking it.
    """
    message = ChatInputUserMessage(text="/address-comments XYZ")
    result = get_user_instructions(message, file_paths=())
    assert "<system-reminder>" in result
    assert _SKILL_INVOCATION_PREAMBLE + "/address-comments" in result
    assert "Skill tool" in result
    assert "/address-comments XYZ" in result


def test_get_user_instructions_skips_reminder_for_claude_cli_builtins() -> None:
    """`/compact` and `/context` are Claude Code TUI built-ins with no stream-json
    equivalent. Sending the skill-invocation reminder makes the model try to
    invoke them via the Skill tool, which always fails. Skip the reminder for
    these so the model can respond directly instead.
    """
    for builtin in ("compact", "context"):
        message = ChatInputUserMessage(text=f"/{builtin}")
        result = get_user_instructions(message, file_paths=())
        assert _SKILL_INVOCATION_PREAMBLE not in result
        assert f"/{builtin}" in result


def test_get_user_instructions_emits_env_var_reminder_when_first_message() -> None:
    message = ChatInputUserMessage(text="hello")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        env_var_names=("OPENAI_API_KEY", "GITHUB_TOKEN"),
    )
    assert "<system-reminder>" in result
    assert _ENV_VAR_PREAMBLE in result
    assert "OPENAI_API_KEY, GITHUB_TOKEN" in result
    assert "hello" in result
    assert result.startswith("<system-reminder>")


def test_get_user_instructions_no_env_var_reminder_when_not_first_message() -> None:
    message = ChatInputUserMessage(text="hello")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=False,
        env_var_names=("OPENAI_API_KEY", "GITHUB_TOKEN"),
    )
    assert _ENV_VAR_PREAMBLE not in result


def test_get_user_instructions_no_env_var_reminder_when_names_empty() -> None:
    message = ChatInputUserMessage(text="hello")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        env_var_names=(),
    )
    assert _ENV_VAR_PREAMBLE not in result


def test_get_user_instructions_env_var_reminder_omits_values() -> None:
    message = ChatInputUserMessage(text="hello")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        env_var_names=("OPENAI_API_KEY", "GITHUB_TOKEN"),
    )
    start = result.index("<system-reminder>")
    end = result.index("</system-reminder>") + len("</system-reminder>")
    reminder_block = result[start:end]
    assert "=" not in reminder_block


def test_get_user_instructions_env_var_reminder_block_ordering() -> None:
    message = ChatInputUserMessage(text="hello there", enter_plan_mode=True)
    result = get_user_instructions(
        message,
        file_paths=("a.txt", "b.txt"),
        is_first_message=True,
        env_var_names=("OPENAI_API_KEY",),
    )
    env_idx = result.index(_ENV_VAR_PREAMBLE)
    attach_idx = result.index("The user has attached these files")
    plan_idx = result.index("EnterPlanMode")
    text_idx = result.index("hello there")
    assert env_idx < attach_idx < plan_idx < text_idx


_SETUP_RUNNING_PREAMBLE = "A workspace setup command is currently running."
_SETUP_FAILED_PREAMBLE = "The workspace setup command exited non-zero."


def test_get_user_instructions_setup_running_reminder() -> None:
    message = ChatInputUserMessage(text="hello")
    setup_state = RunningSetup(command="npm ci", pid=12345, log_path="/abs/setup_log.txt")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        setup_state=setup_state,
    )
    assert result.startswith("<system-reminder>")
    assert _SETUP_RUNNING_PREAMBLE in result
    assert "Command: npm ci" in result
    assert "Bash PID: 12345" in result
    assert "Log file: /abs/setup_log.txt" in result


def test_get_user_instructions_setup_failed_reminder() -> None:
    message = ChatInputUserMessage(text="hello")
    setup_state = FailedSetup(command="npm ci", exit_code=2, log_path="/abs/setup_log.txt")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        setup_state=setup_state,
    )
    assert result.startswith("<system-reminder>")
    assert _SETUP_FAILED_PREAMBLE in result
    assert "Command: npm ci" in result
    assert "Exit code: 2" in result
    assert "Log file: /abs/setup_log.txt" in result


def test_get_user_instructions_no_setup_reminder_when_not_first() -> None:
    message = ChatInputUserMessage(text="hello")
    setup_state = RunningSetup(command="npm ci", pid=12345, log_path="/abs/setup_log.txt")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=False,
        setup_state=setup_state,
    )
    assert _SETUP_RUNNING_PREAMBLE not in result


def test_get_user_instructions_no_setup_reminder_when_state_none() -> None:
    message = ChatInputUserMessage(text="hello")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        setup_state=None,
    )
    assert _SETUP_RUNNING_PREAMBLE not in result
    assert _SETUP_FAILED_PREAMBLE not in result


def test_get_user_instructions_setup_above_env_vars() -> None:
    message = ChatInputUserMessage(text="hello")
    setup_state = RunningSetup(command="npm ci", pid=12345, log_path="/abs/setup_log.txt")
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        env_var_names=("FOO",),
        setup_state=setup_state,
    )
    setup_idx = result.index(_SETUP_RUNNING_PREAMBLE)
    env_idx = result.index(_ENV_VAR_PREAMBLE)
    assert setup_idx < env_idx


def test_get_user_instructions_env_var_reminder_not_emitted_for_resume() -> None:
    message = ResumeAgentResponseRunnerMessage(for_user_message_id=AgentMessageID())
    result = get_user_instructions(
        message,
        file_paths=(),
        is_first_message=True,
        env_var_names=("OPENAI_API_KEY",),
    )
    assert _ENV_VAR_PREAMBLE not in result
    assert "previous response was interrupted" in result


def test_get_user_instructions_preserves_angle_bracket_text() -> None:
    """User-typed angle bracket text like <Component /> must not be stripped."""
    message = ChatInputUserMessage(text="repeat: <DropdownMenu.TriggerIcon />")
    result = get_user_instructions(message, file_paths=())
    assert "<DropdownMenu.TriggerIcon />" in result


def test_get_user_instructions_preserves_user_typed_html_spans() -> None:
    """User-typed <span> tags must not be stripped — only sculptor-generated ones should be."""
    message = ChatInputUserMessage(text="use <span class='highlight'>this</span> styling")
    result = get_user_instructions(message, file_paths=())
    assert "<span class='highlight'>this</span>" in result


def test_get_user_instructions_strips_sculptor_tiptap_spans() -> None:
    """Sculptor-generated TipTap spans (with data-sculptor-node) must be stripped to their text content."""
    message = ChatInputUserMessage(text="see <span data-sculptor-node>README.md</span> for details")
    result = get_user_instructions(message, file_paths=())
    assert "see README.md for details" in result
    assert "data-sculptor-node" not in result
    assert "<span" not in result


def _make_question_answer_message() -> UserQuestionAnswerMessage:
    """Helper to create a UserQuestionAnswerMessage for testing."""
    question_data = AskUserQuestionData(
        questions=[
            UserQuestion(
                question="What language do you prefer?",
                header="Language",
                options=[QuestionOption(label="Python", description="A versatile language")],
                multi_select=False,
            )
        ],
        tool_use_id="toolu_test_123",
    )
    return UserQuestionAnswerMessage(
        answers={"What language do you prefer?": "Python"},
        question_data=question_data,
        tool_use_id="toolu_test_123",
    )


def test_get_user_instructions_answer_message_includes_plan_mode_when_active() -> None:
    """When answering a question while in plan mode, the instructions should tell the agent to re-enter plan mode."""
    message = _make_question_answer_message()
    result = get_user_instructions(message, file_paths=(), is_in_plan_mode=True)
    assert "EnterPlanMode" in result
    assert "plan mode" in result.lower()
    # The answer content should still be present
    assert "Python" in result


def test_get_user_instructions_answer_message_no_plan_mode_when_inactive() -> None:
    """When answering a question while NOT in plan mode, no plan mode reminder should be included."""
    message = _make_question_answer_message()
    result = get_user_instructions(message, file_paths=(), is_in_plan_mode=False)
    assert "plan mode" not in result.lower()
    assert "Python" in result


def test_get_user_instructions_answer_message_default_no_plan_mode() -> None:
    """By default (is_in_plan_mode not specified), no plan mode reminder should be included."""
    message = _make_question_answer_message()
    result = get_user_instructions(message, file_paths=())
    assert "plan mode" not in result.lower()
    assert "Python" in result


def _make_plan_approval_message(answer: str = "Approve plan") -> UserQuestionAnswerMessage:
    """Helper to create a plan approval/revision UserQuestionAnswerMessage."""
    question_data = make_plan_approval_question("toolu_plan_123")
    question_text = question_data.questions[0].question
    return UserQuestionAnswerMessage(
        answers={question_text: answer},
        question_data=question_data,
        tool_use_id="toolu_plan_123",
    )


def test_get_user_instructions_plan_approval_skips_reenter() -> None:
    """When the user approves the plan, the re-enter plan mode instruction should NOT be included."""
    message = _make_plan_approval_message("Approve plan")
    result = get_user_instructions(message, file_paths=(), is_in_plan_mode=True)
    assert "EnterPlanMode" not in result
    assert "approved" in result
    assert "Do NOT call ExitPlanMode" in result


def test_get_user_instructions_plan_approval_uses_explicit_messaging() -> None:
    """Plan approval should use explicit messaging, not the generic AskUserQuestion answer format."""
    message = _make_plan_approval_message("Approve plan")
    result = get_user_instructions(message, file_paths=(), is_in_plan_mode=True)
    assert "The user answered your questions" not in result
    assert "plan has been presented to the user" in result
    assert "already been handled" in result


def test_get_user_instructions_plan_revision_includes_reenter() -> None:
    """When the user revises the plan, the re-enter plan mode instruction SHOULD be included."""
    message = _make_plan_approval_message("Please also handle error cases")
    result = get_user_instructions(message, file_paths=(), is_in_plan_mode=True)
    assert "EnterPlanMode" in result
    assert "Please also handle error cases" in result
    assert "requested revisions" in result
    assert "call ExitPlanMode again" in result


def test_get_user_instructions_plan_revision_no_reenter_when_not_in_plan_mode() -> None:
    """When the user revises but we're not in plan mode, no re-enter reminder should be included."""
    message = _make_plan_approval_message("Please also handle error cases")
    result = get_user_instructions(message, file_paths=(), is_in_plan_mode=False)
    assert "EnterPlanMode" not in result
    assert "Please also handle error cases" in result
    assert "requested revisions" in result


# ---- get_claude_command tests ----


def _get_command_string(
    system_prompt: str = "",
    session_id: str | None = None,
    model_name: str | None = None,
    fast_mode: bool = False,
    effort: str | None = None,
) -> str:
    """Helper: call get_claude_command with defaults and return the bash command string."""
    cmd = get_claude_command(
        system_prompt=system_prompt,
        session_id=session_id,
        model_name=model_name,
        resolve_binary_path=lambda: "claude",
        harness=CLAUDE_CODE_HARNESS,
        fast_mode=fast_mode,
        effort=effort,
    )
    # cmd is ["bash", "-c", "<command string>"]
    return cmd[2]


def test_get_claude_command_fast_mode_adds_settings_flag() -> None:
    """When fast_mode=True, --settings with fastMode should appear in the command."""
    cmd = _get_command_string(fast_mode=True)
    assert "--settings" in cmd
    assert '"fastMode": true' in cmd or '"fastMode":true' in cmd


def test_get_claude_command_fast_mode_false_no_settings_flag() -> None:
    """When fast_mode=False, --settings should not appear."""
    cmd = _get_command_string(fast_mode=False)
    assert "--settings" not in cmd


def test_get_claude_command_effort_adds_effort_flag() -> None:
    """When effort is set, --effort should appear with the correct value."""
    for level in ("low", "medium", "high", "max"):
        cmd = _get_command_string(effort=level)
        assert f"--effort {level}" in cmd


def test_get_claude_command_effort_default_medium() -> None:
    """When effort is 'medium', --effort medium should be in the command."""
    cmd = _get_command_string(effort="medium")
    assert "--effort medium" in cmd


def test_get_claude_command_effort_none_no_effort_flag() -> None:
    """When effort is None, --effort should not appear."""
    cmd = _get_command_string(effort=None)
    assert "--effort" not in cmd


def test_get_claude_command_fast_mode_and_effort_combined() -> None:
    """Both --settings and --effort should appear when both are set."""
    cmd = _get_command_string(fast_mode=True, effort="high")
    assert "--settings" in cmd
    assert "--effort high" in cmd


# --- Tests for get_claude_command resolve_binary_path ---


def test_get_claude_command_with_binary_path() -> None:
    cmd = get_claude_command(
        system_prompt="test",
        session_id=None,
        model_name=None,
        resolve_binary_path=lambda: "/opt/claude/bin/claude",
        harness=CLAUDE_CODE_HARNESS,
    )
    bash_cmd = cmd[2]
    assert "env IS_SANDBOX=1 /opt/claude/bin/claude" in bash_cmd


def test_get_claude_command_fake_claude_ignores_binary_path() -> None:
    called = []

    def resolver() -> str:
        called.append(True)
        return "/opt/claude/bin/claude"

    cmd = get_claude_command(
        system_prompt="test",
        session_id=None,
        model_name=None,
        is_fake_claude=True,
        resolve_binary_path=resolver,
        harness=CLAUDE_CODE_HARNESS,
    )
    bash_cmd = cmd[2]
    assert "fake_claude.py" in bash_cmd
    assert "/opt/claude/bin/claude" not in bash_cmd
    assert not called, "resolver should not be called when is_fake_claude=True"


def test_get_claude_command_binary_path_with_spaces() -> None:
    cmd = get_claude_command(
        system_prompt="test",
        session_id=None,
        model_name=None,
        resolve_binary_path=lambda: "/path with spaces/claude",
        harness=CLAUDE_CODE_HARNESS,
    )
    bash_cmd = cmd[2]
    assert "'/path with spaces/claude'" in bash_cmd


def test_get_claude_command_includes_sculptor_mcp_config() -> None:
    """The Sculptor SDK MCP server must be registered via --mcp-config."""
    bash_cmd = _get_command_string()
    assert "--mcp-config" in bash_cmd
    expected_json = '{"mcpServers": {"sculptor": {"type": "sdk", "name": "sculptor"}}}'
    assert expected_json in bash_cmd


def test_get_claude_command_disables_builtin_auq_and_exit_plan_mode() -> None:
    """Built-in AskUserQuestion and ExitPlanMode must be suppressed via --disallowed-tools."""
    bash_cmd = _get_command_string()
    assert "--disallowed-tools" in bash_cmd
    assert "AskUserQuestion,ExitPlanMode" in bash_cmd


# ---------------------------------------------------------------------------
# Prototype: deterministically emulate Claude stdout for a failed Edit.
#
# Models the pattern surfaced in session d4fffd07-0662-4b40-8f73-5d8ed2c32e9e
# where Claude emitted an Edit tool_use without first Reading the file and got
# back `is_error=True` with "File has not been read yet." The file on disk is
# unchanged by the failed Edit, so DiffTracker must produce no diff, and
# `_create_tool_content` must fall through to GenericToolContent so the real
# error text reaches the chip popover instead of a bogus diff body.
# ---------------------------------------------------------------------------


def _make_repo_with_file_ending_in_newline(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> tuple[LocalAgentExecutionEnvironment, str]:
    """Create a real git repo in ``tmp_path`` containing one committed file
    whose content ends in a newline. Returns (environment, absolute_file_path)."""
    local_env = LocalEnvironment.create(
        environment_id=LocalEnvironmentID(str(tmp_path)),
        project_id=ProjectID(),
        concurrency_group=test_root_concurrency_group,
        repo_host_path=tmp_path,
    )
    dep_service = DependencyManagementService.model_construct(concurrency_group=MagicMock(spec=ConcurrencyGroup))
    environment = LocalAgentExecutionEnvironment(local_env, TaskID(), dep_service)

    file_path = str(tmp_path / "repo.py")
    environment.write_file(file_path, "print('hello')\n")
    run_git_command_in_environment(environment=environment, command=["git", "init"])
    run_git_command_in_environment(environment=environment, command=["git", "add", "."])
    run_git_command_in_environment(environment=environment, command=["git", "commit", "-am", "initial"])
    return environment, file_path


def test_failed_edit_on_unchanged_file_preserves_error_text(
    tmp_path: Path, test_root_concurrency_group: ConcurrencyGroup
) -> None:
    """When Claude emits an Edit tool_use, gets back is_error=True, and leaves the
    file untouched, the resulting ToolResultBlock must carry the error text as
    GenericToolContent — not a phantom DiffToolContent synthesized by DiffTracker.

    Regression: pre-fix, DiffTracker's git-tree snapshot was `.strip()`ed, so an
    unchanged file ending in `\\n` produced a "\\ No newline at end of file" diff,
    and `_create_tool_content` substituted that bogus diff for Claude's real
    error message (e.g. "File has not been read yet").
    """
    environment, file_path = _make_repo_with_file_ending_in_newline(tmp_path, test_root_concurrency_group)
    diff_tracker = DiffTracker(environment=environment)

    tool_use_id = "toolu_fake_failed_edit"
    tool_input = {
        "file_path": file_path,
        "old_string": "print('hello')",
        "new_string": "print('hello world')",
    }
    error_text = "<tool_use_error>File has not been read yet. Read it first before writing to it.</tool_use_error>"

    # ClaudeOutputProcessor populates tool_use_map when it observes an assistant
    # message; parse_claude_code_json_lines does not do that itself. Mirror that
    # side-effect here so the subsequent tool_result carries the real tool name.
    tool_use_map: dict = {tool_use_id: ("Edit", tool_input)}
    assistant_line = json.dumps(
        make_assistant_message(
            message_id="msg_fake",
            content_blocks=[make_tool_use_block(tool_use_id, "Edit", tool_input)],
        )
    )
    parse_claude_code_json_lines(assistant_line, tool_use_map, diff_tracker)

    result_line = json.dumps(make_tool_result_message(tool_use_id=tool_use_id, content=error_text, is_error=True))
    parsed = parse_claude_code_json_lines(result_line, tool_use_map, diff_tracker)

    assert isinstance(parsed, ParsedToolResultResponse), f"expected ParsedToolResultResponse, got {type(parsed)}"
    (block,) = parsed.content_blocks
    assert block.is_error is True
    assert isinstance(block.content, GenericToolContent), (
        f"Failed Edit on unchanged file must not synthesize a DiffToolContent; got {type(block.content).__name__}: {block.content!r}"
    )
    assert "File has not been read yet" in block.content.text
