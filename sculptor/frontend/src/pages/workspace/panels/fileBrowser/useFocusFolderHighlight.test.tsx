import type { Virtualizer } from "@tanstack/react-virtual";
import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode, RefObject } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { mentionChipUnreachableToastAtom } from "~/common/state/atoms/toasts.ts";

import { focusFolderAtom } from "./atoms.ts";
import { useFocusFolderHighlight } from "./useFocusFolderHighlight.ts";
import type { FlatRowEntry } from "./utils.ts";

const HIGHLIGHT_CLASS = "promptNavigatorHighlight";

type TestStore = ReturnType<typeof createStore>;

const WORKSPACE_ID = "ws-1";

const makeRow = (path: string, type: "file" | "directory"): FlatRowEntry => ({
  depth: 0,
  node: { name: path.split("/").pop() ?? path, path, type, children: [] } as FlatRowEntry["node"],
});

const makeVirtualizer = (): { scrollToIndex: ReturnType<typeof vi.fn> } => ({
  scrollToIndex: vi.fn(),
});

const renderFocusFolderHook = ({
  store,
  flatRows,
  virtualizer,
  scrollContainerRef,
}: {
  store: TestStore;
  flatRows: Array<FlatRowEntry>;
  virtualizer: ReturnType<typeof makeVirtualizer>;
  scrollContainerRef: RefObject<HTMLDivElement>;
}): void => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );
  renderHook(
    () =>
      useFocusFolderHighlight({
        workspaceId: WORKSPACE_ID,
        flatRows,
        virtualizer: virtualizer as unknown as Virtualizer<HTMLDivElement, Element>,
        scrollContainerRef,
      }),
    { wrapper },
  );
};

describe("useFocusFolderHighlight", () => {
  it("fires the 'not viewable' toast when the requested row is not in the tree", () => {
    const store = createStore();
    const flatRows = [makeRow("src", "directory"), makeRow("README.md", "file")];
    store.set(focusFolderAtom, { workspaceId: WORKSPACE_ID, path: "hidden-folder", nonce: 1 });

    renderFocusFolderHook({
      store,
      flatRows,
      virtualizer: makeVirtualizer(),
      scrollContainerRef: { current: null },
    });

    expect(store.get(mentionChipUnreachableToastAtom)).toEqual({ title: "Not viewable in Sculptor" });
  });

  it("does not fire the toast when the requested row IS in the tree", () => {
    const store = createStore();
    const flatRows = [makeRow("src", "directory")];
    store.set(focusFolderAtom, { workspaceId: WORKSPACE_ID, path: "src", nonce: 1 });
    const virtualizer = makeVirtualizer();

    renderFocusFolderHook({
      store,
      flatRows,
      virtualizer,
      scrollContainerRef: { current: null },
    });

    expect(store.get(mentionChipUnreachableToastAtom)).toBeNull();
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(0, { align: "center" });
  });

  it("does not fire the toast while flatRows is still empty (tree loading)", () => {
    const store = createStore();
    store.set(focusFolderAtom, { workspaceId: WORKSPACE_ID, path: "anything", nonce: 1 });

    renderFocusFolderHook({
      store,
      flatRows: [],
      virtualizer: makeVirtualizer(),
      scrollContainerRef: { current: null },
    });

    expect(store.get(mentionChipUnreachableToastAtom)).toBeNull();
  });

  it("ignores requests for a different workspace", () => {
    const store = createStore();
    const flatRows = [makeRow("src", "directory")];
    store.set(focusFolderAtom, { workspaceId: "other-ws", path: "hidden-folder", nonce: 1 });

    renderFocusFolderHook({
      store,
      flatRows,
      virtualizer: makeVirtualizer(),
      scrollContainerRef: { current: null },
    });

    expect(store.get(mentionChipUnreachableToastAtom)).toBeNull();
  });

  describe("highlight survives unrelated flatRows churn", () => {
    afterEach(() => {
      vi.unstubAllGlobals();
    });

    it("keeps the highlight class applied when flatRows re-renders mid-animation", () => {
      // Make RAF synchronous so we can observe the post-scroll highlight
      // immediately after render, without juggling fake timers + jsdom's
      // setTimeout-backed RAF implementation.
      vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
        cb(0);
        return 0;
      });
      vi.stubGlobal("cancelAnimationFrame", () => {});

      const store = createStore();
      const container = document.createElement("div");
      const row = document.createElement("div");
      row.setAttribute("data-tree-path", "src");
      container.appendChild(row);
      document.body.appendChild(container);

      try {
        store.set(focusFolderAtom, { workspaceId: WORKSPACE_ID, path: "src", nonce: 1 });

        const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
          <Provider store={store}>{children}</Provider>
        );

        const { rerender } = renderHook(
          ({ flatRows }: { flatRows: Array<FlatRowEntry> }) =>
            useFocusFolderHighlight({
              workspaceId: WORKSPACE_ID,
              flatRows,
              virtualizer: makeVirtualizer() as unknown as Virtualizer<HTMLDivElement, Element>,
              scrollContainerRef: { current: container },
            }),
          {
            wrapper,
            initialProps: { flatRows: [makeRow("src", "directory")] },
          },
        );

        expect(row.classList.contains(HIGHLIGHT_CLASS)).toBe(true);

        // Simulate an unrelated tree refresh — new flatRows reference, same
        // nonce. The effect's deps change, but the in-flight highlight must
        // not be stripped.
        rerender({ flatRows: [makeRow("src", "directory"), makeRow("new_file.txt", "file")] });

        expect(row.classList.contains(HIGHLIGHT_CLASS)).toBe(true);
      } finally {
        container.remove();
      }
    });
  });

  it("finds compacted-folder rows (prefix match) without firing the toast", () => {
    const store = createStore();
    // When `components` has a single folder child `chat`, compactSingleChildFolders
    // produces a row whose path is `src/components/chat` and name `components/chat`.
    // Clicking an @-mention for `src/components` must still resolve to that row.
    const flatRows = [makeRow("src", "directory"), makeRow("src/components/chat", "directory")];
    store.set(focusFolderAtom, { workspaceId: WORKSPACE_ID, path: "src/components", nonce: 1 });
    const virtualizer = makeVirtualizer();

    renderFocusFolderHook({
      store,
      flatRows,
      virtualizer,
      scrollContainerRef: { current: null },
    });

    expect(store.get(mentionChipUnreachableToastAtom)).toBeNull();
    expect(virtualizer.scrollToIndex).toHaveBeenCalledWith(1, { align: "center" });
  });
});
