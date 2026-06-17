import { useStore } from "jotai";
import { useCallback } from "react";

import { useKeybindingHandler } from "~/common/keybindings";
import {
  activePanelPerZoneAtom,
  focusedZoneAtom,
  focusZoneAtom,
  maximizedZoneAtom,
  panelsInZoneAtom,
} from "~/components/panels/atoms.ts";
import type { PaneDirection, ZoneRect } from "~/components/panels/paneNavigation.ts";
import { cycleZone, pickNeighborZone } from "~/components/panels/paneNavigation.ts";
import { CENTER_SECTION_ZONE } from "~/components/panels/sectionHooks.ts";
import type { ZoneId } from "~/components/panels/types.ts";

type Store = ReturnType<typeof useStore>;

/** Read each on-screen section's zone + rect from the DOM (hidden sections are
 *  not mounted, so this naturally excludes them). */
const readZoneRects = (): Array<ZoneRect> =>
  Array.from(document.querySelectorAll<HTMLElement>("[data-zone-id]"))
    .map((el) => ({ zone: el.dataset.zoneId as ZoneId, rect: el.getBoundingClientRect() }))
    .filter((z) => z.rect.width > 0 && z.rect.height > 0);

/** The zone focus should move FROM: the tracked focused zone if it's still on
 *  screen, else the zone of the actually-focused DOM element, else the Center. */
const resolveCurrentZone = (store: Store, rects: ReadonlyArray<ZoneRect>): ZoneId => {
  const tracked = store.get(focusedZoneAtom);
  if (tracked && rects.some((r) => r.zone === tracked)) return tracked;
  const domZone = document.activeElement?.closest<HTMLElement>("[data-zone-id]")?.dataset.zoneId as ZoneId | undefined;
  if (domZone && rects.some((r) => r.zone === domZone)) return domZone;
  return CENTER_SECTION_ZONE;
};

/** Focus a section's content element and mark it as the focused zone (revealing
 *  the active-pane ring). Focuses the pane container (not an inner editor) so a
 *  follow-up Ctrl+Alt+Arrow keeps stepping between panes. */
const focusZone = (store: Store, zone: ZoneId): void => {
  const el = document.querySelector<HTMLElement>(`[data-zone-id="${zone}"]`);
  el?.focus();
  // Pulse the ring (focus + restart fade), so it reappears even when re-focusing
  // the same zone (e.g. tab cycling). resolveCurrentZone still reads the value
  // atom (focusedZoneAtom) for nav.
  store.set(focusZoneAtom, zone);
};

/**
 * Registers tmux-style pane focus keybindings for the compact layout:
 * Ctrl+Alt+Arrow moves focus between sections (geometrically), and
 * Ctrl+Tab / Ctrl+Shift+Tab cycle tabs within the focused section. Mounted once
 * per workspace (AgentWorkspaceCommands). State is read imperatively from the
 * jotai store at keypress time so the window listeners register once.
 */
export const usePaneNavigationShortcuts = (): void => {
  const store = useStore();

  // Up/down move to the spatially-adjacent pane (geometric).
  const navigate = useCallback(
    (direction: PaneDirection): void => {
      // Pane nav is meaningless while one section fills the workspace.
      if (store.get(maximizedZoneAtom) !== null) return;
      const rects = readZoneRects();
      const current = resolveCurrentZone(store, rects);
      const target = pickNeighborZone(rects, current, direction);
      if (target) focusZone(store, target);
    },
    [store],
  );

  // Left/right cycle linearly through every pane, wrapping around the ends.
  const cycle = useCallback(
    (delta: 1 | -1): void => {
      if (store.get(maximizedZoneAtom) !== null) return;
      const rects = readZoneRects();
      const current = resolveCurrentZone(store, rects);
      const target = cycleZone(rects, current, delta);
      if (target && target !== current) focusZone(store, target);
    },
    [store],
  );

  const cycleTab = useCallback(
    (delta: 1 | -1): void => {
      const rects = readZoneRects();
      const zone = resolveCurrentZone(store, rects);
      const panels = store.get(panelsInZoneAtom(zone));
      if (panels.length < 2) return;
      const active = store.get(activePanelPerZoneAtom)[zone] ?? panels[0];
      const index = Math.max(0, panels.indexOf(active));
      const next = panels[(index + delta + panels.length) % panels.length];
      store.set(activePanelPerZoneAtom, { ...store.get(activePanelPerZoneAtom), [zone]: next });
      focusZone(store, zone);
    },
    [store],
  );

  useKeybindingHandler(
    "focus_pane_left",
    useCallback(() => cycle(-1), [cycle]),
  );
  useKeybindingHandler(
    "focus_pane_right",
    useCallback(() => cycle(1), [cycle]),
  );
  useKeybindingHandler(
    "focus_pane_up",
    useCallback(() => navigate("up"), [navigate]),
  );
  useKeybindingHandler(
    "focus_pane_down",
    useCallback(() => navigate("down"), [navigate]),
  );
  useKeybindingHandler(
    "next_pane_tab",
    useCallback(() => cycleTab(1), [cycleTab]),
  );
  useKeybindingHandler(
    "previous_pane_tab",
    useCallback(() => cycleTab(-1), [cycleTab]),
  );
};
