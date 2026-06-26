"""Wire-contract constants the integration tests assert against.

These are small, stable values (status/model enums, version pins, a few magic
strings) that the tests need to recognize what the backend emits. They used to
be imported from the Python backend; after the cutover to the TypeScript backend
(Task 9.6) the Python backend is gone, so the test harness keeps its own copies
here. The TypeScript backend is the source of truth for the live values; keep
these in sync with it (they are part of the held-fixed wire contract and rarely
change).
"""

from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum


class TaskStatus(StrEnum):
    """Agent status the frontend tags task elements with (web/derived.py)."""

    BUILDING = "BUILDING"
    RUNNING = "RUNNING"
    READY = "READY"
    WAITING = "WAITING"
    ERROR = "ERROR"
    REQUEST_ERROR = "REQUEST_ERROR"


class LLMModel(StrEnum):
    """The model identifiers the harness accepts (state/messages.py)."""

    CLAUDE_4_OPUS = "CLAUDE-4-OPUS"
    CLAUDE_4_OPUS_200K = "CLAUDE-4-OPUS-200K"
    CLAUDE_4_7_OPUS = "CLAUDE-4-7-OPUS"
    CLAUDE_4_7_OPUS_200K = "CLAUDE-4-7-OPUS-200K"
    CLAUDE_4_6_OPUS = "CLAUDE-4-6-OPUS"
    CLAUDE_4_6_OPUS_200K = "CLAUDE-4-6-OPUS-200K"
    CLAUDE_4_SONNET = "CLAUDE-4-SONNET"
    CLAUDE_4_SONNET_200K = "CLAUDE-4-SONNET-200K"
    CLAUDE_4_HAIKU = "CLAUDE-4-HAIKU"
    CLAUDE_FABLE_5 = "CLAUDE-FABLE-5"
    FAKE_CLAUDE = "FAKE_CLAUDE"
    FAKE_CLAUDE_2 = "FAKE_CLAUDE_2"


@dataclass(frozen=True)
class BlockedVersionRange:
    min_version: str
    max_version: str


@dataclass(frozen=True)
class VersionRange:
    min_version: str
    max_version: str
    recommended_version: str
    blocked_versions: tuple[BlockedVersionRange, ...] = field(default_factory=tuple)


# Managed-dependency version pins (services/managed_tools.py,
# dependency_management_service.py).
CLAUDE_VERSION_RANGE = VersionRange(
    min_version="2.1.170",
    max_version="2.99.99",
    recommended_version="2.1.170",
    blocked_versions=(BlockedVersionRange(min_version="2.1.101", max_version="2.1.101"),),
)
PI_VERSION_RANGE = VersionRange(
    min_version="0.78.0",
    max_version="0.78.0",
    recommended_version="0.78.0",
)
DEPENDENCIES_DIR_NAME = "dependencies"
VERSION_DIR_PREFIX = "version-"

# The pi backchannel plan-approval dialog title (agents/pi_agent/backchannel.py).
PLAN_APPROVAL_DIALOG_TITLE = "__sculptor_plan_approval__"

# WebSocket close code for an invalid/missing session token (web/auth.py).
WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE = 4401

# Claude Code on-disk layout (agents/default/claude_code_sdk/harness.py).
CLAUDE_SESSION_DIRECTORY_NAME = ".claude"
CLAUDE_JSON_FILENAME = ".claude.json"
CLAUDE_LOCAL_SETTINGS_FILENAME = "settings.local.json"
CLAUDE_COMMANDS_DIRECTORY_NAME = "commands"

# Sculptor's MCP server + tool names, as the claude harness wires them
# (agents/default/claude_code_sdk/harness.py). fake_claude emits tool calls
# under these names so the backend recognizes them.
MCP_SERVER_NAME = "sculptor"
MCP_ASK_TOOL_NAME = "ask_user_question"
MCP_EXIT_PLAN_MODE_TOOL_NAME = "exit_plan_mode"
MCP_ASK_TOOL_FQN = f"mcp__{MCP_SERVER_NAME}__{MCP_ASK_TOOL_NAME}"
MCP_EXIT_PLAN_MODE_TOOL_FQN = f"mcp__{MCP_SERVER_NAME}__{MCP_EXIT_PLAN_MODE_TOOL_NAME}"
PRE_COMPACT_CALLBACK_ID = "sculptor_pre_compact"

# Exit code a SIGTERM'd agent process reports (interfaces/agents/constants.py).
AGENT_EXIT_CODE_FROM_SIGTERM = 143
