import { atom, useSetAtom } from "jotai";
import { useEffect, useRef } from "react";

/**
 * Imperative action callbacks that the palette invokes directly. Components
 * that own each piece of UI (chat panel, workspace tabs, agent tabs)
 * register their callbacks here on mount; the palette runtime reads them
 * out and calls them. The same callback is also wired via
 * `useKeybindingHandler` (or a raw keydown listener), so the binding and
 * the palette converge on a single function instead of going through a
 * synthesized KeyboardEvent.
 *
 * The map keys are the actions the palette exposes — they don't
 * mirror keybinding ids 1:1 because some palette commands could one day
 * point at actions with no shortcut.
 */
export type CommandActionId =
  | "chat.jumpToBottom"
  | "workspace.closeCurrent"
  | "workspace.nextTab"
  | "workspace.previousTab"
  | "agent.next"
  | "agent.previous"
  | "agent.create"
  | "terminal.clearActive";

export type CommandActionCallback = () => void;

/**
 * Single source of truth for registered actions. Stored as a record to keep
 * the API symmetric with the runtime's `ui.*` shape; we replace the whole
 * record on registration so consumers using `useAtomValue` re-render only
 * when the specific slot they read changes.
 *
 * Stored as a frozen object so accidental in-place mutation is loud.
 */
export const commandActionsAtom = atom<Readonly<Partial<Record<CommandActionId, CommandActionCallback>>>>({});

/**
 * Register a callback for `id` while the calling component is mounted.
 * The latest callback wins if a sibling registers under the same id —
 * this happens in practice when the chat panel mounts in two routes
 * during navigation (the unmount cleanup runs after the new mount, but
 * since we key by ref-equality on the previous value, we don't accidentally
 * clear the new entry on the old unmount).
 */
export const useRegisterCommandAction = (id: CommandActionId, callback: CommandActionCallback): void => {
  const setActions = useSetAtom(commandActionsAtom);
  // Keep the callback in a ref so the registered function always sees the
  // latest closure without forcing the effect to re-run on every render.
  const ref = useRef(callback);
  ref.current = callback;

  useEffect(() => {
    const stableCallback: CommandActionCallback = () => ref.current();
    setActions((prev) => ({ ...prev, [id]: stableCallback }));
    return (): void => {
      setActions((prev) => {
        // Only clear if our entry is still the registered one. A faster
        // remount may have already overwritten it.
        if (prev[id] !== stableCallback) return prev;
        const next = { ...prev };
        delete next[id];
        return next;
      });
    };
  }, [id, setActions]);
};
