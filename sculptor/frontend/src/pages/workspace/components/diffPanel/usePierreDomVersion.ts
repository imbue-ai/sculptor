import { useEffect, useRef, useState } from "react";

// Pierre fills its `<diffs-container>` shadow root asynchronously from a web
// worker, and shadow-DOM mutations are invisible to a light-DOM observer on the
// host. Mirroring `useInFileSearch`, we attach a MutationObserver to the host
// AND to every shadow root we find, re-scanning on each mutation so a
// worker-driven render (or a hunk expand/collapse) bumps the version.
const DEBOUNCE_MS = 100;

/**
 * Returns a counter that increments whenever the Pierre diff/file content under
 * `element` mounts or mutates (including inside shadow roots). Effects that must
 * run against painted line rows depend on this so they re-run as rows stream in
 * — rather than gating on a one-shot readiness flag that may have already
 * flipped (the source of the intermittent "no pill on the Files tab" bug).
 *
 * Because the setup effect is keyed on `element` (fed by a callback ref, so it
 * updates exactly when the pane mounts), attachment can never miss the moment
 * the container appears.
 */
export const usePierreDomVersion = (element: HTMLElement | null, enabled: boolean): number => {
  const [version, setVersion] = useState(0);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  useEffect(() => {
    if (!element || !enabled) return;

    const observers: Array<MutationObserver> = [];
    const observedRoots = new Set<Node>();

    const scheduleBump = (): void => {
      clearTimeout(debounceRef.current);
      debounceRef.current = setTimeout(() => setVersion((v) => v + 1), DEBOUNCE_MS);
    };

    const attachObserver = (root: Node): void => {
      if (observedRoots.has(root)) return;
      observedRoots.add(root);
      const observer = new MutationObserver(() => {
        // A mutation may have added new shadow hosts — re-scan before bumping.
        walkAndAttach(element);
        scheduleBump();
      });
      observer.observe(root, { childList: true, subtree: true });
      observers.push(observer);
    };

    const walkAndAttach = (node: Node): void => {
      if (node instanceof HTMLElement && node.shadowRoot) {
        attachObserver(node.shadowRoot);
        for (let child = node.shadowRoot.firstChild; child; child = child.nextSibling) {
          walkAndAttach(child);
        }
      }

      for (let child = node.firstChild; child; child = child.nextSibling) {
        walkAndAttach(child);
      }
    };

    attachObserver(element);
    walkAndAttach(element);
    // Signal once for content already present when we attached.
    scheduleBump();

    return (): void => {
      for (const observer of observers) observer.disconnect();
      clearTimeout(debounceRef.current);
    };
  }, [element, enabled]);

  return version;
};
