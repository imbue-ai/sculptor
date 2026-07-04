import "./focusFolderHighlight.scss";

import type { Virtualizer } from "@tanstack/react-virtual";
import { useAtomValue, useSetAtom } from "jotai";
import type { RefObject } from "react";
import { useCallback, useEffect, useRef } from "react";

import { mentionChipUnreachableToastAtom } from "~/common/state/atoms/toasts.ts";

import { focusFolderAtom } from "./atoms.ts";
import type { FlatRowEntry } from "./utils.ts";

const HIGHLIGHT_CLASS = "promptNavigatorHighlight";
const FADE_OUT_CLASS = "promptNavigatorHighlightFadeOut";
const FADE_IN_DURATION_MS = 500;
const FADE_OUT_DURATION_MS = 1500;

type Options = {
  workspaceId: string;
  flatRows: Array<FlatRowEntry>;
  virtualizer: Virtualizer<HTMLDivElement, Element>;
  scrollContainerRef: RefObject<HTMLDivElement | null>;
};

/**
 * Resolves a clicked folder path to a row in the (possibly compacted) tree.
 * Exact match wins; otherwise prefer a compacted row whose path starts with
 * `${target}/` so clicking an intermediate folder still lands on a visible row.
 */
const findRowIndex = (flatRows: Array<FlatRowEntry>, target: string): number => {
  const exact = flatRows.findIndex((r) => r.node.path === target);
  if (exact >= 0) return exact;
  return flatRows.findIndex((r) => r.node.path.startsWith(`${target}/`));
};

export const useFocusFolderHighlight = ({ workspaceId, flatRows, virtualizer, scrollContainerRef }: Options): void => {
  const request = useAtomValue(focusFolderAtom);
  const setUnreachableToast = useSetAtom(mentionChipUnreachableToastAtom);

  const highlightedElementRef = useRef<HTMLElement | null>(null);
  const fadeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const removeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const rafRef = useRef<number | null>(null);
  // Tracks the most recent request we've already resolved (hit or miss) so
  // we don't fire the toast or re-run the scroll/highlight on every flatRows
  // update while the same request is pending.
  const handledNonceRef = useRef<number | null>(null);

  // Clears any in-flight highlight. Called imperatively at the start of a
  // new highlight cycle and on unmount — deliberately NOT registered as an
  // effect return, because that cleanup fires on every deps change (e.g.
  // when `flatRows` updates due to background tree refreshes), which would
  // strip the class before the 500ms + 1500ms fade can play out.
  //
  // A stable useCallback (empty deps) since it closes over only stable refs
  // and module-level constants, so its identity never needs to change.
  const clearPending = useCallback((): void => {
    if (fadeTimeoutRef.current !== null) {
      clearTimeout(fadeTimeoutRef.current);
      fadeTimeoutRef.current = null;
    }

    if (removeTimeoutRef.current !== null) {
      clearTimeout(removeTimeoutRef.current);
      removeTimeoutRef.current = null;
    }

    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }

    if (highlightedElementRef.current) {
      highlightedElementRef.current.classList.remove(HIGHLIGHT_CLASS, FADE_OUT_CLASS);
      highlightedElementRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!request || request.workspaceId !== workspaceId) return;
    if (handledNonceRef.current === request.nonce) return;
    // Wait for the tree to load before deciding "not found" — an empty
    // flatRows list during initial mount would otherwise fire a false toast.
    if (flatRows.length === 0) return;

    const index = findRowIndex(flatRows, request.path);
    handledNonceRef.current = request.nonce;

    // Replace any still-running highlight from a prior request.
    clearPending();

    if (index < 0) {
      setUnreachableToast({ title: "Not viewable in Sculptor" });
      return;
    }

    virtualizer.scrollToIndex(index, { align: "center" });

    // Wait for the virtualizer to render the target row after scrolling.
    rafRef.current = requestAnimationFrame(() => {
      rafRef.current = requestAnimationFrame(() => {
        const container = scrollContainerRef.current;
        if (!container) return;
        const selector = `[data-tree-path="${CSS.escape(request.path)}"]`;
        const element = container.querySelector<HTMLElement>(selector);
        if (!element) return;

        highlightedElementRef.current = element;
        element.classList.add(HIGHLIGHT_CLASS);

        fadeTimeoutRef.current = setTimeout(() => {
          element.classList.remove(HIGHLIGHT_CLASS);
          element.classList.add(FADE_OUT_CLASS);

          removeTimeoutRef.current = setTimeout(() => {
            element.classList.remove(FADE_OUT_CLASS);
            highlightedElementRef.current = null;
          }, FADE_OUT_DURATION_MS);
        }, FADE_IN_DURATION_MS);
      });
    });

    // Intentionally no effect-return cleanup: we want in-flight highlights
    // to survive unrelated re-renders (e.g. flatRows churn from the agent
    // writing files). Cleanup happens imperatively above on a new nonce,
    // and in the unmount effect below.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [request?.nonce, request?.path, request?.workspaceId, workspaceId, flatRows]);

  // Final cleanup on unmount only — never tied to the main effect's deps.
  // clearPending is a stable useCallback, so the empty dep array is correct
  // and the effect still fires its cleanup solely on unmount.
  useEffect(() => {
    return (): void => clearPending();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
};
