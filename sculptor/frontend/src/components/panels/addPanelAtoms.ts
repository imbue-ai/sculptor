import { atom } from "jotai";

import type { ZoneId } from "~/components/panels/types.ts";

/**
 * Open state for the Add Panel palette (the cmd+k-style picker).
 *
 * `null` means the palette is closed. A `ZoneId` means it is open, scoped to
 * that section as the *initial* destination — the destination is changeable
 * from inside the palette, but it starts here (e.g. the section whose "+" was
 * clicked, or whose empty-state "Browse all panels" button was pressed).
 */
export const addPanelTargetZoneAtom = atom<ZoneId | null>(null);
