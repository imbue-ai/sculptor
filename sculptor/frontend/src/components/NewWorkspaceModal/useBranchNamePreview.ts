import { useCallback, useEffect, useRef, useState } from "react";

import type { WorkspaceInitializationStrategy } from "~/api";
import { branchExists, previewBranchName, WorkspaceInitializationStrategy as Strategy } from "~/api";

export type BranchNameCollisionState = "unknown" | "exists" | "available";

type BranchNamePreviewState = {
  /** The auto-filled value sourced from the backend `preview-branch-name` endpoint. */
  preview: string;
  /** The value the user actually sees: `override` if set, otherwise `preview`. */
  displayedValue: string;
  /** True while the preview fetch is in flight in auto mode. */
  isLoading: boolean;
  /** Result of the debounced `branch-exists` check on `displayedValue`. */
  collision: BranchNameCollisionState;
  /**
   * Re-fetch a fresh auto-filled name. Useful as a "shuffle" affordance —
   * if the user is already in auto mode, the preview effect's normal
   * deps don't change, so this nonce-bump is what forces a new fetch.
   */
  shuffle: () => void;
};

type UseBranchNamePreviewArgs = {
  projectId: string | null;
  workspaceName: string;
  mode: WorkspaceInitializationStrategy;
  /** The user's manual override; null means "use the auto-filled preview". */
  override: string | null;
};

const PREVIEW_DEBOUNCE_MS = 250;
const COLLISION_DEBOUNCE_MS = 300;

export function useBranchNamePreview({
  projectId,
  workspaceName,
  mode,
  override,
}: UseBranchNamePreviewArgs): BranchNamePreviewState {
  const [preview, setPreview] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [collision, setCollision] = useState<BranchNameCollisionState>("unknown");
  // Bumped by `shuffle()` to force the auto-fill effect to re-run
  // even when no other dep changed (e.g. user clicks shuffle while
  // already in auto mode with the same workspace name).
  const [shuffleNonce, setShuffleNonce] = useState<number>(0);

  const previewRequestId = useRef<number>(0);
  const collisionRequestId = useRef<number>(0);

  const isManuallyEdited = override !== null;
  const displayedValue = override ?? preview;

  const shuffle = useCallback((): void => {
    setShuffleNonce((n) => n + 1);
  }, []);

  useEffect(() => {
    if (mode === Strategy.IN_PLACE || !projectId || isManuallyEdited) {
      setIsLoading(false);
      return;
    }
    const myId = ++previewRequestId.current;
    setIsLoading(true);
    const timer = window.setTimeout(() => {
      void (async (): Promise<void> => {
        try {
          const result = await previewBranchName({
            query: { project_id: projectId, workspace_name: workspaceName, mode },
          });
          if (myId === previewRequestId.current && result.data) {
            setPreview(result.data.branchName);
          }
        } catch {
          // keep previous preview
        } finally {
          if (myId === previewRequestId.current) {
            setIsLoading(false);
          }
        }
      })();
    }, PREVIEW_DEBOUNCE_MS);
    return (): void => {
      window.clearTimeout(timer);
    };
  }, [projectId, workspaceName, mode, isManuallyEdited, shuffleNonce]);

  useEffect(() => {
    if (mode === Strategy.IN_PLACE || !projectId) {
      setCollision("unknown");
      return;
    }
    const trimmed = displayedValue.trim();
    if (!trimmed) {
      setCollision("unknown");
      return;
    }
    const myId = ++collisionRequestId.current;
    const timer = window.setTimeout(() => {
      void (async (): Promise<void> => {
        try {
          const result = await branchExists({
            path: { project_id: projectId },
            query: { name: trimmed },
          });
          if (myId === collisionRequestId.current && result.data) {
            setCollision(result.data.exists ? "exists" : "available");
          }
        } catch {
          if (myId === collisionRequestId.current) {
            setCollision("unknown");
          }
        }
      })();
    }, COLLISION_DEBOUNCE_MS);
    return (): void => {
      window.clearTimeout(timer);
    };
  }, [projectId, displayedValue, mode]);

  return { preview, displayedValue, isLoading, collision, shuffle };
}
