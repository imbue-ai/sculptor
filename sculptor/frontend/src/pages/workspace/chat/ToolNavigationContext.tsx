/* eslint-disable react-refresh/only-export-components */
import type { ReactElement, ReactNode } from "react";
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";

type RowRegistration = {
  itemIds: ReadonlyArray<string>;
};

type ToolNavigationContextValue = {
  /** The id of the currently open chip or pill, or null when nothing is open. */
  openItemId: string | null;
  /** Set the open item.
   *  When `pinned` is true, hover-leave will not auto-close the popover —
   *  used by click and keyboard navigation. Hover opens pass `false` so
   *  the popover dismisses when the mouse leaves. */
  setOpenItemId: (id: string | null, pinned?: boolean) => void;
  /** Whether the currently open item should resist hover-leave dismissal. */
  isPinnedRef: React.MutableRefObject<boolean>;
  /** Move the open popover across registered rows.
   *  - `prev` / `next`: one step left/right through the flattened item order.
   *  - `up` / `down`: jump to the adjacent row, picking the item whose
   *    horizontal center is closest to the source item's center.
   *  Pass `fromId` to anchor navigation at a specific item (used when an
   *  unopened item — e.g. a focused subagent pill — wants to advance to the
   *  next sibling without first being opened by a click). */
  navigate: (direction: "prev" | "next" | "up" | "down", fromId?: string) => void;
  registerRow: (rowIndex: number, itemIds: ReadonlyArray<string>) => void;
  unregisterRow: (rowIndex: number) => void;
  setItemRef: (itemId: string, el: HTMLElement | null) => void;
};

const ToolNavigationContext = createContext<ToolNavigationContextValue | null>(null);

export const useToolNavigation = (): ToolNavigationContextValue | null => useContext(ToolNavigationContext);

export const ToolNavigationProvider = ({ children }: { children: ReactNode }): ReactElement => {
  // The setter is wrapped below to also update isPinnedRef in lock-step.
  // eslint-disable-next-line react/hook-use-state
  const [openItemId, setOpenItemIdState] = useState<string | null>(null);
  const isPinnedRef = useRef(false);
  const rowsRef = useRef(new Map<number, RowRegistration>());
  const itemRefsRef = useRef(new Map<string, HTMLElement | null>());

  // Use a ref so navigate() doesn't recreate on every openItemId change.
  // The ref is read only inside navigate() (a callback), never during render,
  // so syncing it in an effect keeps render pure without changing behavior.
  const openItemIdRef = useRef(openItemId);
  useEffect(() => {
    openItemIdRef.current = openItemId;
  });

  const setOpenItemId = useCallback((id: string | null, pinned: boolean = true): void => {
    isPinnedRef.current = id !== null && pinned;
    setOpenItemIdState(id);
  }, []);

  const getAllItemIds = useCallback((): ReadonlyArray<string> => {
    const sorted = [...rowsRef.current.entries()].sort(([a], [b]) => a - b);
    return sorted.flatMap(([, reg]) => [...reg.itemIds]);
  }, []);

  const focusAndOpen = useCallback(
    (targetId: string): void => {
      setOpenItemId(targetId, true);
      const targetEl = itemRefsRef.current.get(targetId);
      targetEl?.scrollIntoView({ block: "nearest", inline: "nearest" });
      // Move focus to the new active item so its keydown handler is the one
      // that fires for the next arrow press. Without this, focus stays on
      // the originally-clicked pill while openItemId crosses into a sibling
      // row (e.g. subagent ↔ tool pill row), and subsequent arrow keys hit
      // the wrong handler.
      targetEl?.focus({ preventScroll: true });
    },
    [setOpenItemId],
  );

  const navigate = useCallback(
    (direction: "prev" | "next" | "up" | "down", fromId?: string): void => {
      const sourceId = fromId ?? openItemIdRef.current;
      if (!sourceId) return;

      if (direction === "prev" || direction === "next") {
        const allIds = getAllItemIds();
        const currentIdx = allIds.indexOf(sourceId);
        if (currentIdx < 0) return;

        const targetIdx =
          direction === "prev" ? Math.max(currentIdx - 1, 0) : Math.min(currentIdx + 1, allIds.length - 1);
        if (targetIdx === currentIdx) return;

        focusAndOpen(allIds[targetIdx]!);
        return;
      }

      // Vertical: jump to the adjacent row, picking the item closest in
      // x-position to the current source item.
      const sortedRows = [...rowsRef.current.entries()].sort(([a], [b]) => a - b);
      const sourceRowIdx = sortedRows.findIndex(([, reg]) => reg.itemIds.includes(sourceId));
      if (sourceRowIdx < 0) return;

      const targetRowIdx = direction === "up" ? sourceRowIdx - 1 : sourceRowIdx + 1;
      if (targetRowIdx < 0 || targetRowIdx >= sortedRows.length) return;
      const targetRow = sortedRows[targetRowIdx]?.[1];
      if (!targetRow || targetRow.itemIds.length === 0) return;

      const sourceEl = itemRefsRef.current.get(sourceId);
      if (!sourceEl) return;
      const sourceRect = sourceEl.getBoundingClientRect();
      const sourceCenter = sourceRect.left + sourceRect.width / 2;

      let closestId: string | null = null;
      let closestDistance = Infinity;
      for (const itemId of targetRow.itemIds) {
        const el = itemRefsRef.current.get(itemId);
        if (!el) continue;
        const rect = el.getBoundingClientRect();
        const center = rect.left + rect.width / 2;
        const distance = Math.abs(center - sourceCenter);
        if (distance < closestDistance) {
          closestDistance = distance;
          closestId = itemId;
        }
      }
      if (!closestId) return;
      focusAndOpen(closestId);
    },
    [getAllItemIds, focusAndOpen],
  );

  const registerRow = useCallback((rowIndex: number, itemIds: ReadonlyArray<string>) => {
    rowsRef.current.set(rowIndex, { itemIds });
  }, []);

  const unregisterRow = useCallback((rowIndex: number) => {
    rowsRef.current.delete(rowIndex);
  }, []);

  const setItemRef = useCallback((itemId: string, el: HTMLElement | null) => {
    if (el) {
      itemRefsRef.current.set(itemId, el);
    } else {
      itemRefsRef.current.delete(itemId);
    }
  }, []);

  const value = useMemo(
    (): ToolNavigationContextValue => ({
      openItemId,
      setOpenItemId,
      isPinnedRef,
      navigate,
      registerRow,
      unregisterRow,
      setItemRef,
    }),
    [openItemId, setOpenItemId, navigate, registerRow, unregisterRow, setItemRef],
  );

  return <ToolNavigationContext.Provider value={value}>{children}</ToolNavigationContext.Provider>;
};
