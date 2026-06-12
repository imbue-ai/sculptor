import { useSetAtom } from "jotai";
import type { RefObject } from "react";
import { useEffect, useLayoutEffect, useRef } from "react";

import {
  browserViewPlacementAtomFamily,
  browserViewRegistryAtom,
  focusedBrowserWorkspaceIdAtom,
} from "./browserViewRegistry";

// Drives one workspace's placement from a placeholder div in the panel.
//
// On mount: registers workspaceId in the host registry (creating the slot
// if it's the first time we've ever shown this workspace's panel), marks
// itself as the focused workspace, and reports its bounds. While mounted
// it keeps bounds in sync with layout via ResizeObserver and scroll
// listeners. On unmount it sets visible:false (so the slot hides) but
// leaves the registry entry alone — webContents stays alive until
// workspace deletion explicitly evicts it.
export const useBrowserPanelPlacement = (workspaceId: string, placeholderRef: RefObject<HTMLElement | null>): void => {
  const setRegistry = useSetAtom(browserViewRegistryAtom);
  const setPlacement = useSetAtom(browserViewPlacementAtomFamily(workspaceId));
  const setFocusedWorkspaceId = useSetAtom(focusedBrowserWorkspaceIdAtom);

  // Compute bounds synchronously before paint so the slot renders at the
  // right position on the first frame, avoiding a flash of the webview at
  // its previous position.
  useLayoutEffect(() => {
    const el = placeholderRef.current;
    if (el === null) return;
    const rect = el.getBoundingClientRect();
    setPlacement({
      bounds: { x: rect.left, y: rect.top, width: rect.width, height: rect.height },
      visible: true,
    });
    setRegistry((prev) => {
      if (prev.has(workspaceId)) return prev;
      const next = new Set(prev);
      next.add(workspaceId);
      return next;
    });
    setFocusedWorkspaceId(workspaceId);

    return (): void => {
      setPlacement((prev) => ({ ...prev, visible: false, bounds: null }));
      setFocusedWorkspaceId((prev) => (prev === workspaceId ? null : prev));
    };
  }, [workspaceId, placeholderRef, setPlacement, setRegistry, setFocusedWorkspaceId]);

  // Track layout/scroll changes after mount. Coalesce via rAF so a burst
  // of resize events in one frame produces one atom write.
  const rafRef = useRef<number | null>(null);
  useEffect(() => {
    const el = placeholderRef.current;
    if (el === null) return;

    const reportBounds = (): void => {
      rafRef.current = null;
      const current = placeholderRef.current;
      if (current === null) return;
      const rect = current.getBoundingClientRect();
      setPlacement((prev) => {
        const bounds = { x: rect.left, y: rect.top, width: rect.width, height: rect.height };
        if (
          prev.visible &&
          prev.bounds !== null &&
          prev.bounds.x === bounds.x &&
          prev.bounds.y === bounds.y &&
          prev.bounds.width === bounds.width &&
          prev.bounds.height === bounds.height
        ) {
          return prev;
        }
        return { bounds, visible: true };
      });
    };

    const schedule = (): void => {
      if (rafRef.current !== null) return;
      rafRef.current = requestAnimationFrame(reportBounds);
    };

    const observer = new ResizeObserver(schedule);
    observer.observe(el);
    window.addEventListener("scroll", schedule, true);
    window.addEventListener("resize", schedule);

    return (): void => {
      observer.disconnect();
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      if (rafRef.current !== null) {
        cancelAnimationFrame(rafRef.current);
        rafRef.current = null;
      }
    };
  }, [placeholderRef, setPlacement]);
};
