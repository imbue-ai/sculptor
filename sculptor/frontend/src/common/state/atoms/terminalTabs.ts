import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";

// The status union lives here (not in useTerminal.ts) so registry/atom consumers can
// import it without pulling the terminal runtime - and its window-global ambient
// deps - into type-only programs like the plugin-SDK .d.ts rollup.
export type TerminalConnectionStatus = "connecting" | "connected" | "reconnecting" | "disconnected";

type PersistedTerminalTab = {
  id: string;
  index: number;
  label: string;
};

export const terminalTabStateAtom = atomWithStorage<Record<string, Array<PersistedTerminalTab>>>(
  "sculptor-terminal-tabs",
  {},
  undefined,
  { getOnInit: true },
);

export const terminalNextIndexAtom = atomWithStorage<Record<string, number>>(
  "sculptor-terminal-next-index",
  {},
  undefined,
  { getOnInit: true },
);

export const activeTerminalTabIdAtom = atomWithStorage<Record<string, string>>(
  "sculptor-active-terminal-tab",
  {},
  undefined,
  { getOnInit: true },
);

// Per-terminal WebSocket connection state, keyed by the terminal's panel id
// (terminal:<wsId>:<index>), so the panel tab can flag a terminal whose connection
// dropped or won't recover. Only unhealthy states (reconnecting/disconnected) are
// stored — a connected/connecting terminal needs no indicator — so the map stays
// bounded and never holds stale entries for recovered terminals. Entries are
// written exclusively by mounted TerminalPanelView instances (only a mounted
// terminal holds a live socket; a backgrounded panel is unmounted by SectionBody),
// and each instance deletes its own key on unmount, so the map can never outgrow
// the set of mounted terminals. Transient by design: unlike the tab atoms above,
// connection state is meaningless across a reload and is not persisted.
export const terminalConnectionStatusesAtom = atom<Record<string, TerminalConnectionStatus>>({});

// Write-through for one terminal's connection status: unhealthy states are
// recorded, healthy ones — or null, on unmount — delete the entry. Owns the
// only-unhealthy-states discipline in one place so the status-change and
// unmount-cleanup callers in TerminalPanelView cannot drift.
export const reportTerminalConnectionStatusAtom = atom(
  null,
  (_get, set, update: { panelId: string; status: TerminalConnectionStatus | null }): void => {
    const { panelId, status } = update;
    set(terminalConnectionStatusesAtom, (previous) => {
      if (status === "reconnecting" || status === "disconnected") {
        if (previous[panelId] === status) {
          return previous;
        }
        return { ...previous, [panelId]: status };
      }

      if (!(panelId in previous)) {
        return previous;
      }
      const next = { ...previous };
      delete next[panelId];
      return next;
    });
  },
);
