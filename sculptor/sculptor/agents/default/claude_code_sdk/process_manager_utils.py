import html
import json
import re
import shlex
import sys
from collections.abc import Callable
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import cast

from loguru import logger

from sculptor.agents.default.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.agents.default.claude_code_sdk.harness import ClaudeCodeHarness
from sculptor.foundation.async_monkey_patches import log_exception
from sculptor.interfaces.agents.agent import ChatInputUserMessage
from sculptor.interfaces.agents.agent import ParsedAgentResponseType
from sculptor.interfaces.agents.agent import ParsedToolResultResponse
from sculptor.interfaces.agents.agent import ResumeAgentResponseRunnerMessage
from sculptor.interfaces.agents.agent import UserQuestionAnswerMessage
from sculptor.interfaces.agents.errors import IllegalOperationError
from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.interfaces.environments.agent_execution_environment import AgentExecutionEnvironment
from sculptor.services.workspace_service.setup_command_runner import RunningSetup
from sculptor.services.workspace_service.setup_command_runner import SetupReminderState
from sculptor.state.chat_state import DiffToolContent
from sculptor.state.chat_state import GenericToolContent
from sculptor.state.chat_state import SimpleToolContent
from sculptor.state.chat_state import ToolInput
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.claude_state import ContentBlockStopEvent
from sculptor.state.claude_state import MessageStartEvent
from sculptor.state.claude_state import MessageStopEvent
from sculptor.state.claude_state import ParsedStreamEventTypes
from sculptor.state.claude_state import ParsedToolResultResponseSimple
from sculptor.state.claude_state import ParsedUserResponse
from sculptor.state.claude_state import TextBlockStartEvent
from sculptor.state.claude_state import TextDeltaEvent
from sculptor.state.claude_state import ToolBlockStartEvent
from sculptor.state.claude_state import ToolInputDeltaEvent
from sculptor.state.claude_state import parse_claude_code_json_lines_simple


def get_claude_command(
    system_prompt: str,
    session_id: str | None,
    model_name: str | None,
    resolve_binary_path: Callable[[], str],
    harness: ClaudeCodeHarness,
    enable_streaming: bool = False,
    is_fake_claude: bool = False,
    plugin_dirs: Sequence[Path] = (),
    fast_mode: bool = False,
    effort: str | None = None,
) -> list[str]:
    if is_fake_claude:
        script_path = Path(__file__).parent.parent.parent / "testing" / "fake_claude.py"
        python_path = sys.executable
        executable = f"{shlex.quote(python_path)} {shlex.quote(str(script_path))}"
    else:
        binary_path = resolve_binary_path()
        # Important not to use /imbue/nix_bin/claude here, since it won't have the right certificates set up and claude will stall.
        executable = f"env IS_SANDBOX=1 {shlex.quote(binary_path)}"

    # `exec` replaces the bash process with claude so that signals (SIGTERM/SIGKILL) are delivered
    # directly to claude rather than to bash, which would otherwise exit without forwarding them.
    # Uses --input-format stream-json to enable the stdin control protocol (for graceful interrupts).
    # The user prompt is sent as a JSON message on stdin after process start.
    claude_command = (
        f"exec {executable} --dangerously-skip-permissions --permission-prompt-tool stdio"
        + " --output-format=stream-json --verbose"
        + " --input-format stream-json"
        + " --include-hook-events"
    )

    # Register Sculptor's in-process SDK MCP server (handled by ClaudeOutputProcessor's
    # mcp_message control_request branch) and suppress the built-in AskUserQuestion /
    # ExitPlanMode tools in favour of the mcp__sculptor__* replacements. The matching
    # system-prompt addendum is spliced in `_get_combined_system_prompt`.
    mcp_server_name = harness.mcp_server_name
    mcp_config_json = json.dumps({"mcpServers": {mcp_server_name: {"type": "sdk", "name": mcp_server_name}}})
    claude_command += f" --mcp-config {shlex.quote(mcp_config_json)}"
    claude_command += f" --disallowed-tools {shlex.quote('AskUserQuestion,ExitPlanMode')}"

    # Enable streaming for lower time-to-first-token
    if enable_streaming:
        claude_command += " --include-partial-messages"

    # If a session ID is provided, then we resume the existing conversation
    if session_id:
        claude_command += f" --resume {shlex.quote(session_id)}"

    if system_prompt:
        claude_command += f" --append-system-prompt {shlex.quote(system_prompt)}"

    if model_name:
        claude_command += f" --model {shlex.quote(model_name)}"

    for plugin_dir in plugin_dirs:
        claude_command += f" --plugin-dir {shlex.quote(str(plugin_dir))}"

    if fast_mode:
        settings_json = json.dumps({"fastMode": True})
        claude_command += f" --settings {shlex.quote(settings_json)}"

    if effort:
        claude_command += f" --effort {shlex.quote(effort)}"

    return ["bash", "-c", claude_command]


_PLAN_APPROVE_ANSWER = "Approve plan"
_PLAN_APPROVAL_HEADER = "Plan approval"


def is_plan_approval_question(message: UserQuestionAnswerMessage) -> bool:
    """Check if this message is a response to the ExitPlanMode plan approval prompt."""
    return any(q.header == _PLAN_APPROVAL_HEADER for q in message.question_data.questions)


def is_plan_approval(message: UserQuestionAnswerMessage) -> bool:
    """Check if a UserQuestionAnswerMessage is approving (not revising) a plan."""
    if not is_plan_approval_question(message):
        return False
    return any(v.strip() == _PLAN_APPROVE_ANSWER for v in message.answers.values())


def _get_plan_approval_instructions(
    message: UserQuestionAnswerMessage,
    plan_approval: bool,
    is_in_plan_mode: bool,
) -> str:
    """Build the instructions sent to the agent after a plan approval/revision/dismissal.

    Uses explicit messaging so the agent knows ExitPlanMode was already called
    on its behalf, even if the original call was orphaned during a session resume.
    """
    if plan_approval:
        return "[Sculptor: Your plan has been presented to the user and they approved it. Proceed to implement the plan now. Do NOT call ExitPlanMode — it has already been handled.]"

    # User requested revisions or dismissed — extract their notes
    revision_notes = ""
    for question in message.question_data.questions:
        answer_value = message.answers.get(question.question, "")
        if answer_value.strip():
            revision_notes = answer_value.strip()

    instructions = f"[Sculptor: Your plan has been presented to the user and they requested revisions. Revise your plan based on their feedback, then call ExitPlanMode again to resubmit.]\n\n**User feedback:** {revision_notes}"

    if is_in_plan_mode:
        instructions += """

<system-reminder>
Note: because you're running inside Sculptor, every new message you receive is via a new CLI invocation of `claude -p`. Therefore, even though you remember that you're in plan mode, the CLI harness has now lost that state. You must call EnterPlanMode again to remind the harness, otherwise your future ExitPlanMode will fail.
</system-reminder>"""

    return instructions


_SKILL_INVOCATION_RE = re.compile(r"^/([a-zA-Z][a-zA-Z0-9:_-]*)")

# Claude Code TUI built-ins that the CLI intercepts in interactive mode but
# that have no equivalent in stream-json mode. Skip the skill-invocation
# reminder for these so the model doesn't try (and fail) to call Skill().
_CLAUDE_CLI_BUILTINS: frozenset[str] = frozenset({"compact", "context"})


def _build_skill_invocation_reminder(skill_name: str) -> str:
    """Reminder injected when a user message starts with /<skill-name>.

    Stream-json mode bypasses Claude Code's TUI slash-command auto-loader, so the
    SKILL.md is not auto-injected and skills with disable-model-invocation: true
    are hidden from the available-skills list. Without this reminder the agent
    often tells the user the skill doesn't exist instead of invoking it.
    """
    return f"""<system-reminder>
The user invoked the /{skill_name} skill. If this skill is not in your available-skills list, it may be hidden (e.g. due to `disable-model-invocation: true`). Use the Skill tool to invoke it (skill="{skill_name}"). If the skill name is not found, do NOT search the filesystem — call the Skill tool first; the harness will return a clear error if the skill truly doesn't exist.
</system-reminder>

"""


def _build_setup_reminder(setup_state: SetupReminderState) -> str:
    if isinstance(setup_state, RunningSetup):
        return f"""<system-reminder>
A workspace setup command is currently running.

Command: {setup_state.command}
Bash PID: {setup_state.pid}
Log file: {setup_state.log_path}

The setup command may modify workspace state — files, dependencies, git, locks — concurrently with your work. Before proceeding, consider whether your task depends on that state being settled, or whether your actions could conflict with what setup is doing. If so, wait on this PID; otherwise, continue.
</system-reminder>

"""
    return f"""<system-reminder>
The workspace setup command exited non-zero.

Command: {setup_state.command}
Exit code: {setup_state.exit_code}
Log file: {setup_state.log_path}
</system-reminder>

"""


# Injected on the first message of an auto-rename-enabled workspace. Asks the agent to give
# the workspace and itself descriptive names once it understands the task. References the
# SCULPT_WORKSPACE_ID / SCULPT_AGENT_ID env vars (always present in the agent's shell), so no
# ids need threading in here; the agent's bash expands them. The id vars are left unquoted
# (ids are space-free) so each command line carries a single quoted literal — two adjacent
# "..." literals here would trip the no-implicit-string-concat ratchet.
_AUTO_RENAME_REMINDER = """<system-reminder>
This is the first message in a new Sculptor workspace, whose workspace and agent both have auto-generated placeholder names. Once you understand what this task is about, give them a concise, descriptive name (3-6 words) that reflects the task by running BOTH of these commands once:

  sculpt workspace rename $SCULPT_WORKSPACE_ID "<name>"
  sculpt agent rename $SCULPT_AGENT_ID "<name>"

Do this early and only once. Do not ask the user about it, do not mention it in your reply, and do not let it delay the real work. If a command fails, ignore it and carry on with the task.
</system-reminder>

"""


def get_user_instructions(
    message: ChatInputUserMessage | ResumeAgentResponseRunnerMessage | UserQuestionAnswerMessage,
    file_paths: tuple[str, ...],
    is_in_plan_mode: bool = False,
    env_var_names: Sequence[str] = (),
    is_first_message: bool = False,
    setup_state: SetupReminderState | None = None,
    enable_auto_rename: bool = False,
) -> str:
    if isinstance(message, ChatInputUserMessage):
        user_instructions = _strip_and_unescape_html(message.text)
        skill_invocation_match = _SKILL_INVOCATION_RE.match(user_instructions)
        if message.enter_plan_mode:
            plan_instructions = """<system-instructions>
CRITICAL: The user has enabled plan mode. You MUST call the EnterPlanMode tool IMMEDIATELY as your very first action, before doing anything else. Do not skip this step regardless of the task. After entering plan mode, explore the codebase, design your approach, and present the plan for approval via ExitPlanMode before writing any code.
</system-instructions>

"""
            user_instructions = plan_instructions + user_instructions
        elif message.exit_plan_mode:
            exit_instructions = """<system-instructions>
CRITICAL: The user has disabled plan mode. You MUST call the ExitPlanMode tool IMMEDIATELY as your very first action to exit plan mode, then proceed with the user's request normally.
</system-instructions>

"""
            user_instructions = exit_instructions + user_instructions
        if file_paths:
            file_paths_str = "\n- ".join(file_paths)
            file_instructions = f"""<system-instructions>
The user has attached these files. Read them before proceeding.
{file_paths_str}
</system-instructions>

"""
            user_instructions = file_instructions + user_instructions
        if is_first_message and env_var_names:
            env_var_instructions = f"""<system-reminder>
The user has configured the following environment variables for this agent: {", ".join(env_var_names)}
</system-reminder>

"""
            user_instructions = env_var_instructions + user_instructions
        if is_first_message and setup_state is not None:
            user_instructions = _build_setup_reminder(setup_state) + user_instructions
        if is_first_message and enable_auto_rename:
            user_instructions = _AUTO_RENAME_REMINDER + user_instructions
        if skill_invocation_match is not None:
            skill_name = skill_invocation_match.group(1)
            if skill_name not in _CLAUDE_CLI_BUILTINS:
                user_instructions = _build_skill_invocation_reminder(skill_name) + user_instructions
    elif isinstance(message, ResumeAgentResponseRunnerMessage):
        user_instructions = """<system-reminder>\nYour previous response was interrupted. Please continue from where you left off. DO NOT respond to this message, just keep continuing with your previous reply as if you had not been stopped part-way through.\n</system-reminder>"""
    elif isinstance(message, UserQuestionAnswerMessage):
        plan_approval = is_plan_approval(message)
        logger.debug(
            "UserQuestionAnswerMessage: is_in_plan_mode={}, is_plan_approval={}, answers={}",
            is_in_plan_mode,
            plan_approval,
            message.answers,
        )
        if is_plan_approval_question(message):
            user_instructions = _get_plan_approval_instructions(message, plan_approval, is_in_plan_mode)
        else:
            answer_lines = ["[Sculptor: The user answered your questions]", ""]
            for question in message.question_data.questions:
                answer_value = message.answers.get(question.question, "")
                answer_lines.append(f"**{question.header}:** {answer_value}")
            user_instructions = "\n".join(answer_lines)
            if is_in_plan_mode:
                user_instructions += """

<system-reminder>
Note: because you're running inside Sculptor, every new message you receive is via a new CLI invocation of `claude -p`. Therefore, even though you remember that you're in plan mode, the CLI harness has now lost that state. You must call EnterPlanMode again to remind the harness, otherwise your future ExitPlanMode will fail.
</system-reminder>"""
    else:
        raise IllegalOperationError(f"Unexpected message type: {type(message)}")
    return user_instructions


_SCULPTOR_NODE_SPAN_RE = re.compile(
    r"<span\s+data-sculptor-node(?:\s+[^>]*)?>(.*?)</span>",
    re.DOTALL,
)


def _strip_and_unescape_html(text: str) -> str:
    """Strip Sculptor-generated TipTap HTML and unescape HTML entities.

    The TipTap editor wraps inline nodes (e.g. file mentions, skill chips) in
    ``<span data-sculptor-node …>…</span>`` tags during markdown serialisation.
    The span may carry additional ``data-*`` attributes (e.g.
    ``data-skill-description`` / ``data-skill-type``) used by the UI to
    restore hover-card metadata across draft round-trips; those are stripped
    here along with the wrapper.  All other angle-bracket content (including
    user-typed JSX, HTML, or generic ``<tags>``) is preserved.
    """
    stripped = _SCULPTOR_NODE_SPAN_RE.sub(r"\1", text)
    return html.unescape(stripped)


def parse_claude_code_json_lines(
    line: str,
    tool_use_map: dict[str, tuple[str, ToolInput]] | None = None,
    diff_tracker: DiffTracker | None = None,
) -> ParsedAgentResponseType | ParsedStreamEventTypes | None:
    """Parse a JSON line from Claude Code SDK.

    Returns a ParsedAgentMessage subtype, ParsedStreamEvent subtype, or None for unknown message types.
    Includes full parsing of tool results, including DiffToolContent.

    Raises
        json.JSONDecodeError: If the line is not valid JSON.
        Other exceptions such as AssertionError
    """
    # First check for stream_event type (from --include-partial-messages)
    data = json.loads(line)
    if isinstance(data, dict) and data.get("type") == "stream_event":
        event = data.get("event", {})
        event_type = event.get("type", "")

        if event_type == "message_start":
            message_id = event.get("message", {}).get("id", "")
            parent_tool_use_id = data.get("parent_tool_use_id")
            return MessageStartEvent(message_id=message_id, parent_tool_use_id=parent_tool_use_id)

        elif event_type == "message_stop":
            return MessageStopEvent()

        elif event_type == "content_block_start":
            content_block = event.get("content_block", {})
            raw_block_type = content_block.get("type", "")
            if raw_block_type == "text":
                return TextBlockStartEvent(
                    index=event.get("index", 0),
                )
            elif raw_block_type == "tool_use":
                return ToolBlockStartEvent(
                    index=event.get("index", 0),
                    tool_id=content_block.get("id"),
                    tool_name=content_block.get("name"),
                )
            # Skip unhandled block types (e.g. "thinking")
            return None

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")
            index = event.get("index", 0)

            if delta_type == "input_json_delta":
                return ToolInputDeltaEvent(
                    index=index,
                    partial_json=delta.get("partial_json", ""),
                )
            elif delta_type == "text_delta":
                return TextDeltaEvent(
                    index=index,
                    text=delta.get("text", ""),
                )
            # Skip unhandled delta types (e.g. "thinking_delta")
            return None

        elif event_type == "content_block_stop":
            return ContentBlockStopEvent(index=event.get("index", 0))

        # skip all other streaming events
        else:
            return None

    # Skip system status messages (e.g. permission mode changes) that _simple
    # doesn't handle. Background-task subtypes must pass this filter — they
    # drive the background-task lifecycle and workflow progress tracking.
    if (
        isinstance(data, dict)
        and data.get("type") == "system"
        and data.get("subtype")
        not in (
            "init",
            "task_started",
            "task_notification",
            "task_progress",
            "task_updated",
        )
    ):
        return None

    # Standard parsing for non-stream events
    message_type_and_results = parse_claude_code_json_lines_simple(line, tool_use_map)
    if message_type_and_results is None:
        return None
    message_type, results_with_simple_tool_calls = message_type_and_results

    if message_type == "user":
        # Skip text-only user messages
        if isinstance(results_with_simple_tool_calls, ParsedUserResponse):
            return None

        return _load_content_for_tool_result_message(
            cast(ParsedToolResultResponseSimple, results_with_simple_tool_calls), diff_tracker
        )
    else:
        return cast(ParsedAgentResponseType, results_with_simple_tool_calls)


def is_session_id_valid(
    session_id: str, environment: AgentExecutionEnvironment, harness: ClaudeCodeHarness, is_session_running: bool
) -> bool:
    """Check if the session id is valid and can be resumed.

    Session ids are valid if they are present in the .claude/projects/-code/ directory.
    And the file contains at least one message that contains the session id.

    This is used to determine if we can resume a session after an interruption.
    """
    claude_session_file_path = _get_claude_session_file_path(environment, harness, session_id)
    logger.debug(
        "Checking session validity: session_id={}, path={}",
        session_id,
        claude_session_file_path,
    )

    # Claude session files are on the HOST filesystem (in ~/.claude/...),
    # not inside the sandbox. We need to access them directly.
    path_exists = claude_session_file_path.exists()
    logger.debug("Checking path {} exists={}", claude_session_file_path, path_exists)
    if not path_exists:
        logger.debug(
            "Session id {} is not valid because the file {} does not exist", session_id, claude_session_file_path
        )
        return False
    file_contents = claude_session_file_path.read_text()
    for line in file_contents.strip().splitlines():
        try:
            maybe_message = json.loads(line)
            if not isinstance(maybe_message, dict):
                continue
            # Only count conversation messages (user/assistant) as evidence of a valid session.
            # queue-operation events are written immediately at process start and don't indicate
            # that the session has any conversation data that can be resumed.
            if (
                maybe_message.get("type") in ("user", "assistant")
                and "sessionId" in maybe_message
                and maybe_message["sessionId"] == session_id
            ):
                return True
        except json.JSONDecodeError:
            if is_session_running:
                logger.debug(
                    "Skipping malformed history line {} - this may happen if the agent is still working", line
                )
            else:
                logger.debug("Found malformed history line {} - this should not happen", line)
                return False
    return False


def _create_tool_content(
    tool_name: str,
    tool_input: ToolInput,
    tool_content: Any,
    diff_tracker: DiffTracker | None,
    is_error: bool = False,
) -> GenericToolContent | DiffToolContent:
    """Create appropriate tool content based on tool type."""
    if tool_name in [AgentToolName.WRITE, AgentToolName.EDIT, AgentToolName.MULTI_EDIT]:
        diff: str | None = None
        if diff_tracker:
            try:
                diff = diff_tracker.compute_diff_for_tool(tool_name, tool_input)
            except Exception as e:
                log_exception(e, "Failed to compute diff for tool, falling back to synthetic diff")

        file_path_str = tool_input.get("file_path", "")
        file_path = diff_tracker.to_git_relative_path(file_path_str) if diff_tracker else file_path_str

        if diff:
            return DiffToolContent(diff=diff, file_path=file_path)

        # DiffTracker unavailable or returned None (e.g. file outside the
        # workspace, like the global Claude memory dir). Synthesize a diff from
        # the tool input so the UI still shows the change. Crucially, this keeps
        # the result a DiffToolContent so it carries ``file_path`` — without it
        # the frontend cannot derive a path for the file chip and silently drops
        # the tool call (see ``chipRowUtils.ts``). This applies to every
        # file-change tool, not just Write.
        #
        # Only do this for a SUCCESSFUL call. On error the file is typically
        # unchanged and the result carries the error text, which must be
        # preserved as generic content rather than replaced by a phantom diff
        # (see test_failed_edit_on_unchanged_file_preserves_error_text).
        if not is_error:
            synthetic_diff = _create_synthetic_diff_from_tool_input(tool_name, file_path, tool_input)
            if synthetic_diff is not None:
                return DiffToolContent(diff=synthetic_diff, file_path=file_path)

    return GenericToolContent(text=str(tool_content))


def _create_synthetic_diff_from_tool_input(tool_name: str, file_path: str, tool_input: ToolInput) -> str | None:
    """Build a best-effort git-format diff from a file-change tool's input.

    Used when the DiffTracker cannot produce a real diff (e.g. the file is
    outside the workspace). Returns None when the input lacks the fields needed
    to synthesize a diff, in which case the caller falls back to generic content.
    """
    if tool_name == AgentToolName.WRITE:
        content = tool_input.get("content")
        if isinstance(content, str) and content:
            return _create_synthetic_write_diff(file_path, content)
        return None

    if tool_name in (AgentToolName.EDIT, AgentToolName.MULTI_EDIT):
        edits = _extract_edits(tool_input)
        if edits:
            return _create_synthetic_edit_diff(file_path, edits)

    return None


def _extract_edits(tool_input: ToolInput) -> list[tuple[str, str]]:
    """Extract (old_string, new_string) pairs from an Edit or MultiEdit input.

    MultiEdit carries a list under ``edits``; Edit carries a single
    ``old_string``/``new_string`` pair at the top level.
    """
    edits = tool_input.get("edits")
    if isinstance(edits, list):
        pairs: list[tuple[str, str]] = []
        for edit in edits:
            if isinstance(edit, dict):
                old_string = edit.get("old_string")
                new_string = edit.get("new_string")
                if isinstance(old_string, str) and isinstance(new_string, str):
                    pairs.append((old_string, new_string))
        return pairs

    old_string = tool_input.get("old_string")
    new_string = tool_input.get("new_string")
    if isinstance(old_string, str) and isinstance(new_string, str):
        return [(old_string, new_string)]

    return []


def _create_synthetic_edit_diff(file_path: str, edits: list[tuple[str, str]]) -> str:
    """Create a synthetic git-format diff for Edit/MultiEdit when DiffTracker is unavailable.

    We don't know the file's real line numbers without its contents, so each
    edit becomes a hunk showing the replaced text as removals and the new text
    as additions. The frontend's ``getLineCounts`` skips the 5-line header and
    counts ``+``/``-`` lines, so the chip's stats stay accurate even though the
    hunk offsets are placeholders. This same string is also rendered in the chip
    diff popover, so the user sees the change anchored at line 1 (the placeholder
    offset) — matching the existing ``_create_synthetic_write_diff`` behavior.
    """
    lines: list[str] = [
        f"diff --git a/{file_path} b/{file_path}",
        "index 0000000..0000000 100644",
        f"--- a/{file_path}",
        f"+++ b/{file_path}",
    ]
    for old_string, new_string in edits:
        old_lines = old_string.split("\n")
        new_lines = new_string.split("\n")
        lines.append(f"@@ -1,{len(old_lines)} +1,{len(new_lines)} @@")
        lines.extend("-" + line for line in old_lines)
        lines.extend("+" + line for line in new_lines)
    return "\n".join(lines) + "\n"


def _create_synthetic_write_diff(file_path: str, content: str) -> str:
    """Create a synthetic git-format diff for a Write tool when DiffTracker is unavailable.

    Produces a 'new file' unified diff showing the full content as additions,
    in the format expected by the frontend's parseDiff (split on 'diff --git').
    """
    lines = content.split("\n")
    line_count = len(lines)
    additions = "\n".join("+" + line for line in lines)
    return (
        f"diff --git a/{file_path} b/{file_path}\n"
        + "new file mode 100644\n"
        + "--- /dev/null\n"
        + f"+++ b/{file_path}\n"
        + f"@@ -0,0 +1,{line_count} @@\n"
        + f"{additions}\n"
    )


def _load_content_for_tool_result_message_no_error_checking(
    simple_tool_result: ParsedToolResultResponseSimple | None,
    diff_tracker: DiffTracker | None,
) -> ParsedToolResultResponse | None:
    """Handle user/tool result message type, including parsing tool content."""

    if simple_tool_result is None:
        return None

    # _handle_tool_result_message only returns one block
    (simple_block,) = simple_tool_result.content_blocks

    assert isinstance(simple_block.content, SimpleToolContent)
    tool_content = _create_tool_content(
        simple_block.tool_name,
        simple_block.content.tool_input,
        simple_block.content.tool_content,
        diff_tracker,
        is_error=simple_block.is_error,
    )

    return ParsedToolResultResponse(
        content_blocks=[
            ToolResultBlock(
                tool_use_id=simple_block.tool_use_id,
                tool_name=simple_block.tool_name,
                invocation_string=simple_block.invocation_string,
                content=tool_content,
                is_error=simple_block.is_error,
                description=simple_block.description,
            )
        ],
        parent_tool_use_id=simple_tool_result.parent_tool_use_id,
        scheduled_wakeup_for=simple_tool_result.scheduled_wakeup_for,
    )


def _load_content_for_tool_result_message(
    simple_tool_result: ParsedToolResultResponseSimple | None,
    diff_tracker: DiffTracker | None,
) -> ParsedToolResultResponse | None:
    """Load content for tool result message, with error checking. If parsing fails, but the JSON is valid, we return None.

    Raises:
        json.JSONDecodeError: If the line is not valid JSON.
    """
    try:
        return _load_content_for_tool_result_message_no_error_checking(simple_tool_result, diff_tracker)
    except Exception as e:
        if isinstance(e, json.JSONDecodeError):
            raise e
        log_exception(e, "Error loading content for tool result message")
        return None


def _get_claude_session_file_path(
    environment: AgentExecutionEnvironment, harness: ClaudeCodeHarness, session_id: str
) -> Path:
    return harness.get_jsonl_path(environment) / f"{session_id}.jsonl"
