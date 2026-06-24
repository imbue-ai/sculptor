import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import {
  activePanelPerZoneAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneSizesAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import type { PanelId, ZoneId } from "~/components/panels/types.ts";

import { isPanelLayoutPerWorkspaceAtom, userConfigAtom } from "../atoms/userConfig.ts";
import { useUserConfig } from "./useUserConfig.ts";

const DEBOUNCE_MS = 2000;
const LOCAL_STORAGE_KEY = "sculptor-zone-assignments";

type BackendPanelLayout = {
  zoneAssignments?: Record<PanelId, ZoneId>;
  activePanelPerZone?: Partial<Record<ZoneId, PanelId>>;
  zoneVisibility?: Partial<Record<ZoneId, boolean>>;
  zoneSizes?: Partial<Record<ZoneId, number>>;
  zoneOrder?: Partial<Record<ZoneId, Array<PanelId>>>;
};

/**
 * Bidirectionally syncs panel layout between localStorage atoms and the backend config API.
 *
 * Write path: when panel atoms change, debounce for 2s then push to backend.
 * Read path: on first load, if localStorage has no panel data and backend has panelLayout, seed atoms.
 */
export const usePanelLayoutSync = (): void => {
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const activePanelPerZone = useAtomValue(activePanelPerZoneAtom);
  const zoneVisibility = useAtomValue(zoneVisibilityAtom);
  const zoneSizes = useAtomValue(zoneSizesAtom);
  const zoneOrder = useAtomValue(zoneOrderAtom);
  const userConfig = useAtomValue(userConfigAtom);
  const isPerWorkspace = useAtomValue(isPanelLayoutPerWorkspaceAtom);

  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setZoneSizes = useSetAtom(zoneSizesAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);

  const { updateConfig } = useUserConfig();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isInitialRenderRef = useRef(true);
  const hasSeededRef = useRef(false);
  const lastSyncedLayoutRef = useRef<string | null>(null);

  // Keep refs so the write-path effect can read latest values without subscribing
  // to visibility/sizes changes when per-workspace mode is active. Written in an
  // effect (not during render) so the values are read only after commit.
  const zoneVisibilityRef = useRef(zoneVisibility);
  const zoneSizesRef = useRef(zoneSizes);
  const isPerWorkspaceRef = useRef(isPerWorkspace);
  useEffect(() => {
    zoneVisibilityRef.current = zoneVisibility;
    zoneSizesRef.current = zoneSizes;
    isPerWorkspaceRef.current = isPerWorkspace;
  });

  // Read path: seed from backend if localStorage is empty
  useEffect(() => {
    if (hasSeededRef.current || !userConfig) return;
    hasSeededRef.current = true;

    // Check if localStorage already has panel data
    const hasLocalData = localStorage.getItem(LOCAL_STORAGE_KEY) !== null;
    if (hasLocalData) return;

    // Check if backend has panel layout data
    const backendLayout = (userConfig as Record<string, unknown>).panelLayout as BackendPanelLayout | undefined;
    if (!backendLayout || Object.keys(backendLayout.zoneAssignments ?? {}).length === 0) return;

    // Seed atoms from backend data (atomWithStorage will persist to localStorage)
    if (backendLayout.zoneAssignments) setZoneAssignments(backendLayout.zoneAssignments);
    if (backendLayout.activePanelPerZone) setActivePanelPerZone(backendLayout.activePanelPerZone);
    // When per-workspace is active, visibility and sizes are managed locally per workspace
    if (!isPerWorkspace) {
      if (backendLayout.zoneVisibility) setZoneVisibility(backendLayout.zoneVisibility);
      if (backendLayout.zoneSizes) setZoneSizes(backendLayout.zoneSizes);
    }
    if (backendLayout.zoneOrder) setZoneOrder(backendLayout.zoneOrder);
  }, [
    userConfig,
    isPerWorkspace,
    setZoneAssignments,
    setActivePanelPerZone,
    setZoneVisibility,
    setZoneSizes,
    setZoneOrder,
  ]);

  // Write path: debounced sync to backend.
  // When per-workspace is active, visibility/sizes are excluded from the synced
  // payload but still appear in the dependency array (unavoidable since hooks
  // subscribe unconditionally). Refs are used inside the timeout so the payload
  // always reflects the latest values at fire time.
  useEffect(() => {
    // Skip the initial render to avoid writing back localStorage data immediately
    if (isInitialRenderRef.current) {
      isInitialRenderRef.current = false;
      return;
    }

    // Don't sync if there are no assignments (empty state)
    if (Object.keys(zoneAssignments).length === 0) return;

    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    timerRef.current = setTimeout(() => {
      // When per-workspace is active, only sync positions (not visibility/sizes)
      const layout = isPerWorkspaceRef.current
        ? {
            zoneAssignments,
            activePanelPerZone,
            zoneOrder,
          }
        : {
            zoneAssignments,
            activePanelPerZone,
            zoneVisibility: zoneVisibilityRef.current,
            zoneSizes: zoneSizesRef.current,
            zoneOrder,
          };
      const serialized = JSON.stringify(layout);
      if (serialized === lastSyncedLayoutRef.current) return;

      lastSyncedLayoutRef.current = serialized;
      updateConfig({ panelLayout: layout } as Record<string, unknown>).catch((error: unknown) => {
        lastSyncedLayoutRef.current = null;
        console.error("Failed to sync panel layout to backend:", error);
      });
    }, DEBOUNCE_MS);

    return (): void => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [zoneAssignments, activePanelPerZone, zoneVisibility, zoneSizes, zoneOrder, isPerWorkspace, updateConfig]);
};
