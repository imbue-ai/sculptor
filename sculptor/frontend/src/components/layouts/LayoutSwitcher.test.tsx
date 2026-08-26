// Component tests for the switcher's capture-phase keyboard machine and its ⌘J
// more-options DropdownMenu. Drives the real component under a jotai store hydrated
// the way layoutActions.test.ts seeds one; keyboard shortcuts are pressed as raw
// window keydowns so they hit the capture-phase listener exactly like production.

import { Theme } from "@radix-ui/themes";
import { act, cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import type { SavedLayout } from "~/components/sections/persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "~/components/sections/persistence/types.ts";
import { appliedLayoutIdAtom, layoutMruAtom, savedLayoutsAtom } from "~/components/sections/savedLayoutAtoms.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import { SYSTEM_DEFAULT_LAYOUT, SYSTEM_DEFAULT_LAYOUT_ID } from "~/components/sections/systemDefaultLayout.ts";
import type * as ElectronUtils from "~/electron/utils.ts";

import { LayoutSwitcher } from "./LayoutSwitcher.tsx";
import { layoutsSwitcherOpenAtom, saveLayoutModalRequestAtom } from "./layoutUiAtoms.ts";

// Force the platform modifier to Cmd so a "Meta+…" binding matches a metaKey press
// regardless of the host OS the suite runs on (jsdom reports no platform).
vi.mock("~/electron/utils.ts", async (importOriginal) => {
  const actual = await importOriginal<typeof ElectronUtils>();
  return { ...actual, isMac: (): boolean => true };
});

type Store = ReturnType<typeof createStore>;

const withStore = (store: Store, children: ReactNode): ReactElement => (
  <Provider store={store}>
    <Theme>{children}</Theme>
  </Provider>
);

function makeLayout(id: string, name: string): SavedLayout {
  return { id, name, version: SAVED_LAYOUT_VERSION, captured: SYSTEM_DEFAULT_LAYOUT.captured };
}

// Three uniquely-named user layouts so a "zeta" query isolates them from the built-in
// System Default + presets (whose names share no substring with "zeta").
const ZETA_LAYOUTS: ReadonlyArray<SavedLayout> = [
  makeLayout("zeta-a", "Zeta Alpha"),
  makeLayout("zeta-b", "Zeta Bravo"),
  makeLayout("zeta-c", "Zeta Charlie"),
];

// A store hydrated for the active workspace with the switcher open, so applying a
// layout has an appliedLayoutId/MRU to write and `close()` has a flag to flip.
function makeStore(saved: ReadonlyArray<SavedLayout> = ZETA_LAYOUTS): Store {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, "ws-1");
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT });
  store.set(savedLayoutsAtom, saved);
  store.set(layoutsSwitcherOpenAtom, true);
  return store;
}

// Fire a raw window-level keydown, the way the OS delivers one to the capture-phase
// listener. Dispatched on document.body so window's capture handler runs first.
function press(key: string, modifiers: { meta?: boolean; shift?: boolean } = {}): void {
  act(() => {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", {
        key,
        metaKey: modifiers.meta ?? false,
        shiftKey: modifiers.shift ?? false,
        bubbles: true,
        cancelable: true,
      }),
    );
  });
}

function setQuery(value: string): void {
  const input = screen.getByTestId(ElementIds.LAYOUTS_SWITCHER_SEARCH_INPUT);
  act(() => {
    // React tracks the value on the input node, so set it through the native setter
    // before dispatching `input` — otherwise the controlled onChange sees no change.
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")?.set;
    setter?.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
  });
}

const rowIds = (): Array<string> =>
  screen.getAllByTestId(ElementIds.LAYOUTS_SWITCHER_ROW).map((row) => row.getAttribute("data-layout-id") ?? "");

const selectedRowId = (): string | undefined =>
  screen
    .getAllByTestId(ElementIds.LAYOUTS_SWITCHER_ROW)
    .find((row) => row.getAttribute("data-selected") === "true")
    ?.getAttribute("data-layout-id") ?? undefined;

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("LayoutSwitcher keyboard machine", () => {
  it("clears the query on Escape while text remains, then closes on the next Escape", () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));

    setQuery("zeta");
    const input = screen.getByTestId(ElementIds.LAYOUTS_SWITCHER_SEARCH_INPUT) as HTMLInputElement;
    expect(input.value).toBe("zeta");

    // First Escape clears the query without closing the switcher.
    press("Escape");
    expect(input.value).toBe("");
    expect(store.get(layoutsSwitcherOpenAtom)).toBe(true);

    // With the query empty, Escape closes the switcher.
    press("Escape");
    expect(store.get(layoutsSwitcherOpenAtom)).toBe(false);
  });

  it("advances the highlight and wraps on ⌘⇧L", () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));
    setQuery("zeta");
    expect(rowIds()).toEqual(["zeta-a", "zeta-b", "zeta-c"]);

    expect(selectedRowId()).toBe("zeta-a");
    press("L", { meta: true, shift: true });
    expect(selectedRowId()).toBe("zeta-b");
    press("L", { meta: true, shift: true });
    expect(selectedRowId()).toBe("zeta-c");
    // Wraps back to the top.
    press("L", { meta: true, shift: true });
    expect(selectedRowId()).toBe("zeta-a");
  });

  it("moves the highlight with Arrow Down/Up and wraps at both ends", () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));
    setQuery("zeta");
    expect(selectedRowId()).toBe("zeta-a");

    press("ArrowDown");
    expect(selectedRowId()).toBe("zeta-b");
    press("ArrowDown");
    expect(selectedRowId()).toBe("zeta-c");
    press("ArrowDown"); // wraps to the first row
    expect(selectedRowId()).toBe("zeta-a");
    press("ArrowUp"); // wraps to the last row
    expect(selectedRowId()).toBe("zeta-c");
  });

  it("applies the highlighted layout on Enter", () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));
    setQuery("zeta");
    expect(selectedRowId()).toBe("zeta-a");

    press("Enter");

    expect(store.get(appliedLayoutIdAtom)).toBe("zeta-a");
    expect(store.get(layoutMruAtom)[0]).toBe("zeta-a");
    // Applying closes the switcher.
    expect(store.get(layoutsSwitcherOpenAtom)).toBe(false);
  });

  it("opens the save dialog on ⌘S", () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));

    press("s", { meta: true });

    expect(store.get(saveLayoutModalRequestAtom)).toEqual({ mode: "create" });
    expect(store.get(layoutsSwitcherOpenAtom)).toBe(false);
  });
});

describe("LayoutSwitcher more-options menu", () => {
  it("toggles the ⌘J menu open and closed while the switcher stays open", async () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));
    setQuery("zeta");

    press("j", { meta: true });
    // The menu mounts with its shared descriptor items.
    expect((await screen.findAllByTestId(ElementIds.LAYOUTS_MORE_OPTIONS_APPLY)).length).toBeGreaterThan(0);

    press("j", { meta: true });
    // ⌘J again closes the menu, but the switcher itself stays mounted and open.
    await waitFor(() => expect(screen.queryAllByTestId(ElementIds.LAYOUTS_MORE_OPTIONS_APPLY)).toHaveLength(0));
    expect(screen.getByTestId(ElementIds.LAYOUTS_SWITCHER_SEARCH_INPUT)).toBeTruthy();
    expect(store.get(layoutsSwitcherOpenAtom)).toBe(true);
  });

  it("renders read-only actions disabled when System Default is highlighted", async () => {
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));
    // Isolate the built-in System Default row and highlight it.
    setQuery("system");
    expect(selectedRowId()).toBe(SYSTEM_DEFAULT_LAYOUT_ID);

    press("j", { meta: true });

    const deleteItems = await screen.findAllByTestId(ElementIds.LAYOUTS_MORE_OPTIONS_DELETE);
    expect(deleteItems.some((el) => el.getAttribute("aria-disabled") === "true")).toBe(true);
    const editItems = screen.getAllByTestId(ElementIds.LAYOUTS_MORE_OPTIONS_EDIT);
    expect(editItems.some((el) => el.getAttribute("aria-disabled") === "true")).toBe(true);
  });

  it("applies the highlighted layout when Apply is chosen from the menu", async () => {
    const user = userEvent.setup();
    const store = makeStore();
    render(withStore(store, <LayoutSwitcher />));
    setQuery("zeta");
    expect(selectedRowId()).toBe("zeta-a");

    press("j", { meta: true });
    const applyItems = await screen.findAllByTestId(ElementIds.LAYOUTS_MORE_OPTIONS_APPLY);
    await user.click(applyItems[0]);

    expect(store.get(appliedLayoutIdAtom)).toBe("zeta-a");
    expect(store.get(layoutMruAtom)[0]).toBe("zeta-a");
  });
});
