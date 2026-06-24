// Parse the Sculptor sub-agent extension's structured lifecycle payloads, ported
// from `pi_agent/subagent.py`. The pinned `sculptor_subagent` extension's
// `subagent` tool spawns each child as its own pi process and returns
// immediately (the launching turn yields), reporting completion out-of-band via
// a `notify`. START rides the tool result's `details.task`; COMPLETION rides the
// `notify.message` JSON under the marker key.

import {
  type Block,
  getToolInvocationString,
  makeTextBlock,
  makeToolResultBlock,
  makeToolUseBlock,
} from "~/harness/claude/stream_parser";
import { mapPiToolCall } from "~/harness/pi/tool_rendering";

export const SUBAGENT_PAYLOAD_VERSION = 1;
export const SUBAGENT_NOTIFY_MARKER = "sculptorSubagentTask";

export interface SubagentChildEvent {
  seq: number;
  kind: string;
  text: string;
  toolCallId: string;
  toolName: string;
  args: Record<string, unknown>;
  isError: boolean;
}

export interface SubagentChild {
  childId: string;
  label: string;
  task: string;
  status: string;
  stopReason: string | null;
  exitCode: number | null;
  events: SubagentChildEvent[];
}

export interface SubagentStart {
  taskId: string;
  toolCallId: string;
  label: string;
  pgids: number[];
  count: number;
  status: string;
}

export interface SubagentCompletion {
  taskId: string;
  toolCallId: string;
  status: string;
  children: SubagentChild[];
}

function coerceInt(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

function asStr(value: unknown, fallback = ""): string {
  return typeof value === "string" ? value : fallback;
}

function parseEvent(raw: unknown): SubagentChildEvent | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const r = raw as Record<string, unknown>;
  if (
    typeof r.seq !== "number" ||
    !Number.isInteger(r.seq) ||
    typeof r.kind !== "string"
  ) {
    return null;
  }
  return {
    seq: r.seq,
    kind: r.kind,
    text: asStr(r.text),
    toolCallId: asStr(r.toolCallId),
    toolName: asStr(r.toolName),
    args:
      typeof r.args === "object" && r.args !== null
        ? (r.args as Record<string, unknown>)
        : {},
    isError: r.isError === true,
  };
}

function parseChild(raw: unknown): SubagentChild | null {
  if (typeof raw !== "object" || raw === null) {
    return null;
  }
  const r = raw as Record<string, unknown>;
  if (typeof r.childId !== "string" || !r.childId) {
    return null;
  }
  const events: SubagentChildEvent[] = [];
  if (Array.isArray(r.events)) {
    for (const entry of r.events) {
      const event = parseEvent(entry);
      if (event !== null) {
        events.push(event);
      }
    }
  }
  events.sort((a, b) => a.seq - b.seq);
  return {
    childId: r.childId,
    label: typeof r.label === "string" && r.label ? r.label : "subagent",
    task: asStr(r.task),
    status: asStr(r.status, "running"),
    stopReason: typeof r.stopReason === "string" ? r.stopReason : null,
    exitCode: coerceInt(r.exitCode),
    events,
  };
}

function parseChildren(raw: unknown): SubagentChild[] {
  const children: SubagentChild[] = [];
  if (Array.isArray(raw)) {
    for (const entry of raw) {
      const child = parseChild(entry);
      if (child !== null) {
        children.push(child);
      }
    }
  }
  return children;
}

// Parse a `subagent` tool result (`tool_execution_end.result`) into a launch
// snapshot, or null when it carries no version-matched task.
export function parseSubagentStart(payload: unknown): SubagentStart | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const details = (payload as Record<string, unknown>).details;
  if (
    typeof details !== "object" ||
    details === null ||
    (details as Record<string, unknown>).v !== SUBAGENT_PAYLOAD_VERSION
  ) {
    return null;
  }
  const task = (details as Record<string, unknown>).task;
  if (typeof task !== "object" || task === null) {
    return null;
  }
  const t = task as Record<string, unknown>;
  if (
    typeof t.taskId !== "string" ||
    !t.taskId ||
    typeof t.toolCallId !== "string" ||
    !t.toolCallId
  ) {
    return null;
  }
  const pgids = Array.isArray(t.pgids)
    ? t.pgids.map(coerceInt).filter((p): p is number => p !== null && p > 0)
    : [];
  const count = coerceInt(t.count);
  return {
    taskId: t.taskId,
    toolCallId: t.toolCallId,
    label: typeof t.label === "string" && t.label ? t.label : "subagent",
    pgids,
    count: count ?? 0,
    status: asStr(t.status, "running"),
  };
}

// Parse a `notify.message` string into a completion snapshot, or null when it is
// not our sub-agent marker.
export function parseSubagentCompletion(
  message: unknown,
): SubagentCompletion | null {
  if (typeof message !== "string" || !message) {
    return null;
  }
  let decoded: unknown;
  try {
    decoded = JSON.parse(message);
  } catch {
    return null;
  }
  if (typeof decoded !== "object" || decoded === null) {
    return null;
  }
  const payload = (decoded as Record<string, unknown>)[SUBAGENT_NOTIFY_MARKER];
  if (
    typeof payload !== "object" ||
    payload === null ||
    (payload as Record<string, unknown>).v !== SUBAGENT_PAYLOAD_VERSION
  ) {
    return null;
  }
  const p = payload as Record<string, unknown>;
  if (
    typeof p.taskId !== "string" ||
    !p.taskId ||
    typeof p.toolCallId !== "string" ||
    !p.toolCallId ||
    typeof p.status !== "string" ||
    !p.status
  ) {
    return null;
  }
  return {
    taskId: p.taskId,
    toolCallId: p.toolCallId,
    status: p.status,
    children: parseChildren(p.children),
  };
}

function namespacedId(
  parentToolCallId: string,
  childId: string,
  childToolCallId: string,
): string {
  return `${parentToolCallId}:${childId}:${childToolCallId}`;
}

function emptyChildText(child: SubagentChild): string {
  if (child.status === "error") {
    return `Sub-agent ${child.label} failed${child.stopReason ? ` (${child.stopReason})` : ""}.`;
  }
  if (child.status === "running") {
    return `Sub-agent ${child.label} did not finish.`;
  }
  return `Sub-agent ${child.label} produced no output.`;
}

// Render one child's events as interleaved nested blocks (ids namespaced under
// the parent + child). Mirrors `build_child_content_blocks`.
export function buildChildContentBlocks(
  child: SubagentChild,
  parentToolCallId: string,
): Block[] {
  const blocks: Block[] = [];
  for (const event of child.events) {
    if (event.kind === "text") {
      if (event.text) {
        blocks.push(makeTextBlock(event.text));
      }
    } else if (event.kind === "tool_call") {
      const { name, input } = mapPiToolCall(event.toolName, event.args);
      blocks.push(
        makeToolUseBlock(
          namespacedId(parentToolCallId, child.childId, event.toolCallId),
          name,
          input,
        ),
      );
    } else if (event.kind === "tool_result") {
      const { name, input } = mapPiToolCall(event.toolName, event.args);
      blocks.push(
        makeToolResultBlock({
          toolUseId: namespacedId(
            parentToolCallId,
            child.childId,
            event.toolCallId,
          ),
          toolName: name,
          invocationString: getToolInvocationString(name, input),
          content: { content_type: "generic", text: event.text },
          isError: event.isError,
          description: null,
        }),
      );
    }
  }
  if (blocks.length === 0) {
    blocks.push(makeTextBlock(emptyChildText(child)));
  }
  return blocks;
}
