import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";
import {
  EXPLORER_LIST_MAX_WIDTH_PX,
  EXPLORER_LIST_MIN_WIDTH_PX,
  explorerListWidthAtom,
} from "~/components/sections/sectionAtoms.ts";

import { ExplorerLayout } from "./ExplorerLayout";

// jsdom does not implement PointerEvent; fall back to MouseEvent so
// fireEvent.pointerDown's `button`/`clientX` reach the ResizeHandle handler.
beforeAll(() => {
  if (typeof window.PointerEvent === "undefined") {
    (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
  }
});

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
  document.body.classList.remove("sculptor-resizing");
});

type JotaiStore = ReturnType<typeof createStore>;

const renderLayout = (store: JotaiStore, listTestId = "list-slot"): void => {
  render(
    <Provider store={store}>
      <Theme>
        <ExplorerLayout
          list={<div data-testid={listTestId}>list</div>}
          detail={(toggle) => (
            <div data-testid="detail-slot">
              {toggle}
              detail
            </div>
          )}
        />
      </Theme>
    </Provider>,
  );
};

const getResizeHandle = (): HTMLElement => screen.getByRole("separator", { name: "Resize file list" });

const getListPane = (listTestId = "list-slot"): HTMLElement => {
  const pane = screen.getByTestId(listTestId).parentElement;
  expect(pane).not.toBeNull();
  // The non-null assertion is safe: the expect above fails first.
  return pane as HTMLElement;
};

// Drag the divider horizontally by deltaX px (positive widens the list). The
// handle applies deltas relative to the width captured at pointer-down.
const dragHandleBy = (deltaX: number): void => {
  const handle = getResizeHandle();
  fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
  fireEvent.pointerMove(window, { clientX: deltaX, clientY: 0 });
  fireEvent.pointerUp(window, { clientX: deltaX, clientY: 0 });
};

describe("ExplorerLayout — drag-resizable shared sidebar", () => {
  it("renders both slots", () => {
    renderLayout(createStore());
    expect(screen.getByTestId("list-slot")).toBeInTheDocument();
    expect(screen.getByTestId("detail-slot")).toBeInTheDocument();
  });

  it("renders a drag-resize divider between the list and the viewer", () => {
    renderLayout(createStore());
    const handle = getResizeHandle();
    expect(handle).toBeInTheDocument();
    expect(handle).toHaveAttribute("aria-orientation", "vertical");
  });

  it("sizes the list pane from the shared width atom", () => {
    const store = createStore();
    store.set(explorerListWidthAtom, 300);
    renderLayout(store);
    expect(getListPane().style.width).toBe("300px");
  });

  it("dragging the divider updates the pane width and writes it to the shared atom", () => {
    const store = createStore();
    store.set(explorerListWidthAtom, 240);
    renderLayout(store);

    dragHandleBy(60);

    expect(getListPane().style.width).toBe("300px");
    expect(store.get(explorerListWidthAtom)).toBe(300);
  });

  it("clamps the width at the minimum when dragged far left", () => {
    const store = createStore();
    store.set(explorerListWidthAtom, 240);
    renderLayout(store);

    dragHandleBy(-1000);

    expect(getListPane().style.width).toBe(`${EXPLORER_LIST_MIN_WIDTH_PX}px`);
    expect(store.get(explorerListWidthAtom)).toBe(EXPLORER_LIST_MIN_WIDTH_PX);
  });

  it("clamps the width at the maximum when dragged far right", () => {
    const store = createStore();
    store.set(explorerListWidthAtom, 240);
    renderLayout(store);

    dragHandleBy(1000);

    expect(getListPane().style.width).toBe(`${EXPLORER_LIST_MAX_WIDTH_PX}px`);
    expect(store.get(explorerListWidthAtom)).toBe(EXPLORER_LIST_MAX_WIDTH_PX);
  });

  it("shares one width across simultaneously mounted layouts (Files/Changes/Commits)", () => {
    // Two layouts in the same store stand in for two of the three panels; the
    // width is one shared atom, so dragging either divider resizes both.
    const store = createStore();
    store.set(explorerListWidthAtom, 240);
    renderLayout(store, "list-slot-a");
    renderLayout(store, "list-slot-b");

    const [handleA] = screen.getAllByRole("separator", { name: "Resize file list" });
    fireEvent.pointerDown(handleA, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerMove(window, { clientX: 40, clientY: 0 });
    fireEvent.pointerUp(window, { clientX: 40, clientY: 0 });

    expect(getListPane("list-slot-a").style.width).toBe("280px");
    expect(getListPane("list-slot-b").style.width).toBe("280px");
    expect(store.get(explorerListWidthAtom)).toBe(280);
  });

  it("hides the divider while the sidebar is collapsed and restores it on show", () => {
    renderLayout(createStore());

    fireEvent.click(screen.getByTestId(ElementIds.FILE_BROWSER_HIDE_TREE_BTN));
    expect(screen.queryByRole("separator", { name: "Resize file list" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("list-slot")).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId(ElementIds.DIFF_HEADER_SHOW_TREE_BTN));
    expect(getResizeHandle()).toBeInTheDocument();
    expect(screen.getByTestId("list-slot")).toBeInTheDocument();
  });
});
