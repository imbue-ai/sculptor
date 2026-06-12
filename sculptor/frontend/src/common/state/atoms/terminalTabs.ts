import { atomWithStorage } from "jotai/utils";

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
