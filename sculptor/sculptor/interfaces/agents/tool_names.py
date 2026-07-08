import enum


class AgentToolName(enum.StrEnum):
    """Enumeration of all known coding agent tools across Claude Code and Codex.

    This is a superset of tools available across different coding agents.
    Not all tools are available in all agents.
    """

    # File operations
    READ = "Read"
    WRITE = "Write"
    EDIT = "Edit"
    MULTI_EDIT = "MultiEdit"
    GLOB = "Glob"
    NOTEBOOK_READ = "NotebookRead"
    NOTEBOOK_EDIT = "NotebookEdit"
    LS = "LS"

    # Search operations
    GREP = "Grep"

    # Execution tools
    BASH = "Bash"
    BASH_OUTPUT = "BashOutput"
    KILL_SHELL = "KillShell"

    # Web operations
    WEB_SEARCH = "WebSearch"
    WEB_FETCH = "WebFetch"

    # Agent orchestration
    TASK = "Task"
    WORKFLOW = "Workflow"
    TASK_CREATE = "TaskCreate"
    TASK_UPDATE = "TaskUpdate"
    TASK_LIST = "TaskList"
    TASK_GET = "TaskGet"
    SLASH_COMMAND = "SlashCommand"
    EXIT_PLAN_MODE = "exit_plan_mode"

    # MCP tools
    MCP_TOOL = "mcp_tool"  # Generic MCP tool prefix
    LIST_MCP_RESOURCES = "ListMcpResourcesTool"
    READ_MCP_RESOURCE = "ReadMcpResourceTool"

    # Code execution
    CODE_EXECUTION = "code_execution"
    BASH_CODE_EXECUTION = "bash_code_execution"
    TEXT_EDITOR_CODE_EXECUTION = "text_editor_code_execution"

    # Codex-specific operations
    COMMAND_EXECUTION = "command_execution"  # Codex's command execution
    FILE_CHANGE = "file_change"  # Codex's file change operation

    # Other tools
    AGENT = "Agent"
    SKILL = "Skill"
    COMPUTER = "computer"  # Computer use capability
    MEMORY = "memory"  # Memory storage
    OTHER = "other"  # Catch-all for unknown/custom tools
