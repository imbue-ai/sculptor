import type { Atom, WritableAtom } from "jotai";
import { atom, createStore } from "jotai";
import { atomFamily, atomWithStorage, selectAtom } from "jotai/utils";
import type { AtomFamily } from "jotai/vanilla/utils/atomFamily";

import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import type { KeybindingId } from "~/common/keybindings/types.ts";
import { atomWithDebouncedStorage } from "~/common/state/atoms/atomWithDebouncedStorage.ts";
import type { DefaultPanelLayout, LayoutSide, PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { LAYOUT_SIDES, SIDE_ZONE_MAP, ZONE_IDS } from "~/components/panels/types.ts";
import { areArraysShallowEqual } from "~/components/panels/utils.ts";

// ── Panel registry atom ─────────────────────────────────────────────
// Writable atom holding the current set of registered panels.
// Starts empty; set via PanelRegistryProvider (React) or
// createPanelStore (tests / programmatic).
export const panelRegistryAtom = atom<ReadonlyArray<PanelDefinition>>([]);

// ── Layout scope (per-workspace persistence, REQ-PERSIST-1) ──────────
// Every layout atom below is an atomFamily keyed by "layout scope": the
// active workspace id, or a global scope when no workspace is active
// (tests, non-workspace routes). The exported atoms are PROXIES that
// resolve the active scope on every read/write, so switching workspaces
// is a single `activeWorkspaceIdAtom` write — the entire layout flips
// atomically with it, with no save/restore copying between workspaces.
//
// Each scope persists to its own localStorage key (`<base>-ws-<id>`, the
// same keys the previous save/restore implementation used, so existing
// saved layouts load unchanged; the global scope keeps the legacy
// un-suffixed key).

export const LAYOUT_SCOPE_GLOBAL = "__global__";

// Tracks the currently active workspace ID for per-workspace panel layout.
// Set by usePerWorkspacePanelLayout (via switchActiveWorkspaceAtom) on
// mount/navigation; null when not viewing a workspace.
export const activeWorkspaceIdAtom = atom<string | null>(null);

export const layoutScopeAtom = atom<string>((get) => get(activeWorkspaceIdAtom) ?? LAYOUT_SCOPE_GLOBAL);

const layoutStorageKey = (baseKey: string, scopeId: string): string =>
  scopeId === LAYOUT_SCOPE_GLOBAL ? baseKey : `${baseKey}-ws-${scopeId}`;

type ScopedLayoutAtom<T> = WritableAtom<T, [T | ((prev: T) => T)], void>;

// Debounced: a single drag-and-drop move updates all four move-related
// atoms in the same frame. Synchronous localStorage writes would stack up on
// the drop frame and produce visible lag — debouncing keeps in-memory state
// immediate and coalesces the JSON-serialized writes to localStorage.
export const scopedLayoutStorageFamily = <T>(
  baseKey: string,
  initialValue: T,
): AtomFamily<string, ScopedLayoutAtom<T>> =>
  atomFamily((scopeId: string) => atomWithDebouncedStorage<T>(layoutStorageKey(baseKey, scopeId), initialValue, 200));

const proxyForScope = <T>(family: (scopeId: string) => ScopedLayoutAtom<T>): ScopedLayoutAtom<T> =>
  atom(
    (get) => get(family(get(layoutScopeAtom))),
    (get, set, update: T | ((prev: T) => T)) => set(family(get(layoutScopeAtom)), update),
  );

export const zoneAssignmentsFamily = scopedLayoutStorageFamily<Record<PanelId, ZoneId>>(
  "sculptor-zone-assignments",
  {},
);

export const activePanelPerZoneFamily = scopedLayoutStorageFamily<Partial<Record<ZoneId, PanelId>>>(
  "sculptor-active-panel-per-zone",
  {},
);

export const zoneVisibilityFamily = scopedLayoutStorageFamily<Partial<Record<ZoneId, boolean>>>(
  "sculptor-zone-visibility",
  {},
);

export const zoneSizesFamily = scopedLayoutStorageFamily<Partial<Record<ZoneId, number>>>("sculptor-zone-sizes", {});

export const zoneOrderFamily = scopedLayoutStorageFamily<Partial<Record<ZoneId, Array<PanelId>>>>(
  "sculptor-zone-order",
  {},
);

// The section (zone) that currently holds focus, persisted per workspace so that
// returning to a workspace restores its last-focused pane (and re-pulses the
// active-pane ring — see focusZoneAtom / useFocusRingFade). Default null: a
// never-visited workspace has no focused pane and shows no ring on first entry.
export const focusedZoneFamily = scopedLayoutStorageFamily<ZoneId | null>("sculptor-focused-zone", null);

export const zoneAssignmentsAtom = proxyForScope(zoneAssignmentsFamily);

export const activePanelPerZoneAtom = proxyForScope(activePanelPerZoneFamily);

export const zoneVisibilityAtom = proxyForScope(zoneVisibilityFamily);

export const zoneSizesAtom = proxyForScope(zoneSizesFamily);

export const zoneOrderAtom = proxyForScope(zoneOrderFamily);

// Logical focus — the anchor for Ctrl+Alt+Arrow pane nav and the two-stage
// Escape clear. Persisted per workspace (see focusedZoneFamily). The *visual*
// ring is a separate, transient layer (focusRingVisibleAtom): focus persists,
// but the ring only flashes and then fades (useFocusRingFade).
export const focusedZoneAtom = proxyForScope(focusedZoneFamily);

// ── Active-pane ring (transient visual layer over focusedZoneAtom) ────
// The ring is wayfinding, not steady-state chrome: it answers "where did focus
// just land?" after a jump (keyboard nav, adding/dropping a panel) or when
// returning to a workspace, then fades out. So the logical focus persists
// (focusedZoneAtom, above) while only the ring's visibility is timed here.

// How long the ring stays fully visible before it fades. Tunable.
export const FOCUS_RING_VISIBLE_MS = 2000;

// Whether the ring is currently shown. Flipped true on each focus change, then
// false after FOCUS_RING_VISIBLE_MS by useFocusRingFade. Non-persisted.
export const focusRingVisibleAtom = atom<boolean>(false);

// Bumped on every deliberate focus action (focusZoneAtom) and on workspace
// entry, so the ring re-appears and its fade timer restarts even when focus
// lands on the SAME zone (e.g. cycling tabs within a pane, or re-entering a
// workspace whose last-focused zone matches the one we left). Non-persisted.
export const focusRingNonceAtom = atom<number>(0);

// Write-only action: focus a zone AND pulse the ring (restart the fade). Use for
// deliberate "jump" actions — pane navigation, adding/dropping a panel. Clearing
// focus (Escape) writes focusedZoneAtom directly with null and does NOT pulse;
// recording focus on a plain click uses selectZoneAtom (below), also no pulse.
export const focusZoneAtom = atom(null, (_get, set, zone: ZoneId): void => {
  set(focusedZoneAtom, zone);
  set(focusRingNonceAtom, (n) => n + 1);
});

// Write-only action: record focus on a zone WITHOUT pulsing the ring — for plain
// pointer interactions (clicking into a pane). This persists "where I'm working"
// so returning to the workspace can flash it, while staying silent during active
// work. Also clears any in-flight ring so a click mid-pulse doesn't drag the ring
// onto the clicked pane.
export const selectZoneAtom = atom(null, (_get, set, zone: ZoneId): void => {
  set(focusedZoneAtom, zone);
  set(focusRingVisibleAtom, false);
});

/**
 * Make `workspaceId` the active layout scope, seeding its layout from
 * `defaultLayout` on first visit (REQ-DEFAULT-1). One write-atom call —
 * a single store transaction — flips the whole layout: every scoped proxy
 * above resolves to the new workspace's values in the same commit, so
 * there is no window where the previous workspace's layout renders under
 * the new workspace's URL. Dynamic panels (the active agent, the terminal)
 * are placed afterward by `useWorkspaceLayoutBootstrap` in the same
 * pre-paint flush.
 */
export const switchActiveWorkspaceAtom = atom(
  null,
  (get, set, params: { workspaceId: string; defaultLayout: DefaultPanelLayout }): void => {
    const { workspaceId, defaultLayout } = params;
    if (get(activeWorkspaceIdAtom) === workspaceId) return;

    // First visit: no in-memory state and no persisted key. (The key check
    // matters for the edge where a user deliberately emptied a workspace's
    // layout — an empty record persisted under the key is still "visited".)
    let hasVisited = Object.keys(get(zoneAssignmentsFamily(workspaceId))).length > 0;
    if (!hasVisited) {
      try {
        hasVisited = localStorage.getItem(layoutStorageKey("sculptor-zone-assignments", workspaceId)) !== null;
      } catch {
        // localStorage unavailable — treat as unvisited
      }
    }

    if (!hasVisited) {
      set(zoneAssignmentsFamily(workspaceId), defaultLayout.zoneAssignments);
      set(zoneOrderFamily(workspaceId), defaultLayout.zoneOrder ?? {});
      set(activePanelPerZoneFamily(workspaceId), defaultLayout.activePanelPerZone);
      set(zoneVisibilityFamily(workspaceId), defaultLayout.zoneVisibility);
    }

    set(activeWorkspaceIdAtom, workspaceId);

    // Re-pulse the active-pane ring on entry so a restored focused pane flashes
    // (then fades) as a wayfinding cue. Harmless when this workspace has no
    // persisted focus — useFocusRingFade keeps the ring hidden while it is null.
    set(focusRingNonceAtom, (n) => n + 1);
  },
);

/**
 * Drop a deleted workspace's layout state: the in-memory family entries and
 * the persisted per-workspace keys (including those owned by
 * sectionLayoutAtoms and the diff panel, listed here by base key so this
 * module doesn't need upward imports to reach their families — their
 * in-memory entries are negligible and die with the session).
 */
export const removeWorkspaceLayoutAtom = atom(null, (_get, _set, workspaceId: string): void => {
  zoneAssignmentsFamily.remove(workspaceId);
  activePanelPerZoneFamily.remove(workspaceId);
  zoneVisibilityFamily.remove(workspaceId);
  zoneSizesFamily.remove(workspaceId);
  zoneOrderFamily.remove(workspaceId);
  focusedZoneFamily.remove(workspaceId);
  const baseKeys = [
    "sculptor-zone-assignments",
    "sculptor-active-panel-per-zone",
    "sculptor-zone-visibility",
    "sculptor-zone-sizes",
    "sculptor-zone-order",
    "sculptor-focused-zone",
    "sculptor-section-split",
    "sculptor-section-size-percent",
    "sculptor-diffPanel-open",
    "sculptor-diffPanel-splitRatio",
  ];
  try {
    for (const baseKey of baseKeys) {
      localStorage.removeItem(layoutStorageKey(baseKey, workspaceId));
    }
  } catch {
    // localStorage unavailable — nothing to clean
  }
});

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

// Modal state atom — NOT persisted (resets on reload)
export const modalPanelIdAtom = atom<PanelId | null>(null);

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
  ZONE_IDS.map((zoneId) => {
    const base = atom<ReadonlyArray<PanelId>>((get) => {
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
    });
    // The filter above rebuilds a new array on every registry/assignment
    // identity change (e.g. the registry being re-set on a workspace switch
    // tick) even when this zone's ids are unchanged — shallow-equal dedupe
    // keeps the previous reference so subscribers don't re-render.
    return [zoneId, selectAtom(base, (ids) => ids, areArraysShallowEqual)];
  }),
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

// The COMPONENT to render for a zone's active panel. Component identities are
// cached per panel id (see dynamicPanels' module-level caches), so this value
// is stable across registry rebuilds — subscribing to it (rather than the
// whole registry) keeps panel bodies from re-rendering on registry ticks.
const activePanelComponentInZoneAtomMap = new Map<ZoneId, Atom<PanelDefinition["component"] | undefined>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<PanelDefinition["component"] | undefined>((get) => {
      const activePanelId = get(activePanelIdInZoneAtomMap.get(zoneId)!);
      if (!activePanelId) return undefined;
      return get(panelRegistryAtom).find((p) => p.id === activePanelId)?.component;
    }),
  ]),
);

export const activePanelComponentInZoneAtom = (zoneId: ZoneId): Atom<PanelDefinition["component"] | undefined> => {
  return activePanelComponentInZoneAtomMap.get(zoneId)!;
};

// Narrow per-zone focus flag: a focus change (adding/dropping a panel, or a
// pane-navigation hotkey) must not re-render every section.
const isZoneFocusedAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [zoneId, atom<boolean>((get) => get(focusedZoneAtom) === zoneId)]),
);

export const isZoneFocusedAtom = (zoneId: ZoneId): Atom<boolean> => {
  return isZoneFocusedAtomMap.get(zoneId)!;
};

// Narrow per-zone "show the ring" flag: this zone is focused AND the ring is
// currently visible. Sections subscribe to their own slice so the fade timer
// flips only the focused section, never every section. (Logical focus uses
// isZoneFocusedAtom above; this gates the transient ring overlay.)
const isZoneRingVisibleAtomMap = new Map<ZoneId, Atom<boolean>>(
  ZONE_IDS.map((zoneId) => [
    zoneId,
    atom<boolean>((get) => get(focusedZoneAtom) === zoneId && get(focusRingVisibleAtom)),
  ]),
);

export const isZoneRingVisibleAtom = (zoneId: ZoneId): Atom<boolean> => {
  return isZoneRingVisibleAtomMap.get(zoneId)!;
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
