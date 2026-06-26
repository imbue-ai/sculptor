import { useEffect, useRef, useState } from "react";

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
};

type UseBranchNamePreviewArgs = {
  projectId: string | null;
  workspaceName: string;
  mode: WorkspaceInitializationStrategy;
  /** The user's manual override; null means "use the auto-filled preview". */
  override: string | null;
  /**
   * Bumping this re-runs the preview fetch even when nothing else changed, so a
   * "regenerate" control can pull a fresh auto-generated name. Defaults to 0.
   */
  regenerationNonce?: number;
};

const PREVIEW_DEBOUNCE_MS = 250;
const COLLISION_DEBOUNCE_MS = 300;

export function useBranchNamePreview({
  projectId,
  workspaceName,
  mode,
  override,
  regenerationNonce = 0,
}: UseBranchNamePreviewArgs): BranchNamePreviewState {
  const [preview, setPreview] = useState<string>("");
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [collision, setCollision] = useState<BranchNameCollisionState>("unknown");

  const previewRequestId = useRef<number>(0);
  const collisionRequestId = useRef<number>(0);

  const isManuallyEdited = override !== null;
  const displayedValue = override ?? preview;

  // The preview only fetches in auto mode for a non-in-place strategy with a
  // project; otherwise there is nothing in flight, so loading is forced false
  // during render rather than reset via a synchronous setState in the effect.
  const shouldFetchPreview = mode !== Strategy.IN_PLACE && Boolean(projectId) && !isManuallyEdited;
  if (!shouldFetchPreview && isLoading) {
    setIsLoading(false);
  }

  useEffect(() => {
    if (!shouldFetchPreview || projectId === null) {
      return;
    }
    const myId = ++previewRequestId.current;
    // Show the spinner immediately when a debounced fetch is queued; the async
    // finally clears it. This is the start signal of external async work, not a
    // value derivable during render.
    // eslint-disable-next-line react-hooks/set-state-in-effect
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
  }, [projectId, workspaceName, mode, shouldFetchPreview, regenerationNonce]);

  // A collision check only runs for a non-in-place strategy with a project and a
  // non-empty branch name; otherwise there is no result to report, so collision is
  // forced "unknown" during render rather than reset by a synchronous setState.
  const trimmedBranchName = displayedValue.trim();
  const shouldCheckCollision = mode !== Strategy.IN_PLACE && Boolean(projectId) && trimmedBranchName !== "";
  if (!shouldCheckCollision && collision !== "unknown") {
    setCollision("unknown");
  }

  useEffect(() => {
    if (!shouldCheckCollision || projectId === null) {
      return;
    }
    const myId = ++collisionRequestId.current;
    const timer = window.setTimeout(() => {
      void (async (): Promise<void> => {
        try {
          const result = await branchExists({
            path: { project_id: projectId },
            query: { name: trimmedBranchName },
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
  }, [projectId, trimmedBranchName, shouldCheckCollision]);

  return { preview, displayedValue, isLoading, collision };
}
