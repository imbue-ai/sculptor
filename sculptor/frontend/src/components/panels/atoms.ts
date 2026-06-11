import type { Atom } from "jotai";
import { atom, createStore } from "jotai";
import { atomFamily, atomWithStorage, selectAtom } from "jotai/utils";

import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import type { KeybindingId } from "~/common/keybindings/types.ts";
import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";
import type { LayoutSide, PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { LAYOUT_SIDES, SIDE_ZONE_MAP, ZONE_IDS } from "~/components/panels/types.ts";
import { areArraysShallowEqual } from "~/components/panels/utils.ts";

// ── Panel registry atom ─────────────────────────────────────────────
// Writable atom holding the current set of registered panels.
// Starts empty; set via PanelRegistryProvider (React) or
// createPanelStore (tests / programmatic).
export const panelRegistryAtom = atom<ReadonlyArray<PanelDefinition>>([]);

// ── Primary atoms with localStorage persistence ──────────────────────
// Debounced: a single drag-and-drop move updates all four move-related
// atoms in the same frame. Synchronous localStorage writes would stack up on
// the drop frame and produce visible lag — debouncing keeps in-memory state
// immediate and coalesces the JSON-serialized writes to localStorage.

export const zoneAssignmentsAtom = atomWithDebouncedStorage<Record<PanelId, ZoneId>>(
  "sculptor-zone-assignments",
  {},
  200,
);

export const activePanelPerZoneAtom = atomWithDebouncedStorage<Partial<Record<ZoneId, PanelId>>>(
  "sculptor-active-panel-per-zone",
  {},
  200,
);

export const zoneVisibilityAtom = atomWithDebouncedStorage<Partial<Record<ZoneId, boolean>>>(
  "sculptor-zone-visibility",
  {},
  200,
);

export const zoneSizesAtom = atomWithDebouncedStorage<Partial<Record<ZoneId, number>>>("sculptor-zone-sizes", {}, 200);

export const zoneOrderAtom = atomWithDebouncedStorage<Partial<Record<ZoneId, Array<PanelId>>>>(
  "sculptor-zone-order",
  {},
  200,
);

export const panelEnabledAtom = atomWithStorage<Record<PanelId, boolean>>("sculptor-panel-enabled", {}, undefined, {
  getOnInit: true,
});

// ── Focus mode atoms (persisted) ─────────────────────────────────────

export const focusModeActiveAtom = atomWithStorage<boolean>("sculptor-focus-mode-active", false, undefined, {
  getOnInit: true,
});

export const focusModeSavedVisibilityAtom = atomWithStorage<Partial<Record<ZoneId, boolean>>>(
  "sculptor-focus-mode-saved-visibility",
  {},
  undefined,
  { getOnInit: true },
);

// ── Zen mode atoms (persisted) ───────────────────────────────────────

export const zenModeActiveAtom = atomWithStorage<boolean>("sculptor-zen-mode-active", false, undefined, {
  getOnInit: true,
});

// Tracks whether zen mode itself activated focus mode, so zen exit
// knows whether to also deactivate focus mode.
export const didZenImplyFocusModeAtom = atomWithStorage<boolean>("sculptor-zen-mode-implied-focus", false, undefined, {
  getOnInit: true,
});

// ── Non-persisted atoms ──────────────────────────────────────────────

// Tracks the currently active workspace ID for per-workspace panel layout.
// Set by WorkspacePageContent on mount/navigation; null when not viewing a workspace.
export const activeWorkspaceIdAtom = atom<string | null>(null);

// Modal state atom — NOT persisted (resets on reload)
export const modalPanelIdAtom = atom<PanelId | null>(null);

// The section (zone) that currently holds user focus, or null until the user
// first focuses a pane. Starts null so a fresh load shows no focus ring — the
// indicator only appears once the user clicks into or keyboard-navigates to a
// pane (it is intentionally NOT set by programmatic mount auto-focus). Drives
// the subtle active-pane ring and is the origin for Ctrl+Alt+Arrow pane nav.
// Non-persisted: focus is transient and should reset on reload.
export const focusedZoneAtom = atom<ZoneId | null>(null);

// Tracks whether a chat panel (real or skeleton) is currently mounted.
// Chat-panel components flip this to `true` on mount and `false` on unmount,
// giving the rest of the app a reactive, DOM-free signal that can be read
// from React render paths (e.g. the command palette's visibility filter).
export const chatPanelMountedAtom = atom<boolean>(false);

// Same pattern for the terminal panel — flipped by `TerminalPanelContent` so
// commands like "Clear terminal" can gate their visibility on whether there's
// a terminal to act on at all.
export const terminalPanelMountedAtom = atom<boolean>(false);

// ── Panel-to-keybinding mapping ─────────────────────────────────────
// Synthetic keybinding ID for a panel; used as the key into
// `userConfig.keybindings` for per-panel shortcuts.
export const panelKeybindingId = (panelId: PanelId): KeybindingId => `panel_${panelId}`;

// ── Enabled-state helpers ───────────────────────────────────────────
// ── Shortcuts (derived from the keybinding registry) ────────────────
// Read-only map of panel id → bound shortcut string, sourced from
// `keybindingsMapAtom` via `panel_<id>` keys. Disabled panels and
// panels with empty/null bindings are omitted entirely.

export const panelShortcutsAtom = atom<Record<PanelId, string>>((get) => {
  const registry = get(panelRegistryAtom);
  const keybindingsMap = get(keybindingsMapAtom);
  const enabled = get(panelEnabledAtom);
  const result: Record<PanelId, string> = {};
  for (const panel of registry) {
    const isEnabled = (panel.isBuiltin ?? false) || (enabled[panel.id] ?? panel.defaultEnabled ?? true);
    if (!isEnabled) continue;
    const binding = keybindingsMap[panelKeybindingId(panel.id)]?.binding ?? "";
    if (binding) result[panel.id] = binding;
  }
  return result;
});

// ── Memoized derived atom factories ──────────────────────────────────
// Each zone ID maps to a stable atom instance to avoid creating new atoms
// on every render (which causes infinite re-render loops in Jotai).

const panelsInZoneAtomMap = new Map<ZoneId, Atom<ReadonlyArray<PanelId>>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<ReadonlyArray<PanelId>>((get) => {
      const assignments = get(zoneAssignmentsAtom);
      const order = get(zoneOrderAtom);
      const registry = get(panelRegistryAtom);
      const enabled = get(panelEnabledAtom);
      const registeredIds = new Set(registry.map((p) => p.id));
      const isEnabled = (panelId: PanelId): boolean => {
        const def = registry.find((p) => p.id === panelId);
        if (def?.isBuiltin ?? false) return true;
        return enabled[panelId] ?? def?.defaultEnabled ?? true;
      };
      // Only surface panels that are actually registered. Dynamic panels
      // (agents, terminals) are per-workspace, so the global zone assignments
      // may still reference panels belonging to another workspace; filtering by
      // the current registry drops those without touching their stored placement.
      const panelsInZone = (Object.entries(assignments) as ReadonlyArray<[PanelId, ZoneId]>)
        .filter(([panelId, zone]) => zone === zoneId && registeredIds.has(panelId) && isEnabled(panelId))
        .map(([panelId]) => panelId);

      const zoneOrder = order[zoneId];
      if (!zoneOrder) return panelsInZone;

      // Sort by stored order, appending any panels not in the order array at the end
      const ordered = zoneOrder.filter((id) => panelsInZone.includes(id));
      const unordered = panelsInZone.filter((id) => !zoneOrder.includes(id));
      return [...ordered, ...unordered];
    }),
  ]),
);

export const panelsInZoneAtom = (zoneId: ZoneId): Atom<ReadonlyArray<PanelId>> => {
  return panelsInZoneAtomMap.get(zoneId)!;
};

const isZoneVisibleAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<boolean>((get) => {
      const visibility = get(zoneVisibilityAtom);
      if (!(visibility[zoneId] ?? false)) return false;
      // A zone with no panels must not be visible, even if the persisted
      // visibility flag says otherwise.  This guards against stale
      // localStorage, race conditions during drag-and-drop, or any other
      // scenario where visibility gets out of sync with panel assignments.
      const panels = get(panelsInZoneAtomMap.get(zoneId)!);
      return panels.length > 0;
    }),
  ]),
);

export const isZoneVisibleAtom = (zoneId: ZoneId): Atom<boolean> => {
  return isZoneVisibleAtomMap.get(zoneId)!;
};

// Derived: is left side visible (top-left OR bottom-left)
export const isLeftSideVisibleAtom = atom<boolean>((get) => {
  return get(isZoneVisibleAtomMap.get("top-left")!) || get(isZoneVisibleAtomMap.get("bottom-left")!);
});

// Derived: is right side visible (top-right OR bottom-right)
export const isRightSideVisibleAtom = atom<boolean>((get) => {
  return get(isZoneVisibleAtomMap.get("top-right")!) || get(isZoneVisibleAtomMap.get("bottom-right")!);
});

// Derived: is bottom visible
export const isBottomVisibleAtom = atom<boolean>((get) => {
  return get(isZoneVisibleAtomMap.get("bottom")!);
});

// ── Side-level visibility (for bottom bar toggle buttons) ───────────
// Stores the per-zone visibility snapshot taken when a side is hidden,
// so it can be fully restored when toggled back on.
export const savedSideVisibilityAtom = atom<Partial<Record<LayoutSide, Partial<Record<ZoneId, boolean>>>>>({});

// Derived: is a layout side currently visible (any of its zones visible)
const isSideVisibleAtomMap = new Map<LayoutSide, Atom<boolean>>(
  LAYOUT_SIDES.map((side) => [
    side,
    atom<boolean>((get) => {
      const zones = SIDE_ZONE_MAP[side];
      return zones.some((zoneId) => get(isZoneVisibleAtomMap.get(zoneId)!));
    }),
  ]),
);

export const isSideVisibleAtom = (side: LayoutSide): Atom<boolean> => {
  return isSideVisibleAtomMap.get(side)!;
};

// Derived: does a layout side have any panels assigned to any of its zones?
const sideHasPanelsAtomMap = new Map<LayoutSide, Atom<boolean>>(
  LAYOUT_SIDES.map((side) => [
    side,
    atom<boolean>((get) => {
      const zones = SIDE_ZONE_MAP[side];
      return zones.some((zoneId) => get(panelsInZoneAtomMap.get(zoneId)!).length > 0);
    }),
  ]),
);

export const sideHasPanelsAtom = (side: LayoutSide): Atom<boolean> => {
  return sideHasPanelsAtomMap.get(side)!;
};

const activePanelInZoneAtomMap = new Map<ZoneId, Atom<PanelDefinition | undefined>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<PanelDefinition | undefined>((get) => {
      const registry = get(panelRegistryAtom);
      const activePanel = get(activePanelPerZoneAtom);
      const panelId = activePanel[zoneId];
      if (!panelId) return undefined;
      return registry.find((p) => p.id === panelId);
    }),
  ]),
);

export const activePanelInZoneAtom = (zoneId: ZoneId): Atom<PanelDefinition | undefined> => {
  return activePanelInZoneAtomMap.get(zoneId)!;
};

// ── Expand mode ──────────────────────────────────────────────────────
// When non-null, the layout enters "expand mode": only the zone containing
// this panel and the center diff area are visible; everything else is hidden.
export const expandedPanelIdAtom = atom<PanelId | null>(null);

// ── Maximize mode (compact layout) ───────────────────────────────────
// When non-null, the section backing this zone is MAXIMIZED: it fills the
// workspace area (covering the top banner) while the far-left nav rail stays
// visible. The maximized section keeps its own tab strip, so a multi-panel
// section can still switch panels while maximized. Distinct from
// `expandedPanelIdAtom` (a diff-panel "review mode" used by the legacy
// DockingLayout). Non-persisted: maximize is a transient, modal-ish view that
// resets on reload, so a stale flag can never leave the app stuck maximized.
export const maximizedZoneAtom = atom<ZoneId | null>(null);

// ── Cross-section tab drag (non-persisted) ───────────────────────────
// Tracks an in-flight tab drag so every PanelSection can preview the move
// without committing it: the target section renders a drop highlight and a
// ghosted full-size copy of the dragged tab at the insertion index, while the
// source keeps the tab until drop. The atoms are only mutated on drop (via
// movePanel), so this preview state is intentionally separate from the
// persisted zone atoms. Reset to null on drop / cancel.
export type PanelDragState = {
  activePanelId: PanelId;
  sourceZone: ZoneId;
  targetZone: ZoneId;
  /** Insertion index within the target zone's panels, excluding the dragged one. */
  insertIndex: number;
};

export const panelDragStateAtom = atom<PanelDragState | null>(null);

/**
 * The panel ids a section should *render* during a drag: the dragged panel is
 * removed from every section and re-inserted into the target section at the
 * insertion index, so its ghost appears to slide between sections. With no drag
 * in flight this is the zone's panels unchanged.
 *
 * Returns the input `panelIds` array (same reference) whenever the drag does
 * not touch this zone, so derived atoms and memos over the result don't churn
 * for uninvolved zones on every drag-state change.
 */
export const computeDisplayedPanelIds = (inputs: {
  zone: ZoneId;
  panelIds: ReadonlyArray<PanelId>;
  drag: PanelDragState | null;
}): ReadonlyArray<PanelId> => {
  const { zone, panelIds, drag } = inputs;
  if (!drag) return panelIds;
  if (drag.targetZone !== zone && !panelIds.includes(drag.activePanelId)) return panelIds;
  const withoutActive = panelIds.filter((id) => id !== drag.activePanelId);
  if (drag.targetZone !== zone) return withoutActive;
  const index = Math.min(Math.max(drag.insertIndex, 0), withoutActive.length);
  return [...withoutActive.slice(0, index), drag.activePanelId, ...withoutActive.slice(index)];
};

// ── Per-zone drag-state slices ───────────────────────────────────────
// During a drag, `panelDragStateAtom` changes on every insertion-index or
// target-zone update. Components must NOT subscribe to it directly (that
// re-renders every section, including heavy panel content, per change); they
// subscribe to these narrow slices instead, which only notify when the value
// for their own zone actually changes.

export const isPanelDragActiveAtom = atom<boolean>((get) => get(panelDragStateAtom) !== null);

// The dragged panel id, stable for the whole drag — lets the DragOverlay owner
// render without re-rendering on every insertion-index change.
export const draggedPanelIdAtom = atom<PanelId | null>((get) => get(panelDragStateAtom)?.activePanelId ?? null);

const isDropTargetAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<boolean>((get) => {
      const drag = get(panelDragStateAtom);
      return drag !== null && drag.targetZone === zoneId && drag.sourceZone !== zoneId;
    }),
  ]),
);

export const isDropTargetAtom = (zoneId: ZoneId): Atom<boolean> => {
  return isDropTargetAtomMap.get(zoneId)!;
};

// The dragged panel id while this zone is the drag target, else null. Tab
// strips use it to extend their tab-definition pool with the incoming ghost —
// pool membership then only changes when the ghost enters/leaves the zone,
// not on every insertion-index change.
const ghostPanelIdAtomMap = new Map<ZoneId, Atom<PanelId | null>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<PanelId | null>((get) => {
      const drag = get(panelDragStateAtom);
      return drag !== null && drag.targetZone === zoneId ? drag.activePanelId : null;
    }),
  ]),
);

export const ghostPanelIdAtom = (zoneId: ZoneId): Atom<PanelId | null> => {
  return ghostPanelIdAtomMap.get(zoneId)!;
};

// `selectAtom` with shallow-array equality keeps the previous reference when a
// recompute yields the same ids — e.g. the source zone's list is re-filtered
// (new array, same contents) on every drag-state change.
const displayedPanelIdsAtomMap = new Map<ZoneId, Atom<ReadonlyArray<PanelId>>>(
  ZONE_IDS.map((zoneId) => {
    const base = atom<ReadonlyArray<PanelId>>((get) =>
      computeDisplayedPanelIds({
        zone: zoneId,
        panelIds: get(panelsInZoneAtomMap.get(zoneId)!),
        drag: get(panelDragStateAtom),
      }),
    );
    return [zoneId, selectAtom(base, (ids) => ids, areArraysShallowEqual)];
  }),
);

export const displayedPanelIdsAtom = (zoneId: ZoneId): Atom<ReadonlyArray<PanelId>> => {
  return displayedPanelIdsAtomMap.get(zoneId)!;
};

// The id of the panel a zone should show as active: the stored active panel
// when it is still in the zone, else the zone's first panel. (Distinct from
// `activePanelInZoneAtom`, which resolves a PanelDefinition and has no
// first-panel fallback.)
const activePanelIdInZoneAtomMap = new Map<ZoneId, Atom<PanelId | undefined>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<PanelId | undefined>((get) => {
      const panelIds = get(panelsInZoneAtomMap.get(zoneId)!);
      const candidate = get(activePanelPerZoneAtom)[zoneId];
      return candidate && panelIds.includes(candidate) ? candidate : panelIds[0];
    }),
  ]),
);

export const activePanelIdInZoneAtom = (zoneId: ZoneId): Atom<PanelId | undefined> => {
  return activePanelIdInZoneAtomMap.get(zoneId)!;
};

// Narrow per-zone focus flag: a focus change (adding/dropping a panel, or a
// pane-navigation hotkey) must not re-render every section.
const isZoneFocusedAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [zoneId, atom<boolean>((get) => get(focusedZoneAtom) === zoneId)]),
);

export const isZoneFocusedAtom = (zoneId: ZoneId): Atom<boolean> => {
  return isZoneFocusedAtomMap.get(zoneId)!;
};

// ── Derived zone atom for "files" panel ────────────────────────────
// Narrows the subscription so consumers that only need the zone for the
// "files" panel don't re-render when other panels' zone assignments change.
export const filesZoneAtom = atom<ZoneId | undefined>((get) => {
  const assignments = get(zoneAssignmentsAtom);
  return assignments["files"] as ZoneId | undefined;
});

// ── File Browser tab state (per workspace) ───────────────────────────
export type FileBrowserTab = "all" | "changes" | "history";

export const activeFileBrowserTabAtomFamily = atomFamily((workspaceId: string) =>
  atomWithStorage<FileBrowserTab>(`sculptor-fb-tab-${workspaceId}`, "all"),
);

// ── Store factory ────────────────────────────────────────────────────
// Unified way to create an initialised panel store.  Usable in tests,
// Storybook decorators, or the main app bootstrap.

type CreatePanelStoreOptions = {
  /** When true, derive zone assignments, active panels, and visibility from
   *  each panel's `defaultZone`.  When false (default), only the registry
   *  is set and the caller is responsible for layout atoms. */
  useDefaultLayout?: boolean;
};

export const createPanelStore = (
  panels: ReadonlyArray<PanelDefinition>,
  { useDefaultLayout = false }: CreatePanelStoreOptions = {},
): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(panelRegistryAtom, panels);

  if (useDefaultLayout) {
    const zoneAssignments = Object.fromEntries(panels.map((p) => [p.id, p.defaultZone])) as Record<PanelId, ZoneId>;
    store.set(zoneAssignmentsAtom, zoneAssignments);

    const activePerZone: Partial<Record<ZoneId, PanelId>> = {};
    const visibility: Partial<Record<ZoneId, boolean>> = {};
    for (const panel of panels) {
      if (!activePerZone[panel.defaultZone]) {
        activePerZone[panel.defaultZone] = panel.id;
      }
      visibility[panel.defaultZone] = true;
    }
    store.set(activePanelPerZoneAtom, activePerZone);
    store.set(zoneVisibilityAtom, visibility);
  }

  return store;
};
