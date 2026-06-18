"""Pydantic models for parsing pi's JSONL RPC events.

Pi's stdout multiplexes three channels distinguished by top-level
`type`: command-acknowledgement `response` envelopes, `extension_ui_request`
dialog calls, and the `AgentSessionEvent` union. The models below cover the
**full documented wire vocabulary** (RPC §4 commands, §5 responses /
session events / extension UI, §7 streaming sub-events, §9 tool events), so
the dispatcher parses once at the boundary and dispatches on typed variants.
Events pi-basic does not consume (turn boundaries, queue/compaction/retry
notices, tool-call rendering) are modeled but currently ignored by the
dispatcher.

Field names are the Python snake_case mirror of pi's camelCase wire shapes;
`SerializableModel`'s `to_camel` alias generator bridges them, and
`validate_by_name=True` lets tests construct by either name. Unknown `type`s
parse to `ParsedUnknownEvent` and are debug-logged and ignored (RPC §5.3
forward-compat).

Reference: the pi RPC protocol notes (pi 0.78.0).
"""

from __future__ import annotations

from typing import Annotated
from typing import Any
from typing import Literal

from pydantic import Field
from pydantic import TypeAdapter
from pydantic import ValidationError

from sculptor.foundation.pydantic_serialization import SerializableModel


# `content` is untyped dicts: pi interleaves text and toolCall blocks, and only
# the text blocks are consumed here.
class AgentMessage(SerializableModel):
    role: str
    content: list[dict[str, Any]] = []
    stop_reason: str | None = None
    # The model id pi reports as having produced this message (assistant
    # messages); absent on other roles.
    model: str | None = None
    # The failure reason pi records when a turn ends in error — carried on an
    # otherwise-empty assistant message with `stopReason:"error"` (e.g. a
    # provider-auth failure). The only place the real reason lives for a turn
    # that fails without a preceding in-stream error event.
    error_message: str | None = None


def extract_assistant_text(message: AgentMessage) -> str:
    """Concatenate every `{type:"text"}` block on an assistant message."""
    return "".join(block.get("text", "") for block in message.content if block.get("type") == "text")


# Substrings (matched case-insensitively) in pi's failure reason that mark a
# provider-auth failure — typically selecting a model whose provider has no
# valid key.
_AUTH_FAILURE_MARKERS = (
    "api key",
    "apikey",
    "api_key",
    "authentication",
    "unauthorized",
    "unauthenticated",
    "401",
    "403",
    "forbidden",
    "permission denied",
    "credential",
)
# Substrings (matched case-insensitively) marking an unknown / unavailable model.
_UNKNOWN_MODEL_MARKERS = (
    "model not found",
    "unknown model",
    "model_not_found",
    "no such model",
    "model does not exist",
)
_AUTH_FAILURE_MESSAGE = (
    "This model isn't available — it may require authentication with its provider. Try another model."
)
_UNKNOWN_MODEL_MESSAGE = (
    "This model isn't available — it may not exist or isn't enabled for your account. Try another model."
)
_GENERIC_FAILURE_MESSAGE = "The model failed to complete this turn. Try again, or switch to another model."


def humanize_pi_failure_reason(reason: str | None) -> str:
    """Turn pi's raw turn-failure reason into a clean, actionable message.

    Recognized failure shapes (provider auth, unknown/unavailable model) lead
    with specific guidance and preserve pi's raw reason on a `Details:` line so
    debugging isn't lost. An already human-readable reason (e.g. pi's own API
    error text) is surfaced unchanged. An empty reason falls back to a clean
    generic message — never the bare "pi message ended in error" placeholder.
    """
    cleaned = (reason or "").strip()
    lowered = cleaned.lower()
    if any(marker in lowered for marker in _AUTH_FAILURE_MARKERS):
        return f"{_AUTH_FAILURE_MESSAGE}\n\nDetails: {cleaned}"
    if any(marker in lowered for marker in _UNKNOWN_MODEL_MARKERS):
        return f"{_UNKNOWN_MODEL_MESSAGE}\n\nDetails: {cleaned}"
    if cleaned:
        return cleaned
    return _GENERIC_FAILURE_MESSAGE


def extract_tool_call_blocks(message: AgentMessage) -> list[dict[str, Any]]:
    """Return the `{type:"toolCall",...}` content blocks on a message.

    Raw dicts, like `content`; consumed by tool-use rendering.
    """
    return [block for block in message.content if block.get("type") == "toolCall"]


# --- Lane 1: command responses (RPC §5.1) ---------------------------------


class RpcResponse(SerializableModel):
    type: Literal["response"]
    command: str
    success: bool
    id: str | None = None
    error: str | None = None
    data: dict[str, Any] | None = None


# --- Lane 2: extension UI requests (RPC §5.3) -----------------------------


class ExtensionUiRequest(SerializableModel):
    type: Literal["extension_ui_request"]
    id: str
    # `method` splits into blocking dialogs (`select`/`confirm`/`input`/
    # `editor`) and fire-and-forget calls (`notify`/`setStatus`/`setWidget`/
    # `setTitle`/`set_editor_text`). `timeout`, when present, means pi
    # auto-resolves a dialog with a default if the client doesn't reply, so
    # the client need not track timeouts — the backchannel extension never sets
    # one (Sculptor's unbounded-wait question model).
    method: str
    timeout: int | None = None
    # Dialog payload fields the backchannel dispatcher consumes (RPC §5.3):
    # `select`/`input`/`confirm`/`editor` carry a `title`; `select` also carries
    # `options`. Other method-specific fields ride `extra="allow"`.
    title: str | None = None
    options: list[str] | None = None
    # The `notify` method's text payload. Sculptor's background-task extension
    # encodes its structured completion marker here, so the dispatcher parses it
    # (`background.py`) onto a BackgroundTaskNotification (RPC §5.3 notify).
    message: str | None = None


# --- Lane 3: session events (the AgentSessionEvent union, RPC §5.2) --------


class ParsedAgentStart(SerializableModel):
    type: Literal["agent_start"]


class ParsedAgentEnd(SerializableModel):
    type: Literal["agent_end"]
    messages: list[AgentMessage] = []
    will_retry: bool = False


class ParsedTurnStart(SerializableModel):
    type: Literal["turn_start"]


class ParsedTurnEnd(SerializableModel):
    type: Literal["turn_end"]
    message: AgentMessage
    tool_results: list[AgentMessage] = []


class ParsedMessageStart(SerializableModel):
    type: Literal["message_start"]
    message: AgentMessage


class ParsedMessageUpdate(SerializableModel):
    type: Literal["message_update"]
    message: AgentMessage
    # WHY: kept as a raw dict — pi nests ~12 `assistantMessageEvent.type`
    # variants (see `ParsedAssistantMessageEvent` for the typed vocabulary)
    # and pi-basic only dispatches on `text_delta` / `error`; the caller
    # validates the variant it consumes (see `ParsedTextDelta`
    # / `ParsedAssistantMessageError`).
    assistant_message_event: dict[str, Any]


class ParsedMessageEnd(SerializableModel):
    type: Literal["message_end"]
    message: AgentMessage


class ParsedToolExecutionStart(SerializableModel):
    type: Literal["tool_execution_start"]
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = {}


class ParsedToolExecutionUpdate(SerializableModel):
    type: Literal["tool_execution_update"]
    tool_call_id: str = ""
    tool_name: str = ""
    args: dict[str, Any] = {}
    # WHY: ACCUMULATED tool output so far, NOT a delta (RPC §9) — a consumer
    # replaces its display on each update rather than appending.
    partial_result: Any = None


class ParsedToolExecutionEnd(SerializableModel):
    type: Literal["tool_execution_end"]
    tool_call_id: str = ""
    tool_name: str = ""
    # `result` shape is tool-specific and uncharacterized in the doc (RPC §9);
    # left permissive.
    result: Any = None
    is_error: bool = False


class ParsedQueueUpdate(SerializableModel):
    type: Literal["queue_update"]
    steering: list[str] = []
    follow_up: list[str] = []


class ParsedCompactionStart(SerializableModel):
    type: Literal["compaction_start"]
    reason: Literal["manual", "threshold", "overflow"]


class ParsedCompactionEnd(SerializableModel):
    type: Literal["compaction_end"]
    reason: Literal["manual", "threshold", "overflow"]
    # `result` shape uncharacterized in the doc (RPC §5.2); left permissive.
    result: Any = None
    aborted: bool = False
    will_retry: bool = False
    error_message: str | None = None


class ParsedAutoRetryStart(SerializableModel):
    type: Literal["auto_retry_start"]
    attempt: int = 0
    max_attempts: int = 0
    delay_ms: int = 0
    error_message: str = ""


class ParsedAutoRetryEnd(SerializableModel):
    type: Literal["auto_retry_end"]
    success: bool
    attempt: int = 0
    final_error: str | None = None


class ParsedSessionInfoChanged(SerializableModel):
    type: Literal["session_info_changed"]
    name: str | None = None


class ParsedThinkingLevelChanged(SerializableModel):
    type: Literal["thinking_level_changed"]
    # ThinkingLevel: off|minimal|low|medium|high|xhigh (RPC §4); left as a
    # str since pi-basic does not act on it.
    level: str = ""


class ParsedExtensionError(SerializableModel):
    type: Literal["extension_error"]
    extension_path: str = ""
    event: str = ""
    error: str = ""


# --- Streaming sub-events: the `assistantMessageEvent` vocabulary (RPC §7) -
#
# These live INSIDE a `message_update` event's `assistantMessageEvent` field.
# pi-basic consumes only `text_delta` and `error`; the rest are modeled but
# currently unused. Several carry fields the doc leaves uncharacterized
# (`partial`, thinking/toolcall delta payloads) — those are left to
# `extra="allow"`.


class ParsedTextDelta(SerializableModel):
    type: Literal["text_delta"]
    delta: str = ""
    content_index: int = 0


class ParsedTextStart(SerializableModel):
    type: Literal["text_start"]
    content_index: int = 0


class ParsedTextEnd(SerializableModel):
    type: Literal["text_end"]
    content_index: int = 0
    content: str = ""


class ParsedThinkingStart(SerializableModel):
    type: Literal["thinking_start"]


class ParsedThinkingDelta(SerializableModel):
    type: Literal["thinking_delta"]


class ParsedThinkingEnd(SerializableModel):
    type: Literal["thinking_end"]


class ParsedToolcallStart(SerializableModel):
    type: Literal["toolcall_start"]


class ParsedToolcallDelta(SerializableModel):
    type: Literal["toolcall_delta"]


class ParsedToolcallEnd(SerializableModel):
    type: Literal["toolcall_end"]
    # Full tool-call object on completion (RPC §7); shape is the toolCall
    # content block, left permissive.
    tool_call: dict[str, Any] = {}


class ParsedStreamStart(SerializableModel):
    type: Literal["start"]


class ParsedStreamDone(SerializableModel):
    type: Literal["done"]
    reason: Literal["stop", "length", "toolUse"] = "stop"


class ParsedAssistantMessageError(SerializableModel):
    type: Literal["error"]
    reason: str = ""


# The documented `assistantMessageEvent` union (RPC §7) — the variants nested in
# a `message_update`, which parses them lazily from its raw-dict field.
ParsedAssistantMessageEvent = (
    ParsedStreamStart
    | ParsedTextStart
    | ParsedTextDelta
    | ParsedTextEnd
    | ParsedThinkingStart
    | ParsedThinkingDelta
    | ParsedThinkingEnd
    | ParsedToolcallStart
    | ParsedToolcallDelta
    | ParsedToolcallEnd
    | ParsedStreamDone
    | ParsedAssistantMessageError
)


# --- The full RPC message union + parse entry point -----------------------


class ParsedUnknownEvent(SerializableModel):
    """Fallback for any stdout payload whose `type` is unrecognized or whose
    known shape fails validation (RPC §5.3 forward-compat: the dispatcher
    debug-logs and ignores it). Holds the raw payload for logging.
    """

    raw: dict[str, Any]


# The three lanes pi multiplexes, as one discriminated union over `type`.
# `ParsedUnknownEvent` is NOT a member — it is the parse fallback for a
# missing/unknown discriminator or a known shape that fails validation.
ParsedKnownRpcMessage = (
    RpcResponse
    | ExtensionUiRequest
    | ParsedAgentStart
    | ParsedAgentEnd
    | ParsedTurnStart
    | ParsedTurnEnd
    | ParsedMessageStart
    | ParsedMessageUpdate
    | ParsedMessageEnd
    | ParsedToolExecutionStart
    | ParsedToolExecutionUpdate
    | ParsedToolExecutionEnd
    | ParsedQueueUpdate
    | ParsedCompactionStart
    | ParsedCompactionEnd
    | ParsedAutoRetryStart
    | ParsedAutoRetryEnd
    | ParsedSessionInfoChanged
    | ParsedThinkingLevelChanged
    | ParsedExtensionError
)

ParsedRpcMessage = ParsedKnownRpcMessage | ParsedUnknownEvent

# Discriminated on `type` for O(1) dispatch (vs. trying each member). Pi's three
# lanes (`response`, `extension_ui_request`, session events) are distinguished
# by `type` (RPC §5).
_KNOWN_RPC_ADAPTER: TypeAdapter[ParsedKnownRpcMessage] = TypeAdapter(
    Annotated[ParsedKnownRpcMessage, Field(discriminator="type")]
)


def parse_rpc_message(event: dict[str, Any]) -> ParsedRpcMessage:
    """Parse one raw pi stdout JSON object into a typed variant.

    An unknown `type`, a missing discriminator, or a known `type` whose payload
    fails validation becomes `ParsedUnknownEvent`, which the dispatcher
    debug-logs and ignores (RPC §5.3 forward-compat).
    """
    try:
        return _KNOWN_RPC_ADAPTER.validate_python(event)
    except ValidationError:
        return ParsedUnknownEvent(raw=event)
