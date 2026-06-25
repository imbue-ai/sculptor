import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import { activeWorkspaceIdAtom, zoneSizesAtom, zoneVisibilityAtom } from "~/components/panels/atoms.ts";
import type { ZoneId } from "~/components/panels/types.ts";
import { diffPanelOpenAtom, diffPanelSplitRatioAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";

import { isPanelLayoutPerWorkspaceAtom } from "../atoms/userConfig.ts";

const VISIBILITY_KEY_PREFIX = "sculptor-zone-visibility-ws-";
const SIZES_KEY_PREFIX = "sculptor-zone-sizes-ws-";
const DIFF_PANEL_OPEN_KEY_PREFIX = "sculptor-diffPanel-open-ws-";
const DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX = "sculptor-diffPanel-splitRatio-ws-";

const saveToLocalStorage = (key: string, value: unknown): void => {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Quota exceeded or storage unavailable — best-effort
  }
};

const loadFromLocalStorage = <T>(key: string): T | undefined => {
  try {
    const stored = localStorage.getItem(key);
    return stored !== null ? (JSON.parse(stored) as T) : undefined;
  } catch {
    return undefined;
  }
};

/**
 * When per-workspace panel layout is enabled, saves and restores
 * zone visibility, sizes, and the diff panel's open/size state on
 * workspace switch.
 *
 * Panel positions (zone assignments, active panel, order) remain shared.
 *
 * Must be called inside WorkspacePageContent where `workspaceId` is known.
 */
export const usePerWorkspacePanelLayout = (workspaceId: string): void => {
  const isPerWorkspace = useAtomValue(isPanelLayoutPerWorkspaceAtom);
  const setActiveWorkspaceId = useSetAtom(activeWorkspaceIdAtom);

  const zoneVisibility = useAtomValue(zoneVisibilityAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const zoneSizes = useAtomValue(zoneSizesAtom);
  const setZoneSizes = useSetAtom(zoneSizesAtom);
  const isDiffPanelOpen = useAtomValue(diffPanelOpenAtom);
  const setDiffPanelOpen = useSetAtom(diffPanelOpenAtom);
  const diffPanelSplitRatio = useAtomValue(diffPanelSplitRatioAtom);
  const setDiffPanelSplitRatio = useSetAtom(diffPanelSplitRatioAtom);

  const prevWorkspaceIdRef = useRef<string | null>(null);
  const isInitialRef = useRef(true);

  // Keep refs in sync so the workspace-switch effect always saves current values.
  // Written in an effect (not during render) so reads in the switch effect see
  // the committed values without touching refs in the render body.
  const zoneVisibilityRef = useRef(zoneVisibility);
  const zoneSizesRef = useRef(zoneSizes);
  const isDiffPanelOpenRef = useRef(isDiffPanelOpen);
  const diffPanelSplitRatioRef = useRef(diffPanelSplitRatio);
  useEffect(() => {
    zoneVisibilityRef.current = zoneVisibility;
    zoneSizesRef.current = zoneSizes;
    isDiffPanelOpenRef.current = isDiffPanelOpen;
    diffPanelSplitRatioRef.current = diffPanelSplitRatio;
  });

  // Always track the active workspace ID
  useEffect(() => {
    setActiveWorkspaceId(workspaceId);
    return (): void => {
      setActiveWorkspaceId(null);
    };
  }, [workspaceId, setActiveWorkspaceId]);

  // Save/restore on workspace switch when per-workspace mode is enabled.
  // State machine: isInitialRef gates first-mount vs subsequent switches,
  // prevWorkspaceIdRef tracks the previous workspace for save-on-switch.
  useEffect(() => {
    if (!isPerWorkspace) {
      prevWorkspaceIdRef.current = null;
      isInitialRef.current = true;
      return;
    }

    const prevId = prevWorkspaceIdRef.current;
    const isInitial = isInitialRef.current;

    // After the first mount, re-runs for the same workspace have nothing to do.
    if (!isInitial && prevId === workspaceId) return;

    if (isInitial) {
      isInitialRef.current = false;
    } else if (prevId !== null) {
      // Switching workspaces: save the outgoing workspace's current state
      // (read from refs to avoid a stale closure) before loading the new one.
      saveToLocalStorage(VISIBILITY_KEY_PREFIX + prevId, zoneVisibilityRef.current);
      saveToLocalStorage(SIZES_KEY_PREFIX + prevId, zoneSizesRef.current);
      saveToLocalStorage(DIFF_PANEL_OPEN_KEY_PREFIX + prevId, isDiffPanelOpenRef.current);
      saveToLocalStorage(DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX + prevId, diffPanelSplitRatioRef.current);
    }

    prevWorkspaceIdRef.current = workspaceId;

    // Load and apply this workspace's saved state, if any. Shared by both the
    // first mount and subsequent workspace switches.
    const savedVisibility = loadFromLocalStorage<Partial<Record<ZoneId, boolean>>>(VISIBILITY_KEY_PREFIX + workspaceId);
    const savedSizes = loadFromLocalStorage<Partial<Record<ZoneId, number>>>(SIZES_KEY_PREFIX + workspaceId);
    const isSavedDiffPanelOpen = loadFromLocalStorage<boolean>(DIFF_PANEL_OPEN_KEY_PREFIX + workspaceId);
    const savedDiffSplitRatio = loadFromLocalStorage<number>(DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX + workspaceId);

    if (savedVisibility !== undefined) {
      setZoneVisibility(savedVisibility);
    }

    if (savedSizes !== undefined) {
      setZoneSizes(savedSizes);
    }

    if (isSavedDiffPanelOpen !== undefined) {
      setDiffPanelOpen(isSavedDiffPanelOpen);
    }

    if (savedDiffSplitRatio !== undefined) {
      setDiffPanelSplitRatio(savedDiffSplitRatio);
    }
  }, [workspaceId, isPerWorkspace, setZoneVisibility, setZoneSizes, setDiffPanelOpen, setDiffPanelSplitRatio]);

  // Persist current state whenever visibility or sizes change (while per-workspace is active)
  useEffect(() => {
    if (!isPerWorkspace || isInitialRef.current) return;
    saveToLocalStorage(VISIBILITY_KEY_PREFIX + workspaceId, zoneVisibility);
  }, [isPerWorkspace, workspaceId, zoneVisibility]);

  useEffect(() => {
    if (!isPerWorkspace || isInitialRef.current) return;
    saveToLocalStorage(SIZES_KEY_PREFIX + workspaceId, zoneSizes);
  }, [isPerWorkspace, workspaceId, zoneSizes]);

  useEffect(() => {
    if (!isPerWorkspace || isInitialRef.current) return;
    saveToLocalStorage(DIFF_PANEL_OPEN_KEY_PREFIX + workspaceId, isDiffPanelOpen);
  }, [isPerWorkspace, workspaceId, isDiffPanelOpen]);

  useEffect(() => {
    if (!isPerWorkspace || isInitialRef.current) return;
    saveToLocalStorage(DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX + workspaceId, diffPanelSplitRatio);
  }, [isPerWorkspace, workspaceId, diffPanelSplitRatio]);
};
