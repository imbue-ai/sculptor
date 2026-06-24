// Parse the Sculptor background-task extension's lifecycle payloads, ported from
// `pi_agent/background.py`. The pinned `sculptor_background` extension's
// `background` tool starts a shell command and returns immediately (the
// launching turn yields), reporting completion out-of-band via a `notify`.

export const BACKGROUND_PAYLOAD_VERSION = 1;
export const BACKGROUND_NOTIFY_MARKER = "sculptorBackgroundTask";

export interface BackgroundTaskStart {
  taskId: string;
  toolCallId: string;
  label: string;
  command: string;
  pgid: number;
  status: string;
}

export interface BackgroundTaskCompletion {
  taskId: string;
  toolCallId: string;
  status: string;
  exitCode: number | null;
  summary: string;
  durationMs: number | null;
}

function coerceInt(value: unknown): number | null {
  return typeof value === "number" && Number.isInteger(value) ? value : null;
}

// Parse a `background` tool result (`tool_execution_end.result`) into a launch
// snapshot, or null when it carries no version-matched task.
export function parseBackgroundStart(
  payload: unknown,
): BackgroundTaskStart | null {
  if (typeof payload !== "object" || payload === null) {
    return null;
  }
  const details = (payload as Record<string, unknown>).details;
  if (
    typeof details !== "object" ||
    details === null ||
    (details as Record<string, unknown>).v !== BACKGROUND_PAYLOAD_VERSION
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
  const pgid = coerceInt(t.pgid);
  return {
    taskId: t.taskId,
    toolCallId: t.toolCallId,
    label: typeof t.label === "string" && t.label ? t.label : "background",
    command: typeof t.command === "string" ? t.command : "",
    pgid: pgid ?? -1,
    status: typeof t.status === "string" ? t.status : "running",
  };
}

// Parse a `notify.message` string into a completion snapshot, or null when it is
// not our background marker.
export function parseBackgroundCompletion(
  message: unknown,
): BackgroundTaskCompletion | null {
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
  const payload = (decoded as Record<string, unknown>)[
    BACKGROUND_NOTIFY_MARKER
  ];
  if (
    typeof payload !== "object" ||
    payload === null ||
    (payload as Record<string, unknown>).v !== BACKGROUND_PAYLOAD_VERSION
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
    exitCode: coerceInt(p.exitCode),
    summary: typeof p.summary === "string" ? p.summary : "",
    durationMs: coerceInt(p.durationMs),
  };
}

// The assistant text surfaced when a background task finishes (mirrors
// `_format_background_completion`).
export function formatBackgroundCompletion(
  completion: BackgroundTaskCompletion,
): string {
  const verb =
    completion.status === "completed" ? "completed" : completion.status;
  const exitNote =
    completion.exitCode === null ? "" : ` (exit code ${completion.exitCode})`;
  const header = `Background task ${verb}${exitNote}.`;
  const summary = completion.summary.trim();
  return summary ? `${header}\n\n${summary}` : header;
}
