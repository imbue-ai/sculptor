import json
import pathlib
import re
import tempfile
from pathlib import Path
from typing import Any
from typing import assert_never
from typing import cast

from loguru import logger

from imbue_core.async_monkey_patches import log_exception
from imbue_core.sculptor.state.chat_state import DiffToolContent
from imbue_core.sculptor.state.chat_state import GenericToolContent
from imbue_core.sculptor.state.chat_state import ImbueCLIToolContent
from imbue_core.sculptor.state.chat_state import SimpleToolContent
from imbue_core.sculptor.state.chat_state import ToolInput
from imbue_core.sculptor.state.chat_state import ToolResultBlock
from imbue_core.sculptor.state.chat_state import ToolUseBlock
from imbue_core.sculptor.state.chat_state import ToolUseID
from imbue_core.sculptor.state.claude_state import ParsedAssistantMessage
from imbue_core.sculptor.state.claude_state import ParsedToolResultMessage
from imbue_core.sculptor.state.claude_state import ParsedToolResultMessageSimple
from imbue_core.sculptor.state.claude_state import ParsedUserMessage
from imbue_core.sculptor.state.claude_state import is_tool_name_in_servers
from imbue_core.sculptor.state.claude_state import parse_claude_code_json_lines_simple
from imbue_core.sculptor.state.mcp_constants import IMBUE_CLI_INTERNAL_MCP_SERVER_NAME
from imbue_core.sculptor.state.mcp_constants import IMBUE_CLI_USER_MCP_SERVER_NAME
from sculptor.agents.claude_code_sdk.diff_tracker import DiffTracker
from sculptor.interfaces.agents.v1.agent import MCPServerInfo
from sculptor.interfaces.agents.v1.agent import MCPServerType
from sculptor.interfaces.agents.v1.agent import ParsedAgentMessageType
from sculptor.interfaces.environments.v1.base import Environment
from sculptor.services.anthropic_credentials_service.api import AnthropicApiKey
from sculptor.services.anthropic_credentials_service.api import AnthropicCredentials
from sculptor.services.anthropic_credentials_service.api import ClaudeOauthCredentials

# Number of characters from the end of API key to store for approval tracking
API_KEY_SUFFIX_LENGTH = 20


def claude_mcp_servers_config(workspace_path: pathlib.Path) -> dict[str, Any]:
    return {
        name: {
            "command": "imbue-cli.sh",
            "args": [
                "--log-to-file=/tmp/imbue-cli.log",
                "mcp",
                *("--project-path", str(workspace_path)),
                *config_args,
                *("--transport", "stdio"),
            ],
            "env": {},
        }
        for name, config_args in (
            (IMBUE_CLI_INTERNAL_MCP_SERVER_NAME, ["--use-internal-config"]),
            (IMBUE_CLI_USER_MCP_SERVER_NAME, ["--config", str(workspace_path / "tools.toml")]),
        )
    }


def claude_project_config(workspace_path: pathlib.Path) -> dict[str, Any]:
    # TODO: do we need all of these settings? last session id seems to be randomly copy pasted from someone's .claude.json
    return {
        "allowedTools": [],
        "history": [],
        "dontCrawlDirectory": False,
        "mcpContextUris": [],
        "mcpServers": claude_mcp_servers_config(workspace_path),
        "enabledMcpjsonServers": [],
        "disabledMcpjsonServers": [],
        "hasTrustDialogAccepted": True,
        "ignorePatterns": [],
        "projectOnboardingSeenCount": 1,
        "hasClaudeMdExternalIncludesApproved": False,
        "hasClaudeMdExternalIncludesWarningShown": False,
        "lastCost": 0,
        "lastAPIDuration": 0,
        "lastDuration": 3172,
        "lastLinesAdded": 0,
        "lastLinesRemoved": 0,
        "lastTotalInputTokens": 0,
        "lastTotalOutputTokens": 0,
        "lastTotalCacheCreationInputTokens": 0,
        "lastTotalCacheReadInputTokens": 0,
        "lastSessionId": "ef949ec0-4a45-4665-81a7-f9e1ec21a41c",
        "bypassPermissionsModeAccepted": True,
    }


def claude_config_template(environment: Environment) -> dict[str, Any]:
    return {
        "numStartups": 3,
        "theme": "light",
        "customApiKeyResponses": {
            "approved": [],
            "rejected": [],
        },
        "firstStartTime": "2025-06-10T21:50:05.520Z",
        "projects": {
            str(environment.to_host_path(environment.get_workspace_path())): claude_project_config(
                environment.to_host_path(environment.get_workspace_path())
            )
        },
        "isQualifiedForDataSharing": False,
        "hasCompletedOnboarding": True,
        "lastOnboardingVersion": "1.0.17",
        "recommendedSubscription": "",
        "subscriptionNoticeCount": 0,
        "hasAvailableSubscription": False,
    }


def populate_claude_settings(environment: Environment, anthropic_credentials: AnthropicCredentials) -> None:
    """Claude Code requires certain settings to run correctly.

    We default to using the user's settings (with some specific changes).
    However, if the user does NOT have claude code installed, we can provide
    them with our own settings.
    """
    logger.info("Populating claude settings")
    claude_config_path = Path.home() / ".claude.json"

    if claude_config_path.exists():
        logger.info("Found existing claude config path at {}", claude_config_path)
        claude_config = json.load(open(claude_config_path, "r"))

        # Make required modifications
        claude_config["projects"][str(environment.to_host_path(environment.get_workspace_path()))] = (
            claude_project_config(environment.to_host_path(environment.get_workspace_path()))
        )
    else:
        logger.info("Generating new claude config")
        claude_config = claude_config_template(environment)
    # A previous version of this code set the primaryApiKey,
    # but we have since moved to injecting environment variables.
    # Remove it in case the container has an old config
    # and there's a conflict between the two approaches.
    claude_config.pop("primaryApiKey", None)
    credentials_file_path = environment.get_root_path() / ".claude" / ".credentials.json"
    match anthropic_credentials:
        case AnthropicApiKey(anthropic_api_key=anthropic_api_key):
            # this is required for claude to work with the anthropic api key without prompting the user (primarily required for compaction and terminal)
            claude_config["customApiKeyResponses"] = {
                "approved": [anthropic_api_key.unwrap()[-API_KEY_SUFFIX_LENGTH:]],
                "rejected": [],
            }
            logger.trace("Writing anthropic api key to {}", credentials_file_path)
            # TODO: This works but it's safer to remove the file completely.
            environment.write_file(str(credentials_file_path), "")
            logger.trace("Wrote anthropic api key to {}", credentials_file_path)
        case ClaudeOauthCredentials():
            claude_config["customApiKeyResponses"] = {
                "approved": [],
                "rejected": [],
            }
            logger.trace("Writing claude oauth credentials to {}", credentials_file_path)
            environment.write_file(
                str(credentials_file_path), anthropic_credentials.convert_to_claude_code_credentials_json()
            )
            logger.trace("Wrote claude oauth credentials to {}", credentials_file_path)
        case _ as unreachable:
            assert_never(unreachable)
    claude_config["hasCompletedOnboarding"] = True

    with tempfile.NamedTemporaryFile() as tmp_file:
        tmp_file.write(json.dumps(claude_config).encode())
        tmp_file.flush()
        logger.trace("Copying claude config to environment at {}", environment.get_root_path() / ".claude.json")
        environment.copy_from_local(Path(tmp_file.name), str(environment.get_root_path() / ".claude.json"))

    logger.info("Populated claude settings")


def _create_tool_content(
    tool_name: str,
    tool_input: ToolInput,
    tool_content: Any,
    diff_tracker: DiffTracker | None,
) -> GenericToolContent | DiffToolContent:
    """Create appropriate tool content based on tool type."""
    if tool_name in ["Write", "Edit", "MultiEdit"] and diff_tracker:
        diff = diff_tracker.compute_diff_for_tool(tool_name, tool_input)
        if diff:
            file_path = tool_input.get("file_path", "")
            return DiffToolContent(diff=diff, file_path=file_path)

    return GenericToolContent(text=str(tool_content))


def _load_content_for_tool_result_message_no_error_checking(
    simple_tool_result: ParsedToolResultMessageSimple | None,
    diff_tracker: DiffTracker | None,
) -> ParsedToolResultMessage | None:
    """Handle user/tool result message type, including parsing tool content."""

    if simple_tool_result is None:
        return None

    # _handle_tool_result_message only returns one block
    (simple_block,) = simple_tool_result.content_blocks

    if is_tool_name_in_servers(simple_block.tool_name):
        tool_content_ = simple_block.content
        assert isinstance(tool_content_, ImbueCLIToolContent)
        tool_content = tool_content_  # for the type checker
    else:
        assert isinstance(simple_block.content, SimpleToolContent)
        tool_content = _create_tool_content(
            simple_block.tool_name, simple_block.content.tool_input, simple_block.content.tool_content, diff_tracker
        )

    return ParsedToolResultMessage(
        content_blocks=[
            ToolResultBlock(
                tool_use_id=simple_block.tool_use_id,
                tool_name=simple_block.tool_name,
                invocation_string=simple_block.invocation_string,
                content=tool_content,
                is_error=simple_block.is_error,
            )
        ]
    )


def _load_content_for_tool_result_message(
    simple_tool_result: ParsedToolResultMessageSimple | None,
    diff_tracker: DiffTracker | None,
) -> ParsedToolResultMessage | None:
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


def parse_claude_code_json_lines(
    line: str,
    tool_use_map: dict[str, tuple[str, ToolInput]] | None = None,
    diff_tracker: DiffTracker | None = None,
) -> ParsedAgentMessageType | None:
    """Parse a JSON line from Claude Code SDK.

    Returns a ParsedAgentMessage subtype or None for unknown message types.
    Includes full parsing of tool results, including DiffToolContent.

    Raises
        json.JSONDecodeError: If the line is not valid JSON.
        Other exceptions such as AssertionError
    """
    message_type_and_results = parse_claude_code_json_lines_simple(line, tool_use_map)
    if message_type_and_results is None:
        return None
    message_type, results_with_simple_tool_calls = message_type_and_results

    if message_type == "user":
        # Skip text-only user messages
        if isinstance(results_with_simple_tool_calls, ParsedUserMessage):
            return None

        return _load_content_for_tool_result_message(
            cast(ParsedToolResultMessageSimple, results_with_simple_tool_calls), diff_tracker
        )
    else:
        return cast(ParsedAgentMessageType, results_with_simple_tool_calls)


def get_claude_session_directory(environment: Environment) -> Path:
    assert environment.get_workspace_path() == Path("/code")
    return environment.get_root_path() / ".claude" / "projects" / "-code"


def get_claude_session_file_path_no_check(root_path: Path, session_id: str) -> Path:
    return root_path / ".claude" / "projects" / "-code" / f"{session_id}.jsonl"


def get_claude_session_file_path(environment: Environment, session_id: str) -> Path:
    # TODO: ideally we shouldn't hardcode "-code" but i'm not too sure how claude code generates
    # these folders from the paths (the original path is in get_workspace_path and is /code in the docker case)
    # in this case, we can at least fail loudly if the workspace path is not what we expect
    assert environment.get_workspace_path() == Path("/code")
    return get_claude_session_file_path_no_check(environment.get_root_path(), session_id)


def cancel_pending_tool_calls(environment: Environment, session_id: str) -> None:
    """This function is expected to be called any time we interrupt the claude
    code process, and will manually mark our tool calls as cancelled.

    This is necessary due to a bug in Claude code:
      https://github.com/anthropics/claude-code/issues/473

    DO NOT CALL THIS while Claude Code is processing, or a demon will fly out of
    your nose.
    """
    claude_session_file_path = get_claude_session_file_path(environment, session_id)
    if not environment.exists(str(claude_session_file_path)):
        logger.info(
            "Session id {} is not valid because the file {} does not exist", session_id, claude_session_file_path
        )
        return

    file_contents = environment.read_file(str(claude_session_file_path))
    assert isinstance(file_contents, str)

    cancelled_tool_calls = isolate_cancelled_tool_calls(file_contents)

    if cancelled_tool_calls:
        logger.info("Uncompleted Tool Calls detected: {}. Surgically removing these lines.", cancelled_tool_calls)

        cancelled_tool_re = re.compile("|".join(cancelled_tool_calls))

        filtered_lines = []
        for line in file_contents.strip().split("\n"):
            if not cancelled_tool_re.search(line):
                filtered_lines.append(line + "\n")

        # update the parent uuid for each line so that the messages are contiguous
        completed_lines = []
        parent_uuid = None
        for line in filtered_lines:
            data = json.loads(line)
            if not isinstance(data, dict):
                completed_lines.append(line)
                continue
            if "uuid" not in data:
                # this may occur for lines such as "InvalidAPIKey"
                completed_lines.append(line)
                continue
            data["parentUuid"] = parent_uuid
            parent_uuid = data["uuid"]
            completed_lines.append(json.dumps(data))

        patched_content = "\n".join(completed_lines) + "\n"

        environment.write_file(
            str(claude_session_file_path),
            patched_content,
        )


def isolate_cancelled_tool_calls(file_contents: str) -> set[ToolUseID]:
    """Search the given file contents for any tool calls that have not been completed."""
    lines = file_contents.split("\n")
    messages: list[ParsedAgentMessageType | None] = []
    for line in lines:
        if not line:
            continue
        try:
            messages.append(parse_claude_code_json_lines(line))
        except json.JSONDecodeError:
            logger.info("Skipping malformed history line {!r}", line)
        except Exception as e:
            logger.info("Could not successfully parse user line: {!r}, {}", line, e)

    # Use two sets to calculate set difference, to make us robust to processing tools out of order.
    started_tool_use_ids: set[ToolUseID] = set()
    completed_tool_use_ids: set[ToolUseID] = set()

    for message in filter(lambda message: message and message.type in ("assistant", "tool_result"), messages):
        # for the type checker (guaranteed by the filter)
        assert isinstance(message, ParsedAssistantMessage) or isinstance(message, ParsedToolResultMessage)
        for content in message.content_blocks:
            if content.type == "tool_use" and message.type == "assistant":
                assert isinstance(content, ToolUseBlock)  # for the type checker
                started_tool_use_ids.add(content.id)

            if content.type == "tool_result" and message.type == "tool_result":
                assert isinstance(content, ToolResultBlock)  # for the type checker
                completed_tool_use_ids.add(content.tool_use_id)

    logger.info("Started {} tool use ids: {}", len(started_tool_use_ids), started_tool_use_ids)
    logger.info("Completed {} tool use ids: {}", len(completed_tool_use_ids), completed_tool_use_ids)

    return started_tool_use_ids - completed_tool_use_ids


def parse_mcp_tools_by_server(tools: list[str], mcp_servers: dict[str, str]) -> dict[str, MCPServerInfo]:
    """Parse MCP tools and group them by server.

    MCP tools follow the pattern: mcp__<server_name>__<tool_name>
    """
    server_tools: dict[str, list[str]] = {name: [] for name in mcp_servers.keys()}

    # Group tools by server
    for tool in tools:
        if tool.startswith("mcp__"):
            # Extract server name from tool
            parts = tool.split("__", 2)
            if len(parts) >= 3:
                server_name = parts[1]
                tool_name = parts[2]

                if server_name in server_tools:
                    server_tools[server_name].append(tool_name)
                else:
                    # This shouldn't happen if mcp_servers is complete, but log it
                    logger.warning("Found MCP tool '{}' for unknown server '{}'", tool, server_name)

    # Determine server types based on known imbue-cli server names
    imbue_cli_servers = {IMBUE_CLI_INTERNAL_MCP_SERVER_NAME, IMBUE_CLI_USER_MCP_SERVER_NAME}

    # Create MCPServerInfo objects
    result = {}
    for name, status in mcp_servers.items():
        server_type = MCPServerType.IMBUE_CLI if name in imbue_cli_servers else MCPServerType.EXTERNAL
        result[name] = MCPServerInfo(status=status, server_type=server_type, tools=server_tools.get(name, []))

    return result


def is_session_id_valid(session_id: str, environment: Environment, is_session_running: bool) -> bool:
    """Check if the session id is valid and can be resumed.

    Session ids are valid if they are present in the .claude/projects/-code/ directory.
    And the file contains at least one message that contains the session id.

    This is used to determine if we can resume a session after an interruption.
    """
    claude_session_file_path = get_claude_session_file_path(environment, session_id)
    if not environment.exists(str(claude_session_file_path)):
        logger.info(
            "Session id {} is not valid because the file {} does not exist", session_id, claude_session_file_path
        )
        return False
    file_contents = environment.read_file(str(claude_session_file_path))
    for line in file_contents.strip().splitlines():
        try:
            maybe_message = json.loads(line)
            if (
                isinstance(maybe_message, dict)
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
