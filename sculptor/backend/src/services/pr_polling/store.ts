import type { StreamingUpdate } from "~/projection/streaming_update_types";
import type { PrStatusInfo } from "~/services/pr_polling/status";

type WirePrStatus = StreamingUpdate["pr_status_by_workspace_id"][string];

// Latest PR/CI status per workspace, as last produced by the poller. The poll
// publishes a live `pr_status` event (→ delta), but a freshly-connected or
// navigated client needs the current value in its initial snapshot too —
// otherwise the PR badge/button is blank until the next poll fires. This is the
// snapshot-side mirror of pr_status_by_workspace_id (web keeps the same map).

const latestPrStatus = new Map<string, PrStatusInfo | null>();

export function setPrStatus(
  workspaceId: string,
  status: PrStatusInfo | null,
): void {
  latestPrStatus.set(workspaceId, status);
}

export function clearPrStatus(workspaceId: string): void {
  latestPrStatus.delete(workspaceId);
}

export function getPrStatusByWorkspaceId(): Record<
  string,
  WirePrStatus | null
> {
  return Object.fromEntries(latestPrStatus) as Record<
    string,
    WirePrStatus | null
  >;
}

export function resetPrStatusStoreForTests(): void {
  latestPrStatus.clear();
}
