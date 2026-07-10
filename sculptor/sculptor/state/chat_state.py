import datetime
from enum import StrEnum
from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import Field
from pydantic import Tag

from sculptor.foundation.pydantic_serialization import SerializableModel
from sculptor.foundation.pydantic_serialization import build_discriminator
from sculptor.primitives.ids import AgentMessageID
from sculptor.primitives.ids import ToolUseID


class ContentBlock(SerializableModel):
    object_type: str = Field(..., description="Type discriminator for content blocks")
    type: str = Field(..., description="Type discriminator for content blocks")


class TextBlock(ContentBlock):
    object_type: str = "TextBlock"
    type: Literal["text"] = "text"
    text: str


class ContextSummaryBlock(ContentBlock):
    object_type: str = "ContextSummaryBlock"
    type: Literal["context_summary"] = "context_summary"
    text: str


class ContextClearedBlock(ContentBlock):
    object_type: str = "ContextClearedBlock"
    type: Literal["context_cleared"] = "context_cleared"
    text: str = "Cleared successfully"


class ResumeResponseBlock(ContentBlock):
    object_type: str = "ResumeResponseBlock"
    type: Literal["resume_response"] = "resume_response"


ToolInput = dict[str, Any]

# The interactive-backchannel role of a tool, when it is one — set server-side
# from the task's harness (`Harness.classify_tool_ui_role`) so the frontend
# renders ask-user-question / plan-approval tools by role instead of matching a
# hardcoded set of tool names. `None` for a regular tool.
ToolInteractiveRole = Literal["ask_user_question", "exit_plan_mode"]


class ToolUseBlock(ContentBlock):
    object_type: str = "ToolUseBlock"
    type: Literal["tool_use"] = "tool_use"
    id: ToolUseID = Field(..., description="Unique identifier for this tool use")
    name: str = Field(..., description="Name of the tool being used")
    input: ToolInput = Field(default_factory=ToolInput, description="Input parameters for the tool")
    interactive_role: ToolInteractiveRole | None = Field(
        default=None,
        description="Set server-side from the harness when this tool is an interactive-backchannel surface (ask-user-question / exit-plan-mode); the frontend renders by this role rather than by tool name. None for a regular tool.",
    )


class ToolResultContent(SerializableModel):
    """Base class for tool result content with type discriminator"""

    content_type: str = Field(..., description="Type discriminator for tool result content")


class SimpleToolContent(ToolResultContent):
    """Generic tool content, or information to reconstruct diff tool content"""

    content_type: Literal["simple"] = "simple"
    text: str = Field(..., description="The tool output as text")
    tool_input: ToolInput
    tool_content: Any


class GenericToolContent(ToolResultContent):
    """Generic content for most tools - just a string"""

    content_type: Literal["generic"] = "generic"
    text: str = Field(..., description="The tool output as text")


class DiffToolContent(ToolResultContent):
    """Content for diff-producing tools (Write, Edit, MultiEdit)"""

    content_type: Literal["diff"] = "diff"
    diff: str = Field(..., description="The git diff string")
    file_path: str = Field(..., description="The file that was modified")


ToolResultContentType = GenericToolContent | DiffToolContent


class ToolResultBlockSimple(ContentBlock):
    object_type: str = "ToolResultBlockSimple"
    type: Literal["tool_result_simple"] = "tool_result_simple"
    tool_use_id: ToolUseID = Field(..., description="ID of the corresponding tool use")
    tool_name: str = Field(..., description="Name of the tool that was used")
    invocation_string: str = Field(..., description="String representation of how the tool was invoked")
    content: SimpleToolContent = Field(..., description="Result content from the tool execution")
    is_error: bool = Field(default=False, description="Whether the tool execution resulted in an error")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock duration of the tool execution in seconds"
    )
    description: str | None = Field(default=None, description="Human-readable description of what the tool call does")


class ToolResultBlock(ContentBlock):
    object_type: str = "ToolResultBlock"
    type: Literal["tool_result"] = "tool_result"
    tool_use_id: ToolUseID = Field(..., description="ID of the corresponding tool use")
    tool_name: str = Field(..., description="Name of the tool that was used")
    invocation_string: str = Field(..., description="String representation of how the tool was invoked")
    content: ToolResultContentType = Field(..., description="Result content from the tool execution")
    is_error: bool = Field(default=False, description="Whether the tool execution resulted in an error")
    duration_seconds: float | None = Field(
        default=None, description="Wall-clock duration of the tool execution in seconds"
    )
    interactive_role: ToolInteractiveRole | None = Field(
        default=None,
        description="Set server-side from the harness when the originating tool is an interactive-backchannel surface; lets the frontend suppress the result (it renders inside the question panel) by role rather than by tool name. None for a regular tool.",
    )
    description: str | None = Field(default=None, description="Human-readable description of what the tool call does")
    background_task_id: str | None = Field(
        default=None,
        description="Set when this tool call launched a background task (an Agent/Task call converted to an async agent, or a run_in_background Bash): the CLI task id, matchable against pending_background_task_ids. When set, `content` is only the launch acknowledgment — the tool's real outcome arrives later via the task's notification, not in this block.",
    )


class WarningBlock(ContentBlock):
    object_type: str = "WarningBlock"
    type: Literal["warning"] = "warning"
    message: str = Field(..., description="Warning message")
    traceback: str | None = Field(..., description="Warning traceback")
    warning_type: str | None = Field(..., description="Type of warning, i.e. name of the exception that was raised")


class ErrorBlock(ContentBlock):
    object_type: str = "ErrorBlock"
    type: Literal["error"] = "error"
    message: str = Field(..., description="Error message")
    traceback: str = Field(..., description="Error traceback")
    error_type: str = Field(..., description="Type of error, i.e. name of the exception that was raised")


class FileBlock(ContentBlock):
    object_type: str = "FileBlock"
    type: Literal["file"] = "file"
    source: str = Field(..., description="A file path on the users local machine.")


class TurnMetrics(SerializableModel):
    """Per-turn metrics attached to completed assistant messages."""

    duration_seconds: float = Field(..., description="Wall-clock turn duration in seconds")
    input_tokens: int | None = Field(
        default=None, description="Input tokens for this turn (None when interrupted before completion)"
    )
    output_tokens: int | None = Field(
        default=None, description="Output tokens for this turn (None when interrupted before completion)"
    )
    reasoning_tokens: int | None = Field(
        default=None, description="Reasoning/thinking tokens (None if not applicable)"
    )
    changed_files: list[str] = Field(
        default_factory=list,
        description="File paths changed during this turn (git-relative, all tools including Bash)",
    )
    # Context usage snapshot at the end of this turn. Sourced from the
    # get_context_usage control response, attached here so each turn footer
    # shows its own historical point-in-time values.
    context_total_tokens: int | None = Field(
        default=None, description="Total tokens in the context window at turn end (None if unavailable)"
    )
    auto_compact_threshold: int | None = Field(
        default=None, description="Threshold at which auto-compaction fires (denominator for the percent display)"
    )


ContentBlockTypes = Annotated[
    (
        Annotated[TextBlock, Tag("TextBlock")]
        | Annotated[ToolUseBlock, Tag("ToolUseBlock")]
        | Annotated[ToolResultBlock, Tag("ToolResultBlock")]
        | Annotated[ErrorBlock, Tag("ErrorBlock")]
        | Annotated[WarningBlock, Tag("WarningBlock")]
        | Annotated[ContextSummaryBlock, Tag("ContextSummaryBlock")]
        | Annotated[ContextClearedBlock, Tag("ContextClearedBlock")]
        | Annotated[ResumeResponseBlock, Tag("ResumeResponseBlock")]
        | Annotated[FileBlock, Tag("FileBlock")]
    ),
    build_discriminator(),
]


class ChatMessageRole(StrEnum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"


class ChatMessage(SerializableModel):
    """Chat message with content blocks. A ChatMessage corresponds to a single turn in the conversation."""

    role: ChatMessageRole
    id: AgentMessageID
    content: tuple[ContentBlockTypes, ...]
    parent_tool_use_id: str | None = Field(
        default=None,
        description="Tool use ID of the parent Task call if this message belongs to a subagent",
    )
    approximate_creation_time: datetime.datetime = Field(
        ...,
        description="Approximate UTC timestamp when the message was created",
    )
    turn_metrics: TurnMetrics | None = Field(
        default=None,
        description="Per-turn metrics (duration, tokens) for completed assistant messages",
    )
    stopped: bool = Field(
        default=False,
        description="Whether this turn was stopped by the user",
    )
    sent_via: str | None = Field(
        default=None,
        description="Interface that sent this message, e.g. 'sculpt'",
    )


class QuestionOption(SerializableModel):
    label: str
    description: str


class UserQuestion(SerializableModel):
    question: str
    header: str
    options: list[QuestionOption]
    multi_select: bool
    other_label: str | None = None


class AskUserQuestionData(SerializableModel):
    questions: list[UserQuestion]
    tool_use_id: str
    plan_file_path: str | None = Field(
        default=None,
        description="Absolute path of the plan file the agent wrote in this turn, when the question is the synthesized ExitPlanMode approval. Set by `make_plan_approval_question` and consumed by the frontend ExitPlanMode tool block to render a click-to-reopen link. None for non-plan-approval questions or when the agent didn't write a plan file in the current turn (e.g. re-using a plan from a prior turn).",
    )


def make_plan_approval_question(
    tool_use_id: str,
    plan_file_path: str | None = None,
) -> AskUserQuestionData:
    """Construct the plan approval question shown when the agent calls ExitPlanMode.

    The optional plan_file_path is propagated to the frontend so the
    ExitPlanMode tool block can render a click-to-reopen link without
    scanning the chat for .claude/plans/ tool results.
    """
    return AskUserQuestionData(
        questions=[
            UserQuestion(
                question="Planning complete. How would you like to proceed?",
                header="Plan approval",
                options=[
                    QuestionOption(label="Approve plan", description="Proceed with implementing the plan"),
                ],
                multi_select=False,
                other_label="Revise",
            ),
        ],
        tool_use_id=tool_use_id,
        plan_file_path=plan_file_path,
    )
