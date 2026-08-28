import { atom } from "jotai";

import type { CommandId, PageId } from "../types/commandPalette.ts";

export const commandPaletteOpenAtom = atom<boolean>(false);

/**
 * Search query. Intentionally not persisted: persisting it would reopen the
 * palette with stale text.
 */
export const commandPaletteSearchAtom = atom<string>("");

export const commandPalettePagesAtom = atom<ReadonlyArray<PageId>>([]);

/**
 * Set by callers that want to open the palette directly to a specific
 * sub-page (e.g. the Cmd+P "Go to workspace" keybinding lands the user
 * on `workspaces.switch`). Read once on the rising edge of
 * `commandPaletteOpenAtom` by `useResetOnOpenChange`, which seeds the
 * page stack with `[initial]` instead of `[]`, then clears the atom.
 *
 * Why an atom and not just calling pushPage(): React batches the
 * `setIsOpen(true)` and `setPages([page])` updates into one commit,
 * after which `useResetOnOpenChange` would clobber pages back to []
 * because it sees the open transition. This atom carries the intent
 * across the reset effect.
 */
export const commandPaletteInitialPageAtom = atom<PageId | null>(null);

/**
 * Currently in-flight async command (for showing a per-row spinner). Null
 * when nothing is pending. Set by the run-command hook.
 */
export const commandPalettePendingAtom = atom<CommandId | null>(null);
