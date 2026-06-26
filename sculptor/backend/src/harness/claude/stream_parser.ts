// Pure stream-json parsing for the Claude CLI's stdout, ported from
// `state/claude_state.py` (`parse_claude_code_json_lines_simple`,
// `extract_media_tags_from_text`, `split_text_and_media`,
// `get_tool_invocation_string`) and the tool-content synthesis in
// `process_manager_utils.py` (`_create_tool_content` /
// `_create_synthetic_*_diff`). Produces typed `Parsed*` objects whose content
// blocks are the plain JSON dicts the message log stores and the fold
// consumes — `object_type`/`type` discriminators reproduced exactly.
//
// The diff-tracker fast path (live `git diff` per tool, `diff_tracker.py`) is
// not reproduced here; file-change tools synthesize a git-format diff from the
// tool input (the same fallback the Python path uses when the tracker is
// unavailable), which is sufficient for the frontend's file chip.

// --- Content block dicts --------------------------------------------------

export type Block = Record<string, unknown>;

export function makeTextBlock(text: string): Block {
  return { object_type: "TextBlock", type: "text", text };
}

export function makeFileBlock(source: string): Block {
  return { object_type: "FileBlock", type: "file", source };
}

export function makeToolUseBlock(
  id: string,
  name: string,
  input: Record<string, unknown>,
): Block {
  return {
    object_type: "ToolUseBlock",
    type: "tool_use",
    id,
    name,
    input,
    interactive_role: null,
  };
}

export interface GenericToolContent {
  content_type: "generic";
  text: string;
}
export interface DiffToolContent {
  content_type: "diff";
  diff: string;
  file_path: string;
}

export function makeToolResultBlock(args: {
  toolUseId: string;
  toolName: string;
  invocationString: string;
  content: GenericToolContent | DiffToolContent;
  isError: boolean;
  description: string | null;
  durationSeconds?: number | null;
}): Block {
  return {
    object_type: "ToolResultBlock",
    type: "tool_result",
    tool_use_id: args.toolUseId,
    tool_name: args.toolName,
    invocation_string: args.invocationString,
    content: args.content,
    is_error: args.isError,
    duration_seconds: args.durationSeconds ?? null,
    interactive_role: null,
    description: args.description,
  };
}

// --- Media extraction -----------------------------------------------------

const RE_IMG_TAG = /<img\s[^>]*src=["']([^"']+)["'][^>]*\/?>(?:\s*<\/img>)?/gi;
const RE_VIDEO_TAG =
  /<video\s[^>]*src=["']([^"']+)["'][^>]*\/?>(?:\s*<\/video>)?/gi;
const SUPPORTED_MEDIA_EXTENSIONS = [
  ".png",
  ".jpg",
  ".jpeg",
  ".gif",
  ".webp",
  ".svg",
  ".mp4",
  ".webm",
  ".mov",
];

function hasSupportedMediaExtension(path: string): boolean {
  const lower = path.toLowerCase();
  return SUPPORTED_MEDIA_EXTENSIONS.some((ext) => lower.endsWith(ext));
}

interface MediaMatch {
  source: string;
  start: number;
  end: number;
}

function findLocalMediaMatches(text: string): MediaMatch[] {
  const matches: MediaMatch[] = [];
  for (const re of [RE_IMG_TAG, RE_VIDEO_TAG]) {
    re.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      const source = m[1];
      if (
        source !== undefined &&
        source.startsWith("/") &&
        hasSupportedMediaExtension(source)
      ) {
        matches.push({ source, start: m.index, end: m.index + m[0].length });
      }
    }
  }
  matches.sort((a, b) => a.start - b.start);
  return matches;
}

// Strip <img>/<video> tags with local media paths; returns cleaned text + paths.
export function extractMediaTagsFromText(text: string): {
  cleanedText: string;
  filePaths: string[];
} {
  const matches = findLocalMediaMatches(text);
  const filePaths = matches.map((m) => m.source);
  let cleaned = text;
  for (let i = matches.length - 1; i >= 0; i--) {
    const match = matches[i];
    if (match !== undefined) {
      cleaned = cleaned.slice(0, match.start) + cleaned.slice(match.end);
    }
  }
  return { cleanedText: cleaned.trim(), filePaths };
}

// Split text into interleaved TextBlock/FileBlock segments, preserving order.
export function splitTextAndMedia(text: string): Block[] {
  const matches = findLocalMediaMatches(text);
  if (matches.length === 0) {
    return [makeTextBlock(text)];
  }
  const result: Block[] = [];
  let prevEnd = 0;
  for (const match of matches) {
    const preceding = text.slice(prevEnd, match.start).trim();
    if (preceding) {
      result.push(makeTextBlock(preceding));
    }
    result.push(makeFileBlock(match.source));
    prevEnd = match.end;
  }
  const trailing = text.slice(prevEnd).trim();
  if (trailing) {
    result.push(makeTextBlock(trailing));
  }
  return result;
}

// --- Tool invocation string -----------------------------------------------

export function getToolInvocationString(
  toolName: string,
  toolInput: Record<string, unknown>,
): string {
  const str = (key: string): string => {
    const v = toolInput[key];
    return typeof v === "string" ? v : "";
  };
  switch (toolName) {
    case "Read":
    case "Write":
    case "Edit":
    case "MultiEdit":
      return str("file_path");
    case "Bash":
      return str("command");
    case "Grep":
    case "Glob": {
      const pattern = str("pattern");
      const path = str("path");
      return `"${pattern}"` + (path ? ` in ${path}` : "");
    }
    case "LS":
      return str("path");
    case "NotebookRead":
    case "NotebookEdit":
      return str("notebook_path");
    case "WebFetch":
      return str("url");
    case "WebSearch":
      return str("query");
    case "Task":
      return str("description");
    case "Skill":
      return str("skill");
    default: {
      for (const key of ["path", "file_path", "command"]) {
        if (typeof toolInput[key] === "string") {
          return toolInput[key] as string;
        }
      }
      for (const value of Object.values(toolInput)) {
        if (typeof value === "string" && value) {
          return value;
        }
      }
      return "tool invocation";
    }
  }
}

// --- Tool-result content synthesis ----------------------------------------

const FILE_CHANGE_TOOLS: ReadonlySet<string> = new Set([
  "Write",
  "Edit",
  "MultiEdit",
]);

function syntheticWriteDiff(filePath: string, content: string): string {
  const lines = content.split("\n");
  const additions = lines.map((line) => "+" + line).join("\n");
  return (
    `diff --git a/${filePath} b/${filePath}\n` +
    `new file mode 100644\n` +
    `--- /dev/null\n` +
    `+++ b/${filePath}\n` +
    `@@ -0,0 +1,${lines.length} @@\n` +
    `${additions}\n`
  );
}

function extractEdits(toolInput: Record<string, unknown>): [string, string][] {
  const editsField = toolInput.edits;
  if (Array.isArray(editsField)) {
    const pairs: [string, string][] = [];
    for (const edit of editsField) {
      if (typeof edit === "object" && edit !== null) {
        const e = edit as Record<string, unknown>;
        if (
          typeof e.old_string === "string" &&
          typeof e.new_string === "string"
        ) {
          pairs.push([e.old_string, e.new_string]);
        }
      }
    }
    return pairs;
  }
  if (
    typeof toolInput.old_string === "string" &&
    typeof toolInput.new_string === "string"
  ) {
    return [[toolInput.old_string, toolInput.new_string]];
  }
  return [];
}

function syntheticEditDiff(
  filePath: string,
  edits: [string, string][],
): string {
  const lines: string[] = [
    `diff --git a/${filePath} b/${filePath}`,
    "index 0000000..0000000 100644",
    `--- a/${filePath}`,
    `+++ b/${filePath}`,
  ];
  for (const [oldString, newString] of edits) {
    const oldLines = oldString.split("\n");
    const newLines = newString.split("\n");
    lines.push(`@@ -1,${oldLines.length} +1,${newLines.length} @@`);
    lines.push(...oldLines.map((l) => "-" + l));
    lines.push(...newLines.map((l) => "+" + l));
  }
  return lines.join("\n") + "\n";
}

function syntheticDiffFromToolInput(
  toolName: string,
  filePath: string,
  toolInput: Record<string, unknown>,
): string | null {
  if (toolName === "Write") {
    const content = toolInput.content;
    if (typeof content === "string" && content) {
      return syntheticWriteDiff(filePath, content);
    }
    return null;
  }
  const edits = extractEdits(toolInput);
  if (edits.length > 0) {
    return syntheticEditDiff(filePath, edits);
  }
  return null;
}

// Mirrors `_create_tool_content`: a DiffToolContent for a successful
// file-change tool (so the file chip resolves a path), else GenericToolContent.
export function createToolContent(
  toolName: string,
  toolInput: Record<string, unknown>,
  toolContent: unknown,
  isError: boolean,
): GenericToolContent | DiffToolContent {
  if (FILE_CHANGE_TOOLS.has(toolName) && !isError) {
    const filePath =
      typeof toolInput.file_path === "string" ? toolInput.file_path : "";
    const diff = syntheticDiffFromToolInput(toolName, filePath, toolInput);
    if (diff !== null) {
      return { content_type: "diff", diff, file_path: filePath };
    }
  }
  return { content_type: "generic", text: stringifyToolContent(toolContent) };
}

// Approximate Python's `str(tool_content)` for the common shapes (string or a
// list of content blocks). Objects fall back to JSON.
function stringifyToolContent(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (value === null || value === undefined) {
    return String(value);
  }
  return JSON.stringify(value);
}

// --- Stream events --------------------------------------------------------

export type ParsedStreamEvent =
  | { kind: "message_start"; messageId: string; parentToolUseId: string | null }
  | { kind: "message_stop" }
  | { kind: "text_block_start"; index: number }
  | {
      kind: "tool_block_start";
      index: number;
      toolId: string;
      toolName: string;
    }
  | { kind: "text_delta"; index: number; text: string }
  | { kind: "tool_input_delta"; index: number; partialJson: string }
  | { kind: "content_block_stop"; index: number };

// --- Non-stream parsed responses ------------------------------------------

export interface ParsedInitResponse {
  kind: "init";
  sessionId: string;
}
export interface ParsedAssistantResponse {
  kind: "assistant";
  messageId: string;
  contentBlocks: Block[];
  parentToolUseId: string | null;
}
export interface ParsedToolResultResponse {
  kind: "tool_result";
  contentBlocks: Block[];
  parentToolUseId: string | null;
  scheduledWakeupFor: number | null;
  // Per-block tool metadata needed for diff/artifact decisions.
  toolUseIds: string[];
}
export interface ParsedEndResponse {
  kind: "end";
  isError: boolean;
  result: string;
  durationMs: number | null;
  inputTokens: number | null;
  outputTokens: number | null;
  totalCostUsd: number | null;
  sessionId: string | null;
}
export interface ParsedTaskStartedResponse {
  kind: "task_started";
  taskId: string;
  toolUseId: string;
  description: string;
  taskType: string;
}
export interface ParsedTaskNotificationResponse {
  kind: "task_notification";
  taskId: string;
  toolUseId: string;
  status: string;
  summary: string;
  durationMs: number | null;
}
export interface ParsedTaskUpdatedResponse {
  kind: "task_updated";
  taskId: string;
  status: string;
}

export type ParsedResponse =
  | ParsedInitResponse
  | ParsedAssistantResponse
  | ParsedToolResultResponse
  | ParsedEndResponse
  | ParsedTaskStartedResponse
  | ParsedTaskNotificationResponse
  | ParsedTaskUpdatedResponse;

export type ToolUseMap = Map<
  string,
  { name: string; input: Record<string, unknown> }
>;

// Strips ANSI escape sequences the CLI may emit. Built from a computed ESC
// (char 27) rather than a control-char regex literal.
const ESC = String.fromCharCode(27);
const RE_STRIP_ANSI = new RegExp(
  `${ESC}\\[[0-9;]*[mGKHfABCDhls]|${ESC}\\[[?][0-9;]*[hlHLdcE]|${ESC}[=>]`,
  "g",
);

function asNumberOrNull(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}

// Parse a stream_event line into a ParsedStreamEvent, or null for events we
// don't surface. Mirrors the stream_event branch of `parse_claude_code_json_lines`.
function parseStreamEvent(
  data: Record<string, unknown>,
): ParsedStreamEvent | null {
  const event = (data.event ?? {}) as Record<string, unknown>;
  const eventType = event.type;
  if (eventType === "message_start") {
    const message = (event.message ?? {}) as Record<string, unknown>;
    return {
      kind: "message_start",
      messageId: typeof message.id === "string" ? message.id : "",
      parentToolUseId:
        typeof data.parent_tool_use_id === "string"
          ? data.parent_tool_use_id
          : null,
    };
  }
  if (eventType === "message_stop") {
    return { kind: "message_stop" };
  }
  if (eventType === "content_block_start") {
    const contentBlock = (event.content_block ?? {}) as Record<string, unknown>;
    const index = typeof event.index === "number" ? event.index : 0;
    if (contentBlock.type === "text") {
      return { kind: "text_block_start", index };
    }
    if (contentBlock.type === "tool_use") {
      return {
        kind: "tool_block_start",
        index,
        toolId: String(contentBlock.id ?? ""),
        toolName: String(contentBlock.name ?? ""),
      };
    }
    return null;
  }
  if (eventType === "content_block_delta") {
    const delta = (event.delta ?? {}) as Record<string, unknown>;
    const index = typeof event.index === "number" ? event.index : 0;
    if (delta.type === "input_json_delta") {
      return {
        kind: "tool_input_delta",
        index,
        partialJson: String(delta.partial_json ?? ""),
      };
    }
    if (delta.type === "text_delta") {
      return { kind: "text_delta", index, text: String(delta.text ?? "") };
    }
    return null;
  }
  if (eventType === "content_block_stop") {
    return {
      kind: "content_block_stop",
      index: typeof event.index === "number" ? event.index : 0,
    };
  }
  return null;
}

function parseAssistant(
  data: Record<string, unknown>,
): ParsedAssistantResponse {
  const messageData = (data.message ?? {}) as Record<string, unknown>;
  const messageId = String(messageData.id ?? "");
  const blocks: Block[] = [];
  const content = Array.isArray(messageData.content) ? messageData.content : [];
  for (const raw of content) {
    if (typeof raw !== "object" || raw === null) {
      continue;
    }
    const c = raw as Record<string, unknown>;
    if (c.type === "text") {
      const { cleanedText, filePaths } = extractMediaTagsFromText(
        String(c.text ?? ""),
      );
      if (cleanedText) {
        blocks.push(makeTextBlock(cleanedText));
      }
      for (const path of filePaths) {
        blocks.push(makeFileBlock(path));
      }
    } else if (c.type === "tool_use") {
      blocks.push(
        makeToolUseBlock(
          String(c.id ?? ""),
          String(c.name ?? ""),
          (c.input ?? {}) as Record<string, unknown>,
        ),
      );
    }
  }
  return {
    kind: "assistant",
    messageId,
    contentBlocks: blocks,
    parentToolUseId:
      typeof data.parent_tool_use_id === "string"
        ? data.parent_tool_use_id
        : null,
  };
}

// Parse a `user` frame. Returns null for plain-text user echoes (which the
// Python path drops); only tool-result frames produce a message.
function parseUser(
  data: Record<string, unknown>,
  toolUseMap: ToolUseMap,
): ParsedToolResultResponse | null {
  const message = (data.message ?? {}) as Record<string, unknown>;
  const messageContent = message.content;
  if (typeof messageContent === "string") {
    return null;
  }
  if (!Array.isArray(messageContent) || messageContent.length === 0) {
    return null;
  }
  const first = messageContent[0] as Record<string, unknown>;
  if (first.type === "text" || first.type === "document") {
    return null;
  }
  const toolUseId = String(first.tool_use_id ?? "");
  const toolInfo = toolUseMap.get(toolUseId) ?? { name: "unknown", input: {} };
  const toolResultContent = first.content;
  const invocationString = getToolInvocationString(
    toolInfo.name,
    toolInfo.input,
  );
  const isError = first.is_error === true;
  const content = createToolContent(
    toolInfo.name,
    toolInfo.input,
    toolResultContent,
    isError,
  );
  const description =
    typeof toolInfo.input.description === "string"
      ? toolInfo.input.description
      : null;
  const toolUseResult = data.tool_use_result;
  const scheduledWakeupFor =
    typeof toolUseResult === "object" && toolUseResult !== null
      ? asNumberOrNull((toolUseResult as Record<string, unknown>).scheduledFor)
      : null;
  const block = makeToolResultBlock({
    toolUseId,
    toolName: toolInfo.name,
    invocationString,
    content,
    isError,
    description,
  });
  return {
    kind: "tool_result",
    contentBlocks: [block],
    parentToolUseId:
      typeof data.parent_tool_use_id === "string"
        ? data.parent_tool_use_id
        : null,
    scheduledWakeupFor,
    toolUseIds: [toolUseId],
  };
}

function parseEnd(data: Record<string, unknown>): ParsedEndResponse {
  const usage = (data.usage ?? {}) as Record<string, unknown>;
  return {
    kind: "end",
    isError: data.is_error === true,
    result: typeof data.result === "string" ? data.result : "",
    durationMs: asNumberOrNull(data.duration_ms),
    inputTokens: asNumberOrNull(usage.input_tokens),
    outputTokens: asNumberOrNull(usage.output_tokens),
    totalCostUsd: asNumberOrNull(data.total_cost_usd),
    sessionId: typeof data.session_id === "string" ? data.session_id : null,
  };
}

// Discriminated result: a stream event, a parsed response, or null. Throws on
// invalid JSON so the caller can surface a warning (matching the Python path).
export type ParseResult =
  | { event: ParsedStreamEvent }
  | { response: ParsedResponse }
  | null;

export function parseClaudeLine(
  line: string,
  toolUseMap: ToolUseMap,
): ParseResult {
  const cleaned = line.replace(RE_STRIP_ANSI, "").trim();
  if (cleaned === "") {
    return null;
  }
  const data = JSON.parse(cleaned) as unknown;
  if (typeof data !== "object" || data === null) {
    return null;
  }
  const d = data as Record<string, unknown>;

  if (d.type === "stream_event") {
    const event = parseStreamEvent(d);
    return event === null ? null : { event };
  }

  if (d.type === "system") {
    const subtype = d.subtype;
    if (subtype === "init") {
      return {
        response: { kind: "init", sessionId: String(d.session_id ?? "") },
      };
    }
    if (subtype === "task_started") {
      return {
        response: {
          kind: "task_started",
          taskId: String(d.task_id ?? ""),
          toolUseId: String(d.tool_use_id ?? ""),
          description: typeof d.description === "string" ? d.description : "",
          taskType: typeof d.task_type === "string" ? d.task_type : "",
        },
      };
    }
    if (subtype === "task_notification") {
      const usage = (d.usage ?? {}) as Record<string, unknown>;
      const rawDuration = usage.duration_ms;
      return {
        response: {
          kind: "task_notification",
          taskId: String(d.task_id ?? ""),
          toolUseId: String(d.tool_use_id ?? ""),
          status: typeof d.status === "string" ? d.status : "",
          summary: typeof d.summary === "string" ? d.summary : "",
          durationMs:
            typeof rawDuration === "number" ? Math.trunc(rawDuration) : null,
        },
      };
    }
    if (subtype === "task_updated") {
      const patch = (d.patch ?? {}) as Record<string, unknown>;
      return {
        response: {
          kind: "task_updated",
          taskId: String(d.task_id ?? ""),
          status: typeof patch.status === "string" ? patch.status : "",
        },
      };
    }
    return null;
  }

  if (d.type === "assistant") {
    return { response: parseAssistant(d) };
  }
  if (d.type === "user") {
    const parsed = parseUser(d, toolUseMap);
    return parsed === null ? null : { response: parsed };
  }
  if (d.type === "result") {
    return { response: parseEnd(d) };
  }
  return null;
}
