import json
import re
from abc import ABC
from typing import Any
from typing import Sequence
from typing import cast

from loguru import logger
from pydantic import Field

from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.interfaces.agents.tool_names import AgentToolName
from sculptor.primitives.ids import AssistantMessageID
from sculptor.state.chat_state import ContentBlockTypes
from sculptor.state.chat_state import FileBlock
from sculptor.state.chat_state import SimpleToolContent
from sculptor.state.chat_state import TextBlock
from sculptor.state.chat_state import ToolInput
from sculptor.state.chat_state import ToolResultBlock
from sculptor.state.chat_state import ToolResultBlockSimple
from sculptor.state.chat_state import ToolUseBlock

_RE_STRIP_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*[mGKHfABCDhls]|\x1b\[[?][0-9;]*[hlHLdcE]|\x1b[=>]")

_RE_IMG_TAG = re.compile(r'<img\s[^>]*src=["\']([^"\']+)["\'][^>]*/?>(?:\s*</img>)?', re.IGNORECASE | re.DOTALL)
_RE_VIDEO_TAG = re.compile(
    r'<video\s[^>]*src=["\']([^"\']+)["\'][^>]*/?>(?:\s*</video>)?',
    re.IGNORECASE | re.DOTALL,
)

_SUPPORTED_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"})
_SUPPORTED_VIDEO_EXTENSIONS = frozenset({".mp4", ".webm", ".mov"})
_SUPPORTED_MEDIA_EXTENSIONS = _SUPPORTED_IMAGE_EXTENSIONS | _SUPPORTED_VIDEO_EXTENSIONS


def _has_supported_media_extension(path: str) -> bool:
    """Check whether a file path has a supported image or video extension."""
    lower_path = path.lower()
    return any(lower_path.endswith(ext) for ext in _SUPPORTED_MEDIA_EXTENSIONS)


def extract_media_tags_from_text(text: str) -> tuple[str, list[str]]:
    """Extract HTML <img> and <video> tags with local file paths from text.

    Returns cleaned text (tags removed) and a list of absolute file paths.
    Only extracts src paths that are absolute local paths (starting with /)
    with supported media file extensions (png, jpg, gif, webp, svg, mp4, webm, mov).
    HTTP and data: URLs are left untouched in the text.
    Non-media file paths (e.g. .html) are left untouched in the text.
    """
    img_matches = list(_RE_IMG_TAG.finditer(text))
    video_matches = list(_RE_VIDEO_TAG.finditer(text))

    local_matches = [
        m
        for m in img_matches + video_matches
        if m.group(1).startswith("/") and _has_supported_media_extension(m.group(1))
    ]

    file_paths = [m.group(1) for m in local_matches]

    # Remove matched tags from text in reverse order to preserve offsets
    cleaned_text = text
    for match in reversed(local_matches):
        cleaned_text = cleaned_text[: match.start()] + cleaned_text[match.end() :]

    return cleaned_text.strip(), file_paths


def split_text_and_media(text: str) -> list[TextBlock | FileBlock]:
    """Split text into interleaved TextBlock and FileBlock segments.

    Unlike ``extract_media_tags_from_text`` which strips all media tags and
    returns them separately, this function preserves the order so that each
    image/video appears right after the text that precedes it.

    Returns a list of TextBlock and FileBlock instances.  Empty text segments
    (whitespace-only) between consecutive media tags are omitted.
    """
    img_matches = list(_RE_IMG_TAG.finditer(text))
    video_matches = list(_RE_VIDEO_TAG.finditer(text))

    local_matches = sorted(
        [
            m
            for m in img_matches + video_matches
            if m.group(1).startswith("/") and _has_supported_media_extension(m.group(1))
        ],
        key=lambda m: m.start(),
    )

    if not local_matches:
        return [TextBlock(text=text)]

    result: list[TextBlock | FileBlock] = []
    prev_end = 0

    for match in local_matches:
        preceding_text = text[prev_end : match.start()].strip()
        if preceding_text:
            result.append(TextBlock(text=preceding_text))
        result.append(FileBlock(source=match.group(1)))
        prev_end = match.end()

    trailing_text = text[prev_end:].strip()
    if trailing_text:
        result.append(TextBlock(text=trailing_text))

    return result


class ParsedStreamEvent(SerializableModel, ABC):
    pass


class MessageStartEvent(ParsedStreamEvent):
    """Emitted when a new assistant message begins streaming."""

    event_type: str = "message_start"
    message_id: str
    parent_tool_use_id: str | None = None


class MessageStopEvent(ParsedStreamEvent):
    """Emitted when the assistant message is complete."""

    event_type: str = "message_stop"


class ContentBlockStartEvent(ParsedStreamEvent):
    """Emitted when a new content block (text or tool_use) begins."""

    event_type: str = "content_block_start"
    block_type: str
    index: int


class ToolBlockStartEvent(ContentBlockStartEvent):
    block_type: str = "tool_start"
    tool_id: str
    tool_name: str


class TextBlockStartEvent(ContentBlockStartEvent):
    block_type: str = "text_start"


class ContentBlockDeltaEvent(ParsedStreamEvent, ABC):
    """Base class for incremental content updates within a block."""

    event_type: str = "content_block_delta"
    index: int


class TextDeltaEvent(ContentBlockDeltaEvent):
    """Emitted for incremental text content updates."""

    delta_type: str = "text_delta"
    text: str


class ToolInputDeltaEvent(ContentBlockDeltaEvent):
    """Emitted for incremental tool input JSON updates."""

    delta_type: str = "input_json_delta"
    partial_json: str


class ContentBlockStopEvent(ParsedStreamEvent):
    """Emitted when a content block is complete."""

    event_type: str = "content_block_stop"
    index: int


ParsedStreamEventTypes = (
    MessageStartEvent
    | MessageStopEvent
    | ContentBlockStartEvent
    | ToolBlockStartEvent
    | TextBlockStartEvent
    | TextDeltaEvent
    | ToolInputDeltaEvent
    | ContentBlockStopEvent
)


class ParsedAgentResponse(SerializableModel):
    """Base class for parsed agent messages with type discriminator"""

    object_type: str = Field(description="Type discriminator for parsed messages")


class ParsedInitResponse(ParsedAgentResponse):
    object_type: str = Field(default="ParsedInitResponse")
    session_id: str = Field(description="Session ID from claude code init")
    mcp_servers: dict[str, str] = Field(description="Map from enabled MCP servers to their statuses")
    tools: list[str] = Field(default_factory=list, description="List of all available tools")


class ParsedAssistantResponse(ParsedAgentResponse):
    object_type: str = Field(default="ParsedAssistantResponse")
    message_id: AssistantMessageID = Field(description="Unique identifier for assistant message")
    content_blocks: list[ContentBlockTypes] = Field(description="Content blocks containing assistant response data")
    parent_tool_use_id: str | None = Field(
        default=None, description="Tool use ID of the parent Task call if this is a subagent message"
    )


class ParsedUserResponse(ParsedAgentResponse):
    object_type: str = Field(default="ParsedUserResponse")
    content_blocks: list[ContentBlockTypes] = Field(
        description="Content blocks containing user response data",
    )


class ParsedToolResultResponseSimple(ParsedAgentResponse):
    object_type: str = Field(default="ParsedToolResultResponse")
    content_blocks: Sequence[ToolResultBlockSimple] = Field(
        description="Tool result content blocks that may contain user data"
    )
    parent_tool_use_id: str | None = Field(
        default=None, description="Tool use ID of the parent Task call if this is a subagent message"
    )
    # Unix timestamp (ms) from ScheduleWakeup's tool_use_result.scheduledFor.
    # Non-None means Claude Code has accepted a wakeup and will fire a second
    # turn after the delay.
    scheduled_wakeup_for: int | None = Field(default=None)


ParsedUserResponseTypeSimple = ParsedUserResponse | ParsedToolResultResponseSimple


class ParsedToolResultResponse(ParsedAgentResponse):
    object_type: str = Field(default="ParsedToolResultResponse")
    content_blocks: Sequence[ToolResultBlock] = Field(
        description="Tool result content blocks that may contain user data"
    )
    parent_tool_use_id: str | None = Field(
        default=None, description="Tool use ID of the parent Task call if this is a subagent message"
    )
    # Unix timestamp (ms) from ScheduleWakeup's tool_use_result.scheduledFor.
    scheduled_wakeup_for: int | None = Field(default=None)


class ParsedEndResponse(ParsedAgentResponse):
    object_type: str = Field(default="ParsedEndResponse")
    is_error: bool = Field(default=False, description="Whether the stream ended due to an error")
    result: str = Field(description="The result of the stream")
    status: str | None = Field(default=None, description="Optional status field for result")
    duration_ms: float | None = Field(default=None, description="Wallclock duration of agent process")
    duration_api_ms: float | None = Field(
        default=None, description="Model compute duration of agent process if provided"
    )
    num_turns: int | None = Field(default=None, description="Number of turns in this agent session")
    # Session ID can be the claude_code session ID which potentially exposes user messages
    session_id: str | None = Field(default=None, description="Agent call session ID")
    total_tokens: int | None = Field(default=None, description="Total number of tokens")
    input_tokens: int | None = Field(default=None, description="Input tokens")
    output_tokens: int | None = Field(default=None, description="Output tokens")
    total_cost_usd: float | None = Field(default=None, description="Total cost of agent session")
    api_error_status: int | None = Field(
        default=None,
        description="HTTP status of the API error that ended the turn (e.g. 429/500/529), or None if the turn did not fail on an API error",
    )


class ParsedCompactionSummaryResponse(ParsedAgentResponse):
    object_type: str = Field(default="ParsedCompactionSummaryResponse")
    content: TextBlock = Field(
        description="Content blocks containing user response data",
    )


class ParsedTaskStartedResponse(ParsedAgentResponse):
    """Emitted by Claude Code when a background task (run_in_background) is launched."""

    object_type: str = Field(default="ParsedTaskStartedResponse")
    task_id: str = Field(description="Background task ID assigned by Claude Code")
    tool_use_id: str = Field(
        description="Tool use ID of the tool call that launched the background task. Empty when the CLI omits it (parity with ParsedTaskNotificationResponse — see SCU-1666).",
    )
    description: str = Field(default="", description="Human-readable description of the background task")
    task_type: str = Field(default="", description="Type of background task (e.g. local_bash)")


class ParsedTaskNotificationResponse(ParsedAgentResponse):
    """Emitted by Claude Code when a background task completes."""

    object_type: str = Field(default="ParsedTaskNotificationResponse")
    task_id: str = Field(description="Background task ID matching the task_started event")
    tool_use_id: str = Field(
        description="Tool use ID of the tool call that launched the background task. Empty when the CLI omits it, e.g. a task orphaned by a process exit and reported as failed on resume (see SCU-1666).",
    )
    status: str = Field(description="Completion status (e.g. completed)")
    summary: str = Field(default="", description="Human-readable summary of the background task result")
    duration_ms: int | None = Field(
        default=None, description="Background task run time in milliseconds (from CLI usage.duration_ms)"
    )


class ParsedTaskUpdatedResponse(ParsedAgentResponse):
    """Emitted by Claude Code when a background task's state changes.

    The CLI emits task_updated with patch.status="completed" when a background
    task finishes, even when task_notification is not emitted (e.g. when the
    task completes while the CLI is busy executing another tool call).
    """

    object_type: str = Field(default="ParsedTaskUpdatedResponse")
    task_id: str = Field(description="Background task ID matching the task_started event")
    status: str = Field(
        default="", description="Status from patch (e.g. completed, failed, stopped). Empty if patch has no status."
    )


# Response types that pass through the parse pipeline unchanged (they have no
# simple/rich variants). Both ParsedAgentResponseTypeSimple and the downstream
# ParsedAgentResponseType in sculptor.interfaces.agents.agent are built from
# this union, so adding a pass-through type here lands it in both.
ParsedAgentResponsePassthrough = (
    ParsedInitResponse
    | ParsedAssistantResponse
    | ParsedEndResponse
    | ParsedCompactionSummaryResponse
    | ParsedTaskStartedResponse
    | ParsedTaskNotificationResponse
    | ParsedTaskUpdatedResponse
)


# the tool results are not parsed in this kind of message
ParsedAgentResponseTypeSimple = ParsedAgentResponsePassthrough | ParsedUserResponseTypeSimple


def get_tool_invocation_string(tool_name: str, tool_input: ToolInput, _tool_result: str | None = None) -> str:
    """Generate a human-readable invocation string for a tool."""
    if tool_name == AgentToolName.READ:
        result = tool_input.get("file_path", "")
    elif tool_name in [AgentToolName.WRITE, AgentToolName.EDIT, AgentToolName.MULTI_EDIT]:
        result = tool_input.get("file_path", "")
    elif tool_name == AgentToolName.BASH:
        result = tool_input.get("command", "")
    elif tool_name in [AgentToolName.GREP, AgentToolName.GLOB]:
        pattern = tool_input.get("pattern", "")
        path = tool_input.get("path", "")
        result = f'"{pattern}"' + (f" in {path}" if path else "")
    elif tool_name == AgentToolName.LS:
        result = tool_input.get("path", "")
    elif tool_name == AgentToolName.NOTEBOOK_READ:
        result = tool_input.get("notebook_path", "")
    elif tool_name == AgentToolName.NOTEBOOK_EDIT:
        result = tool_input.get("notebook_path", "")
    elif tool_name == AgentToolName.WEB_FETCH:
        result = tool_input.get("url", "")
    elif tool_name == AgentToolName.WEB_SEARCH:
        result = tool_input.get("query", "")
    elif tool_name == AgentToolName.TASK:
        result = tool_input.get("description", "")
    elif tool_name == AgentToolName.SKILL:
        result = tool_input.get("skill", "")
    else:
        # For unknown tools, try to extract the most relevant field
        if "path" in tool_input:
            result = tool_input["path"]
        elif "file_path" in tool_input:
            result = tool_input["file_path"]
        elif "command" in tool_input:
            result = tool_input["command"]
        else:
            # Return first non-empty string value
            result = "tool invocation"
            for value in tool_input.values():
                if isinstance(value, str) and value:
                    result = value
                    break
    return cast(str, result)  # for the type checker


def _handle_init_message(data: dict[str, Any]) -> ParsedInitResponse:
    """Handle system/init message type."""
    mcp_servers = data.get("mcp_servers", [])
    tools = data.get("tools", [])

    if mcp_servers:
        logger.debug("MCP servers found in init message: {}", mcp_servers)

    return ParsedInitResponse(
        session_id=data["session_id"],
        mcp_servers={server["name"]: server["status"] for server in mcp_servers},
        tools=tools,
    )


def _handle_task_started_message(data: dict[str, Any]) -> ParsedTaskStartedResponse:
    """Handle system/task_started message type."""
    # ``tool_use_id`` is read defensively (see _handle_task_notification_message)
    # to keep a variant payload from crashing the whole agent.
    return ParsedTaskStartedResponse(
        task_id=data["task_id"],
        tool_use_id=data.get("tool_use_id", ""),
        description=data.get("description", ""),
        task_type=data.get("task_type", ""),
    )


def _handle_task_notification_message(data: dict[str, Any]) -> ParsedTaskNotificationResponse:
    """Handle system/task_notification message type."""
    # ``usage`` is a nested dict in the raw payload — see SCU-1151. duration_ms
    # is the only field we care about right now; tool_uses/total_tokens stay
    # unparsed until a caller asks for them.
    usage = data.get("usage") or {}
    raw_duration_ms = usage.get("duration_ms") if isinstance(usage, dict) else None
    # ``tool_use_id`` is absent when a background task orphaned by a process exit
    # is reported as failed on resume: the launching tool call's id died with the
    # previous process (see SCU-1666). Default to "" rather than indexing so the
    # notification is surfaced instead of a missing key killing the agent.
    return ParsedTaskNotificationResponse(
        task_id=data["task_id"],
        tool_use_id=data.get("tool_use_id", ""),
        status=data.get("status", ""),
        summary=data.get("summary", ""),
        duration_ms=int(raw_duration_ms) if isinstance(raw_duration_ms, (int, float)) else None,
    )


def _handle_task_updated_message(data: dict[str, Any]) -> ParsedTaskUpdatedResponse:
    """Handle system/task_updated message type.

    The CLI emits task_updated when a background task's state changes (e.g.
    completed, failed, stopped). The status is in data["patch"]["status"].
    """
    patch = data.get("patch", {})
    return ParsedTaskUpdatedResponse(
        task_id=data["task_id"],
        status=patch.get("status", ""),
    )


def _handle_assistant_message(data: dict[str, Any]) -> ParsedAssistantResponse:
    """Handle assistant message type."""
    message_data = data["message"]
    message_id = message_data["id"]

    # ``content`` is normally a list of block dicts, but the CLI can emit a bare
    # string instead. Wrap it as a single text block so we don't iterate over its
    # characters and crash on ``content["type"]``.
    raw_content = message_data["content"]
    if isinstance(raw_content, str):
        raw_content = [{"type": "text", "text": raw_content}]

    content_blocks: list[ContentBlockTypes] = []
    for content in raw_content:
        # Only dict blocks carry a ``type`` we can dispatch on; tolerate stray
        # non-dict items (e.g. a bare string mixed into the list) by skipping them.
        if not isinstance(content, dict):
            continue
        if content["type"] == "text":
            cleaned_text, img_file_paths = extract_media_tags_from_text(content["text"])
            if cleaned_text:
                content_blocks.append(TextBlock(text=cleaned_text))
            for img_path in img_file_paths:
                content_blocks.append(FileBlock(source=img_path))
        elif content["type"] == "tool_use":
            content_blocks.append(ToolUseBlock(id=content["id"], name=content["name"], input=content["input"]))

    return ParsedAssistantResponse(
        message_id=message_id,
        content_blocks=content_blocks,
        parent_tool_use_id=data.get("parent_tool_use_id"),
    )


def _handle_tool_result_message(
    data: dict[str, Any],
    tool_use_map: dict[str, tuple[str, ToolInput]] | None,
) -> ParsedUserResponseTypeSimple | None:
    """Handle user/tool result message type without parsing tool content."""

    message_content = data["message"]["content"]

    if isinstance(message_content, str):
        return ParsedUserResponse(content_blocks=[TextBlock(text=message_content)])

    # An empty content list has no block to inspect; skip it rather than indexing
    # ``[0]`` (the CLI has been seen to emit user messages with empty content).
    if len(message_content) == 0:
        return None

    if message_content[0]["type"] == "text":
        if len(message_content) > 1:
            logger.warning("Message content has more than one block: {}", message_content)
        return ParsedUserResponse(content_blocks=[TextBlock(text=message_content[0]["text"])])
    elif message_content[0]["type"] == "document":
        if len(message_content) > 1:
            logger.warning("Message content has more than one block: {}", message_content)
        media_type = message_content[0].get("source", {}).get("media_type", "UNSPECIFIED")
        return ParsedUserResponse(content_blocks=[TextBlock(text=f"Document, media_type: {media_type}")])

    tool_result = message_content[0]
    tool_use_id = tool_result["tool_use_id"]

    # Get tool info from map
    tool_name, tool_input = (
        tool_use_map.get(tool_use_id, ("unknown", ToolInput())) if tool_use_map else ("unknown", ToolInput())
    )

    # ``content`` is optional on tool_result blocks in the Anthropic format;
    # tolerate its absence (defaulting to empty) instead of raising KeyError.
    tool_result_content = tool_result.get("content", "")
    invocation_string = get_tool_invocation_string(tool_name, tool_input, tool_result_content)
    tool_content = SimpleToolContent(
        text=str(tool_result_content), tool_input=tool_input, tool_content=tool_result_content
    )

    # Extract ScheduleWakeup metadata from the top-level tool_use_result field.
    # Claude Code sets this when ScheduleWakeup is accepted:
    #   {"tool_use_result": {"scheduledFor": <unix_ms>, ...}}
    tool_use_result = data.get("tool_use_result")
    scheduled_wakeup_for = tool_use_result.get("scheduledFor") if isinstance(tool_use_result, dict) else None

    description = tool_input.get("description") if tool_input else None

    return ParsedToolResultResponseSimple(
        content_blocks=[
            ToolResultBlockSimple(
                tool_use_id=tool_use_id,
                tool_name=tool_name,
                invocation_string=invocation_string,
                content=tool_content,
                is_error=tool_result.get("is_error", False),
                description=description,
            )
        ],
        parent_tool_use_id=data.get("parent_tool_use_id"),
        scheduled_wakeup_for=scheduled_wakeup_for,
    )


def _handle_stream_end_message(data: dict[str, Any]) -> ParsedEndResponse:
    """Handle result/stream end message type."""
    return ParsedEndResponse(
        is_error=data.get("is_error", False),
        result=data.get("result", ""),
        status=data.get("subtype", ""),
        duration_ms=data.get("duration_ms", 0),
        duration_api_ms=data.get("duration_api_ms", 0),
        num_turns=data.get("num_turns", 0),
        session_id=data.get("session_id", ""),
        total_tokens=(data.get("usage", {}).get("input_tokens", 0) + data.get("usage", {}).get("output_tokens", 0))
        + data.get("usage", {}).get("cache_creation_input_tokens", 0)
        + data.get("usage", {}).get("cache_read_input_tokens", 0),
        input_tokens=data.get("usage", {}).get("input_tokens", 0),
        output_tokens=data.get("usage", {}).get("output_tokens", 0),
        total_cost_usd=data.get("total_cost_usd", 0),
        # Present only when the turn failed on an API error; the CLI omits it otherwise.
        api_error_status=data.get("api_error_status"),
    )


def parse_claude_code_json_lines_simple(
    line: str,
    tool_use_map: dict[str, tuple[str, ToolInput]] | None = None,
) -> tuple[str, ParsedAgentResponseTypeSimple | None] | None:
    """Parse a JSON line from Claude Code SDK.

    Returns a ``(message_type, parsed_response)`` tuple, or None for blank lines
    and unknown message types. For tool results this only ever produces
    SimpleToolContent, never the rich DiffToolContent, since DiffToolContent
    requires the diff tracker to be passed in.
    """
    line = _RE_STRIP_ANSI_ESCAPE.sub("", line).strip()

    if line == "":
        return None

    data = json.loads(line)

    message_type = data.get("type")

    if message_type == "system" and data.get("subtype") == "init":
        return (message_type, _handle_init_message(data))
    elif message_type == "system" and data.get("subtype") == "task_started":
        return (message_type, _handle_task_started_message(data))
    elif message_type == "system" and data.get("subtype") == "task_notification":
        return (message_type, _handle_task_notification_message(data))
    elif message_type == "system" and data.get("subtype") == "task_progress":
        # TODO: task_progress carries usage stats and last_tool_name for in-flight
        # background tasks. Silently drop for now; add a ParsedTaskProgressResponse
        # when we build the "background task running..." UI indicator.
        return None
    elif message_type == "system" and data.get("subtype") == "task_updated":
        return (message_type, _handle_task_updated_message(data))
    elif message_type == "assistant":
        return (message_type, _handle_assistant_message(data))
    elif message_type == "user":
        return (message_type, _handle_tool_result_message(data, tool_use_map))
    elif message_type == "result":
        return (message_type, _handle_stream_end_message(data))

    logger.debug("Unhandled message type: {} with subtype: {}", message_type, data.get("subtype"))

    return None
