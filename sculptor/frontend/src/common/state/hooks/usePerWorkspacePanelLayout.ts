import { useAtomValue, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

import {
  activePanelPerZoneAtom,
  activeWorkspaceIdAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneSizesAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import {
  type SectionSizeKey,
  sectionSizePercentAtom,
  sectionSizesSharedAtom,
  type SectionSplit,
  sectionSplitAtom,
} from "~/components/panels/sectionLayoutAtoms.ts";
import type { DefaultPanelLayout, PanelId, ZoneId } from "~/components/panels/types.ts";
import { diffPanelOpenAtom, diffPanelSplitRatioAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";

// Panel layout is per-workspace (REQ-PERSIST-1). The full layout — panel
// positions (assignments / order / active panel), section visibility, and
// section split state — is snapshotted to localStorage keyed by workspace id and
// restored on workspace switch. There is no cross-workspace sharing and no
// backend sync: when a workspace has no saved layout, we fall back to the
// default layout (REQ-DEFAULT-1) and let `useWorkspaceLayoutBootstrap` place the
// per-workspace dynamic panels (the active agent, the terminal).
//
// Section SIZES are handled separately (see `sectionSizePercentAtom`): they are
// global/shared by default with an experimental toggle to make them per-workspace.
const ASSIGNMENTS_KEY_PREFIX = "sculptor-zone-assignments-ws-";
const ORDER_KEY_PREFIX = "sculptor-zone-order-ws-";
const ACTIVE_KEY_PREFIX = "sculptor-active-panel-per-zone-ws-";
const VISIBILITY_KEY_PREFIX = "sculptor-zone-visibility-ws-";
const SPLIT_KEY_PREFIX = "sculptor-section-split-ws-";
const SIZES_KEY_PREFIX = "sculptor-zone-sizes-ws-";
const SECTION_SIZE_PERCENT_KEY_PREFIX = "sculptor-section-size-percent-ws-";
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
 * Restores a workspace's saved panel layout, or — on a workspace's first visit
 * (no saved layout) — resets the layout atoms to the default so the previous
 * workspace's layout does not leak in. Dynamic panels (the active agent, the
 * terminal) are placed afterward by `useWorkspaceLayoutBootstrap`.
 *
 * Must be called inside WorkspacePageContent where `workspaceId` is known.
 */
export const usePerWorkspacePanelLayout = (workspaceId: string, defaultLayout: DefaultPanelLayout): void => {
  const setActiveWorkspaceId = useSetAtom(activeWorkspaceIdAtom);

  const assignments = useAtomValue(zoneAssignmentsAtom);
  const order = useAtomValue(zoneOrderAtom);
  const active = useAtomValue(activePanelPerZoneAtom);
  const visibility = useAtomValue(zoneVisibilityAtom);
  const split = useAtomValue(sectionSplitAtom);
  const sizes = useAtomValue(zoneSizesAtom);
  const sectionSizePercent = useAtomValue(sectionSizePercentAtom);
  const areSectionSizesShared = useAtomValue(sectionSizesSharedAtom);
  const isDiffPanelOpen = useAtomValue(diffPanelOpenAtom);
  const diffPanelSplitRatio = useAtomValue(diffPanelSplitRatioAtom);

  const setAssignments = useSetAtom(zoneAssignmentsAtom);
  const setOrder = useSetAtom(zoneOrderAtom);
  const setActive = useSetAtom(activePanelPerZoneAtom);
  const setVisibility = useSetAtom(zoneVisibilityAtom);
  const setSplit = useSetAtom(sectionSplitAtom);
  const setSizes = useSetAtom(zoneSizesAtom);
  const setSectionSizePercent = useSetAtom(sectionSizePercentAtom);
  const setDiffPanelOpen = useSetAtom(diffPanelOpenAtom);
  const setDiffPanelSplitRatio = useSetAtom(diffPanelSplitRatioAtom);

  // Latest-value refs so the workspace-switch effect saves current values
  // without re-subscribing.
  const stateRef = useRef({
    assignments,
    order,
    active,
    visibility,
    split,
    sizes,
    sectionSizePercent,
    sectionSizesShared: areSectionSizesShared,
    isDiffPanelOpen,
    diffPanelSplitRatio,
  });
  stateRef.current = {
    assignments,
    order,
    active,
    visibility,
    split,
    sizes,
    sectionSizePercent,
    sectionSizesShared: areSectionSizesShared,
    isDiffPanelOpen,
    diffPanelSplitRatio,
  };

  const isInitialRef = useRef(true);
  const prevWorkspaceIdRef = useRef<string | null>(null);
  // The workspace whose layout is currently loaded into the atoms. The
  // save-on-change effects gate on this so they never persist the previous
  // workspace's values under the new workspace's key during a switch.
  const loadedWorkspaceIdRef = useRef<string | null>(null);

  const defaultLayoutRef = useRef(defaultLayout);
  defaultLayoutRef.current = defaultLayout;

  // Track the active workspace ID for atoms that need it.
  useEffect(() => {
    setActiveWorkspaceId(workspaceId);
    return (): void => {
      setActiveWorkspaceId(null);
    };
  }, [workspaceId, setActiveWorkspaceId]);

  // Save / restore on first mount and on every workspace switch.
  useEffect(() => {
    const persist = (id: string): void => {
      const s = stateRef.current;
      saveToLocalStorage(ASSIGNMENTS_KEY_PREFIX + id, s.assignments);
      saveToLocalStorage(ORDER_KEY_PREFIX + id, s.order);
      saveToLocalStorage(ACTIVE_KEY_PREFIX + id, s.active);
      saveToLocalStorage(VISIBILITY_KEY_PREFIX + id, s.visibility);
      saveToLocalStorage(SPLIT_KEY_PREFIX + id, s.split);
      saveToLocalStorage(SIZES_KEY_PREFIX + id, s.sizes);
      saveToLocalStorage(DIFF_PANEL_OPEN_KEY_PREFIX + id, s.isDiffPanelOpen);
      saveToLocalStorage(DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX + id, s.diffPanelSplitRatio);
      // Section sizes are per-workspace only when sharing is disabled; otherwise
      // they live in their own global storage key and are left untouched here.
      if (!s.sectionSizesShared) {
        saveToLocalStorage(SECTION_SIZE_PERCENT_KEY_PREFIX + id, s.sectionSizePercent);
      }
    };

    const restoreOrReset = (id: string): void => {
      const savedAssignments = loadFromLocalStorage<Record<PanelId, ZoneId>>(ASSIGNMENTS_KEY_PREFIX + id);
      if (savedAssignments !== undefined) {
        // Restore this workspace's saved layout. Every atom is set so the
        // save-on-change effects re-persist the freshly-loaded (correct) values
        // after the switch, overwriting any transient pre-switch save.
        setAssignments(savedAssignments);
        setOrder(loadFromLocalStorage<Partial<Record<ZoneId, Array<PanelId>>>>(ORDER_KEY_PREFIX + id) ?? {});
        setActive(loadFromLocalStorage<Partial<Record<ZoneId, PanelId>>>(ACTIVE_KEY_PREFIX + id) ?? {});
        setVisibility(loadFromLocalStorage<Partial<Record<ZoneId, boolean>>>(VISIBILITY_KEY_PREFIX + id) ?? {});
        setSplit(loadFromLocalStorage<Partial<Record<ZoneId, SectionSplit>>>(SPLIT_KEY_PREFIX + id) ?? {});
        setSizes(loadFromLocalStorage<Partial<Record<ZoneId, number>>>(SIZES_KEY_PREFIX + id) ?? {});
        const isSavedDiffPanelOpen = loadFromLocalStorage<boolean>(DIFF_PANEL_OPEN_KEY_PREFIX + id);
        if (isSavedDiffPanelOpen !== undefined) setDiffPanelOpen(isSavedDiffPanelOpen);
        const savedDiffRatio = loadFromLocalStorage<number>(DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX + id);
        if (savedDiffRatio !== undefined) setDiffPanelSplitRatio(savedDiffRatio);
      } else {
        // First visit — fall back to the default layout. Dynamic panels (agent,
        // terminal) are placed by useWorkspaceLayoutBootstrap after this.
        const fallback = defaultLayoutRef.current;
        setAssignments(fallback.zoneAssignments);
        setOrder(fallback.zoneOrder ?? {});
        setActive(fallback.activePanelPerZone);
        setVisibility(fallback.zoneVisibility);
        setSplit({});
      }

      // Section sizes: only restore per-workspace when sharing is disabled. When
      // shared, the global sectionSizePercentAtom value is kept as-is.
      if (!stateRef.current.sectionSizesShared) {
        const savedSizePercent = loadFromLocalStorage<Partial<Record<SectionSizeKey, number>>>(
          SECTION_SIZE_PERCENT_KEY_PREFIX + id,
        );
        if (savedSizePercent !== undefined) setSectionSizePercent(savedSizePercent);
      }
      loadedWorkspaceIdRef.current = id;
    };

    if (isInitialRef.current) {
      isInitialRef.current = false;
      prevWorkspaceIdRef.current = workspaceId;
      restoreOrReset(workspaceId);
      return;
    }

    if (prevWorkspaceIdRef.current === workspaceId) return;

    if (prevWorkspaceIdRef.current !== null) {
      persist(prevWorkspaceIdRef.current);
    }
    prevWorkspaceIdRef.current = workspaceId;
    restoreOrReset(workspaceId);
  }, [
    workspaceId,
    setAssignments,
    setOrder,
    setActive,
    setVisibility,
    setSplit,
    setSizes,
    setSectionSizePercent,
    setDiffPanelOpen,
    setDiffPanelSplitRatio,
  ]);

  // Persist current state on change — but only once this workspace's layout is
  // the one loaded into the atoms (guards against saving the outgoing
  // workspace's values under the incoming key mid-switch).
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(ASSIGNMENTS_KEY_PREFIX + workspaceId, assignments);
  }, [workspaceId, assignments]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(ORDER_KEY_PREFIX + workspaceId, order);
  }, [workspaceId, order]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(ACTIVE_KEY_PREFIX + workspaceId, active);
  }, [workspaceId, active]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(VISIBILITY_KEY_PREFIX + workspaceId, visibility);
  }, [workspaceId, visibility]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(SPLIT_KEY_PREFIX + workspaceId, split);
  }, [workspaceId, split]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(SIZES_KEY_PREFIX + workspaceId, sizes);
  }, [workspaceId, sizes]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId || areSectionSizesShared) return;
    saveToLocalStorage(SECTION_SIZE_PERCENT_KEY_PREFIX + workspaceId, sectionSizePercent);
  }, [workspaceId, sectionSizePercent, areSectionSizesShared]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(DIFF_PANEL_OPEN_KEY_PREFIX + workspaceId, isDiffPanelOpen);
  }, [workspaceId, isDiffPanelOpen]);
  useEffect(() => {
    if (loadedWorkspaceIdRef.current !== workspaceId) return;
    saveToLocalStorage(DIFF_PANEL_SPLIT_RATIO_KEY_PREFIX + workspaceId, diffPanelSplitRatio);
  }, [workspaceId, diffPanelSplitRatio]);
};
