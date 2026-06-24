import { eventBus } from "~/events";

// UI-action publishing (web/ui_actions.py). These actions succeed by emitting a
// stream event the frontend reacts to (the ui_open_file_by_workspace_id /
// ui_webview_command_by_workspace_id StreamingUpdate fields), not by returning
// data. Payloads are built snake_case (internal); the projection's to_wire
// boundary camelCases them.

// Per-workspace monotonically-increasing sequence for webview commands so the
// frontend can drop out-of-order deliveries (ui_actions.py next_webview_seq).
const webviewSeqByWorkspace = new Map<string, number>();

export function nextWebviewSeq(workspaceId: string): number {
  const seq = (webviewSeqByWorkspace.get(workspaceId) ?? 0) + 1;
  webviewSeqByWorkspace.set(workspaceId, seq);
  return seq;
}

export type OpenFileMode = "auto" | "diff" | "file";

export function publishOpenFile(
  workspaceId: string,
  filePath: string,
  mode: OpenFileMode,
): void {
  eventBus.publish({
    kind: "ui_open_file",
    workspaceId,
    action: { workspace_id: workspaceId, file_path: filePath, mode },
  });
}

export function publishWebviewCommand(
  workspaceId: string,
  kind: "navigate" | "refresh",
  url: string | null,
): void {
  eventBus.publish({
    kind: "ui_webview_command",
    workspaceId,
    command: {
      workspace_id: workspaceId,
      seq: nextWebviewSeq(workspaceId),
      kind,
      url,
    },
  });
}
