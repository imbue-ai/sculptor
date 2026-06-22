import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect, useMemo } from "react";
import { flushSync } from "react-dom";

import { isDismissibleOverlayOpen, shouldHandleKeybinding } from "~/common/ShortcutUtils";
import {
  activePanelPerZoneAtom,
  didZenImplyFocusModeAtom,
  focusModeActiveAtom,
  focusModeSavedVisibilityAtom,
  isSideVisibleAtom,
  panelEnabledAtom,
  panelRegistryAtom,
  panelShortcutsAtom,
  panelsInZoneAtom,
  savedSideVisibilityAtom,
  zenModeActiveAtom,
  zoneAssignmentsAtom,
  zoneOrderAtom,
  zoneVisibilityAtom,
} from "~/components/panels/atoms.ts";
import type { LayoutSide, PanelDefinition, PanelId, ZoneId } from "~/components/panels/types.ts";
import { SIDE_ZONE_MAP, ZONE_IDS } from "~/components/panels/types.ts";
import { computeToggleAction } from "~/components/panels/utils.ts";

/** Look up a single panel definition from the registry by ID. */
export const usePanelById = (id: PanelId | null): PanelDefinition | undefined => {
  const registry = useAtomValue(panelRegistryAtom);
  if (!id) return undefined;
  return registry.find((p) => p.id === id);
};

/** Per-zone enabled-panel lists. Use this for any guard or layout logic that
 *  must respect `panelEnabledAtom` — disabled panels are filtered out. */
export const usePanelsByZone = (): Partial<Record<ZoneId, ReadonlyArray<PanelId>>> => {
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const zonePanelArrays = ZONE_IDS.map((zoneId) => useAtomValue(panelsInZoneAtom(zoneId)));
  return useMemo(() => {
    const result: Partial<Record<ZoneId, ReadonlyArray<PanelId>>> = {};
    ZONE_IDS.forEach((zoneId, i) => {
      result[zoneId] = zonePanelArrays[i];
    });
    return result;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, zonePanelArrays);
};

type UsePanelEnabledResult = {
  enabled: Record<PanelId, boolean>;
  setEnabled: (id: PanelId, value: boolean) => void;
};

/** Per-panel on/off state. Builtin panels cannot be disabled. */
export const usePanelEnabled = (): UsePanelEnabledResult => {
  const [enabled, setEnabledState] = useAtom(panelEnabledAtom);
  const registry = useAtomValue(panelRegistryAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const panelsByZone = usePanelsByZone();
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);

  const setEnabled = useCallback(
    (id: PanelId, value: boolean): void => {
      const def = registry.find((p) => p.id === id);
      if ((def?.isBuiltin ?? false) && !value) return;

      // When disabling the active panel in a zone, rotate to the next enabled
      // sibling (in zoneOrder) so ZoneContent doesn't keep rendering the
      // now-disabled panel. panelsByZone[zone] is enabled-filtered and ordered.
      if (!value) {
        const zone = zoneAssignments[id];
        if (zone !== undefined) {
          setActivePanelPerZone((prev) => {
            if (prev[zone] !== id) return prev;
            const sibling = (panelsByZone[zone] ?? []).find((pid) => pid !== id);
            const next = { ...prev };
            if (sibling !== undefined) {
              next[zone] = sibling;
            } else {
              delete next[zone];
            }
            return next;
          });
        }
      }

      setEnabledState((prev) => ({ ...prev, [id]: value }));
    },
    [registry, zoneAssignments, panelsByZone, setActivePanelPerZone, setEnabledState],
  );

  return { enabled, setEnabled };
};

type UsePanelActionsResult = {
  movePanel: (panelId: PanelId, targetZone: ZoneId, insertIndex?: number) => void;
  togglePanel: (panelId: PanelId) => void;
};

/** Hook providing intent-based panel mutation operations. */
export const usePanelActions = (): UsePanelActionsResult => {
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const panelsByZone = usePanelsByZone();
  const [activePanelPerZone, setActivePanelPerZone] = useAtom(activePanelPerZoneAtom);
  const [zoneVisibility, setZoneVisibility] = useAtom(zoneVisibilityAtom);
  const setZoneAssignments = useSetAtom(zoneAssignmentsAtom);
  const setZoneOrder = useSetAtom(zoneOrderAtom);
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const setFocusModeActive = useSetAtom(focusModeActiveAtom);
  const setFocusModeSavedVisibility = useSetAtom(focusModeSavedVisibilityAtom);

  const movePanel = useCallback(
    (panelId: PanelId, targetZone: ZoneId, insertIndex?: number): void => {
      const sourceZone = zoneAssignments[panelId];

      if (sourceZone !== targetZone) {
        // Pre-compute remaining panels in the source zone before any state updates
        // so the downstream setters don't depend on a stale zoneAssignments closure.
        const remainingInSource = (Object.entries(zoneAssignments) as Array<[PanelId, ZoneId]>).filter(
          ([pid, zone]) => zone === sourceZone && pid !== panelId,
        );

        setZoneAssignments((prev) => ({ ...prev, [panelId]: targetZone }));

        setActivePanelPerZone((prev) => {
          const next = { ...prev, [targetZone]: panelId };
          if (prev[sourceZone] === panelId) {
            if (remainingInSource.length > 0) {
              next[sourceZone] = remainingInSource[0][0];
            } else {
              delete next[sourceZone];
            }
          }
          return next;
        });

        setZoneVisibility((prev) => {
          const next = { ...prev, [targetZone]: true };
          if (remainingInSource.length === 0) {
            next[sourceZone] = false;
          }
          return next;
        });
      }

      // Update zone order (handles both cross-zone moves and same-zone reorders)
      setZoneOrder((prev) => {
        const getDefaultOrder = (zone: ZoneId): Array<PanelId> =>
          (Object.entries(zoneAssignments) as Array<[PanelId, ZoneId]>)
            .filter(([, z]) => z === zone)
            .map(([pid]) => pid);

        const targetOrder = (prev[targetZone] ?? getDefaultOrder(targetZone)).filter((id) => id !== panelId);
        if (insertIndex !== undefined) {
          const clampedIndex = Math.min(insertIndex, targetOrder.length);
          targetOrder.splice(clampedIndex, 0, panelId);
        } else {
          targetOrder.push(panelId);
        }

        const sourceZone = zoneAssignments[panelId];
        if (sourceZone === targetZone) {
          return { ...prev, [targetZone]: targetOrder };
        }
        const sourceOrder = (prev[sourceZone] ?? getDefaultOrder(sourceZone)).filter((id) => id !== panelId);
        return { ...prev, [sourceZone]: sourceOrder, [targetZone]: targetOrder };
      });

      // Invariant: bottom-{side} cannot hold panels while top-{side} is empty.
      // If this move vacated a top zone whose bottom sibling still has panels,
      // promote the bottom panels up to the top so the side stays consolidated.
      // The empty check uses enabled-filtered panels (panelsByZone): a zone with
      // only disabled panels is visually empty and must trigger promotion.
      const siblingSide: "left" | "right" | null =
        sourceZone === "top-left" ? "left" : sourceZone === "top-right" ? "right" : null;
      if (siblingSide !== null && sourceZone !== targetZone) {
        const topZone: ZoneId = siblingSide === "left" ? "top-left" : "top-right";
        const bottomZone: ZoneId = siblingSide === "left" ? "bottom-left" : "bottom-right";
        const isTopNowEmpty = !(panelsByZone[topZone] ?? []).some((pid) => pid !== panelId);
        if (isTopNowEmpty) {
          const bottomPanels = (Object.entries(zoneAssignments) as Array<[PanelId, ZoneId]>)
            .filter(([, z]) => z === bottomZone)
            .map(([p]) => p);
          if (bottomPanels.length > 0) {
            setZoneAssignments((prev) => {
              const next = { ...prev };
              for (const p of bottomPanels) {
                next[p] = topZone;
              }
              return next;
            });
            setActivePanelPerZone((prev) => {
              const next = { ...prev };
              if (prev[bottomZone] !== undefined) {
                next[topZone] = prev[bottomZone];
                delete next[bottomZone];
              }
              return next;
            });
            setZoneVisibility((prev) => ({
              ...prev,
              [topZone]: true,
              [bottomZone]: false,
            }));
            setZoneOrder((prev) => {
              const next = { ...prev };
              next[topZone] = prev[bottomZone] ?? bottomPanels;
              next[bottomZone] = [];
              return next;
            });
          }
        }
      }
    },
    [zoneAssignments, panelsByZone, setZoneAssignments, setActivePanelPerZone, setZoneVisibility, setZoneOrder],
  );

  const togglePanel = useCallback(
    (panelId: PanelId): void => {
      const action = computeToggleAction({
        panelId,
        zoneAssignments,
        activePanelPerZone,
        zoneVisibility,
      });

      switch (action.type) {
        case "close-zone":
          setZoneVisibility((prev) => ({ ...prev, [action.zone]: false }));
          break;
        case "switch-panel":
          setActivePanelPerZone((prev) => ({ ...prev, [action.zone]: action.panelId }));
          setZoneVisibility((prev) => ({ ...prev, [action.zone]: true }));
          break;
        case "open-zone":
          setZoneVisibility((prev) => ({ ...prev, [action.zone]: true }));
          break;
      }

      if (isZenModeActive) {
        // In zen mode: update saved focus mode visibility so the change
        // persists when exiting zen mode, but don't exit focus/zen mode.
        const isNowVisible = action.type !== "close-zone";
        setFocusModeSavedVisibility((prev) => ({ ...prev, [action.zone]: isNowVisible }));
        return;
      }

      // Any panel state change exits focus mode.
      if (isFocusModeActive) {
        setFocusModeActive(false);
        setFocusModeSavedVisibility({});
      }
    },
    [
      zoneAssignments,
      activePanelPerZone,
      zoneVisibility,
      isZenModeActive,
      isFocusModeActive,
      setActivePanelPerZone,
      setZoneVisibility,
      setFocusModeActive,
      setFocusModeSavedVisibility,
    ],
  );

  return { movePanel, togglePanel };
};

type UseSideToggleResult = {
  isVisible: boolean;
  toggle: () => void;
};

/** Toggle an entire layout side (left / bottom / right).
 *  Saves per-zone visibility before hiding so it can be fully restored. */
export const useSideToggle = (side: LayoutSide): UseSideToggleResult => {
  const isVisible = useAtomValue(isSideVisibleAtom(side));
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const [savedSideVisibility, setSavedSideVisibility] = useAtom(savedSideVisibilityAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const setFocusModeActive = useSetAtom(focusModeActiveAtom);
  const setFocusModeSavedVisibility = useSetAtom(focusModeSavedVisibilityAtom);

  // Read the panels assigned to each zone in this side so we can fill in
  // missing active-panel entries when restoring visibility.
  const zones = SIDE_ZONE_MAP[side];
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const zonePanelArrays = zones.map((zoneId) => useAtomValue(panelsInZoneAtom(zoneId)));
  const panelsPerZone = useMemo(() => {
    const result: Partial<Record<ZoneId, ReadonlyArray<PanelId>>> = {};
    zones.forEach((zoneId, i) => {
      result[zoneId] = zonePanelArrays[i];
    });
    return result;
  }, [zones, zonePanelArrays]);

  const toggle = useCallback((): void => {
    if (isVisible) {
      // Snapshot current zone visibility and hide all zones in one pass.
      // The updater runs synchronously in Jotai, so `snapshot` is populated
      // before the next setter call.
      const snapshot: Partial<Record<ZoneId, boolean>> = {};
      setZoneVisibility((prev) => {
        const next = { ...prev };
        for (const zoneId of zones) {
          snapshot[zoneId] = prev[zoneId] ?? false;
          next[zoneId] = false;
        }
        return next;
      });
      setSavedSideVisibility((prev) => ({ ...prev, [side]: snapshot }));
    } else {
      // Restore saved visibility, or default to showing the first zone
      const saved = savedSideVisibility[side];
      setZoneVisibility((prev) => {
        const next = { ...prev };
        if (saved && Object.values(saved).some(Boolean)) {
          for (const zoneId of zones) {
            next[zoneId] = saved[zoneId] ?? false;
          }
        } else {
          next[zones[0]] = true;
        }
        return next;
      });
      setSavedSideVisibility((prev) => {
        const rest = { ...prev };
        delete rest[side];
        return rest;
      });

      // Ensure every zone being shown has an active panel. Without this,
      // a zone can become visible but render empty because no panel is selected.
      setActivePanelPerZone((prev) => {
        const next = { ...prev };
        for (const zoneId of zones) {
          if (!next[zoneId]) {
            const panels = panelsPerZone[zoneId];
            if (panels && panels.length > 0) {
              next[zoneId] = panels[0];
            }
          }
        }
        return next;
      });
    }

    if (isZenModeActive) {
      // In zen mode: update saved focus mode visibility so the change
      // persists when exiting zen mode, but don't exit focus/zen mode.
      setFocusModeSavedVisibility((prev) => {
        const next = { ...prev };
        if (isVisible) {
          // Just hid this side → mark its zones as hidden in saved state
          for (const zoneId of zones) {
            next[zoneId] = false;
          }
        } else {
          // Just showed this side → mark its zones as visible in saved state
          const saved = savedSideVisibility[side];
          if (saved && Object.values(saved).some(Boolean)) {
            for (const zoneId of zones) {
              next[zoneId] = saved[zoneId] ?? false;
            }
          } else {
            next[zones[0]] = true;
          }
        }
        return next;
      });
      return;
    }

    // Any panel state change exits focus mode.
    if (isFocusModeActive) {
      setFocusModeActive(false);
      setFocusModeSavedVisibility({});
    }
  }, [
    side,
    isVisible,
    isZenModeActive,
    isFocusModeActive,
    savedSideVisibility,
    panelsPerZone,
    zones,
    setZoneVisibility,
    setSavedSideVisibility,
    setActivePanelPerZone,
    setFocusModeActive,
    setFocusModeSavedVisibility,
  ]);

  return { isVisible, toggle };
};

type UseFocusModeResult = {
  isFocusModeActive: boolean;
  toggleFocusMode: () => void;
};

/** Toggle focus mode — hide all panels (saving their state) or restore them.
 *  When exiting focus mode while zen mode is active, also exits zen mode
 *  (Cmd+\ is a full escape from zen mode). */
export const useFocusMode = (): UseFocusModeResult => {
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const setFocusModeActive = useSetAtom(focusModeActiveAtom);
  const [focusModeSavedVisibility, setFocusModeSavedVisibility] = useAtom(focusModeSavedVisibilityAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const setZenModeActive = useSetAtom(zenModeActiveAtom);
  const setZenModeImpliedFocusMode = useSetAtom(didZenImplyFocusModeAtom);

  // Read the panels assigned to each zone so we can fill in missing
  // active-panel entries when restoring visibility.
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const zonePanelArrays = ZONE_IDS.map((zoneId) => useAtomValue(panelsInZoneAtom(zoneId)));
  const panelsPerZone = useMemo(() => {
    const result: Partial<Record<ZoneId, ReadonlyArray<PanelId>>> = {};
    ZONE_IDS.forEach((zoneId, i) => {
      result[zoneId] = zonePanelArrays[i];
    });
    return result;
  }, [zonePanelArrays]);

  const toggleFocusMode = useCallback((): void => {
    if (!isFocusModeActive) {
      // Entering focus mode: snapshot current visibility, then hide all zones.
      const snapshot: Partial<Record<ZoneId, boolean>> = {};
      setZoneVisibility((prev) => {
        const next = { ...prev };
        for (const zoneId of ZONE_IDS) {
          snapshot[zoneId] = prev[zoneId] ?? false;
          next[zoneId] = false;
        }
        return next;
      });
      setFocusModeSavedVisibility(snapshot);
      setFocusModeActive(true);
    } else {
      // Exiting focus mode: restore saved visibility.
      setZoneVisibility((prev) => {
        const next = { ...prev };
        if (Object.values(focusModeSavedVisibility).some(Boolean)) {
          for (const zoneId of ZONE_IDS) {
            next[zoneId] = focusModeSavedVisibility[zoneId] ?? false;
          }
        }
        return next;
      });

      // Ensure every restored-visible zone has an active panel.
      setActivePanelPerZone((prev) => {
        const next = { ...prev };
        for (const zoneId of ZONE_IDS) {
          if (!next[zoneId]) {
            const panels = panelsPerZone[zoneId];
            if (panels && panels.length > 0) {
              next[zoneId] = panels[0];
            }
          }
        }
        return next;
      });

      setFocusModeSavedVisibility({});
      setFocusModeActive(false);

      // Exiting focus mode also fully exits zen mode.
      setZenModeActive(false);
      setZenModeImpliedFocusMode(false);
    }
  }, [
    isFocusModeActive,
    focusModeSavedVisibility,
    panelsPerZone,
    setZoneVisibility,
    setFocusModeSavedVisibility,
    setFocusModeActive,
    setActivePanelPerZone,
    setZenModeActive,
    setZenModeImpliedFocusMode,
  ]);

  return { isFocusModeActive, toggleFocusMode };
};

type UseZenModeResult = {
  isZenModeActive: boolean;
  toggleZenMode: () => void;
};

/** Toggle zen mode — hide all UI chrome and panels, maximizing chat space.
 *  Builds on focus mode: entering zen also enters focus mode (if not already active).
 *  Exiting zen via Cmd+Shift+\ preserves pre-existing focus mode;
 *  exiting via Cmd+\ (focus mode toggle) exits both. */
export const useZenMode = (): UseZenModeResult => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const setZenModeActive = useSetAtom(zenModeActiveAtom);
  const [didZenImplyFocusMode, setZenModeImpliedFocusMode] = useAtom(didZenImplyFocusModeAtom);
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const { toggleFocusMode } = useFocusMode();

  const toggleZenMode = useCallback((): void => {
    if (!isZenModeActive) {
      // Entering zen mode: also enter focus mode if not already active.
      if (!isFocusModeActive) {
        toggleFocusMode();
        setZenModeImpliedFocusMode(true);
      } else {
        setZenModeImpliedFocusMode(false);
      }
      setZenModeActive(true);
    } else {
      // Exiting zen mode: show chrome. If zen implied focus mode, also exit it.
      setZenModeActive(false);
      if (didZenImplyFocusMode) {
        toggleFocusMode();
        setZenModeImpliedFocusMode(false);
      }
    }
  }, [
    isZenModeActive,
    isFocusModeActive,
    didZenImplyFocusMode,
    toggleFocusMode,
    setZenModeActive,
    setZenModeImpliedFocusMode,
  ]);

  return { isZenModeActive, toggleZenMode };
};

/**
 * PyCharm/VS Code-style focus-then-toggle dispatch. Disabled panels are
 * already absent from `panelShortcutsAtom`, so they never fire here.
 */
export const usePanelKeyboardShortcuts = (): void => {
  const shortcuts = useAtomValue(panelShortcutsAtom);
  const registry = useAtomValue(panelRegistryAtom);
  const zoneAssignments = useAtomValue(zoneAssignmentsAtom);
  const zoneVisibility = useAtomValue(zoneVisibilityAtom);
  const activePanelPerZone = useAtomValue(activePanelPerZoneAtom);
  const setZoneVisibility = useSetAtom(zoneVisibilityAtom);
  const setActivePanelPerZone = useSetAtom(activePanelPerZoneAtom);
  const isFocusModeActive = useAtomValue(focusModeActiveAtom);
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const setFocusModeActive = useSetAtom(focusModeActiveAtom);
  const setFocusModeSavedVisibility = useSetAtom(focusModeSavedVisibilityAtom);

  useEffect(() => {
    const focusPanel = (panel: PanelDefinition, zone: ZoneId): void => {
      const customTarget = panel.getFocusTarget?.() ?? null;
      if (customTarget instanceof HTMLElement) {
        customTarget.focus();
        return;
      }
      const fallback = document.querySelector(`[data-zone-id="${zone}"]`);
      if (fallback instanceof HTMLElement) fallback.focus();
    };

    const handleKeyDown = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;
      for (const [panelId, shortcutString] of Object.entries(shortcuts)) {
        if (!shouldHandleKeybinding(e, shortcutString)) continue;
        const panel = registry.find((p) => p.id === panelId);
        if (!panel) return;
        const zone = zoneAssignments[panelId];
        if (!zone) return;

        e.preventDefault();

        const isVisible = zoneVisibility[zone] ?? false;
        const isActiveTab = activePanelPerZone[zone] === panelId;
        const zoneEl = document.querySelector(`[data-zone-id="${zone}"]`);
        const hasFocus = zoneEl?.contains(document.activeElement) ?? false;

        let isNowVisible = true;
        if (!isVisible) {
          // flushSync forces React to commit the visibility/active-panel
          // changes before we try to focus the (now-mounted) zone element.
          flushSync(() => {
            setZoneVisibility((prev) => ({ ...prev, [zone]: true }));
            setActivePanelPerZone((prev) => ({ ...prev, [zone]: panelId as PanelId }));
          });
          focusPanel(panel, zone);
        } else if (!isActiveTab) {
          flushSync(() => {
            setActivePanelPerZone((prev) => ({ ...prev, [zone]: panelId as PanelId }));
          });
          focusPanel(panel, zone);
        } else if (!hasFocus) {
          focusPanel(panel, zone);
        } else {
          setZoneVisibility((prev) => ({ ...prev, [zone]: false }));
          isNowVisible = false;
        }

        if (isZenModeActive) {
          // In zen mode, mirror the visibility change into the saved focus-mode
          // snapshot so it survives zen-mode exit.
          setFocusModeSavedVisibility((prev) => ({ ...prev, [zone]: isNowVisible }));
        } else if (isFocusModeActive) {
          setFocusModeActive(false);
          setFocusModeSavedVisibility({});
        }
        return;
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return (): void => window.removeEventListener("keydown", handleKeyDown);
  }, [
    shortcuts,
    registry,
    zoneAssignments,
    zoneVisibility,
    activePanelPerZone,
    isFocusModeActive,
    isZenModeActive,
    setZoneVisibility,
    setActivePanelPerZone,
    setFocusModeActive,
    setFocusModeSavedVisibility,
  ]);
};
