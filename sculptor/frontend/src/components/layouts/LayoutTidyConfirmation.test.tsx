import { Theme } from "@radix-ui/themes";
import { act, cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";
import type { CapturedLayout, SavedLayout, WorkspaceLayoutState } from "~/components/sections/persistence/types.ts";
import { EMPTY_WORKSPACE_LAYOUT, SAVED_LAYOUT_VERSION } from "~/components/sections/persistence/types.ts";
import { tidyConfirmationSuppressedAtom } from "~/components/sections/savedLayoutAtoms.ts";
import { activeWorkspaceIdAtom, workspaceLayoutAtom } from "~/components/sections/sectionAtoms.ts";
import type { PanelId, SubSectionId } from "~/components/sections/sectionTypes.ts";
import { SYSTEM_DEFAULT_LAYOUT } from "~/components/sections/systemDefaultLayout.ts";
import { layoutTidyTargetAtom } from "~/components/sections/transientAtoms.ts";

import { LayoutTidyConfirmation } from "./LayoutTidyConfirmation.tsx";
import { saveLayoutModalRequestAtom } from "./layoutUiAtoms.ts";

// Dynamic (multi-instance) panels: the tidy closure never includes these, so they
// stand in as the agent/terminal that must survive a tidy.
const AGENT_PANEL: PanelId = "agent:1";
const TERMINAL_PANEL: PanelId = "terminal:ws-1:1";

type Store = ReturnType<typeof createStore>;

const withStore = (store: Store, children: ReactNode): ReactElement => (
  <Provider store={store}>
    <Theme>{children}</Theme>
  </Provider>
);

// A store hydrated for the ACTIVE workspace: the tidy target reads its captured
// panels, and computeTidyClosure diffs them against the live workspace layout — so
// both the workspace arrangement and the pending target have to be seeded.
function storeWith(layout: Partial<WorkspaceLayoutState>, target: SavedLayout | null, workspaceId = "ws-1"): Store {
  const store = createStore();
  store.set(activeWorkspaceIdAtom, workspaceId);
  store.set(workspaceLayoutAtom, { ...EMPTY_WORKSPACE_LAYOUT, ...layout });
  store.set(layoutTidyTargetAtom, target);
  return store;
}

// A CapturedLayout that declares exactly `panelIds` as its statics. The tidy closure
// is (open statics) − (declared), so a target's declared set is all that shapes it;
// the sub-section values are arbitrary because computeTidyClosure reads only the keys.
function capturedDeclaring(panelIds: ReadonlyArray<PanelId>): CapturedLayout {
  const placement: Partial<Record<PanelId, SubSectionId>> = {};
  for (const id of panelIds) {
    placement[id] = "left";
  }
  return { ...SYSTEM_DEFAULT_LAYOUT.captured, placement, order: {}, activePanel: {} };
}

function makeUserLayout(id: string, declares: ReadonlyArray<PanelId>): SavedLayout {
  return { id, name: `Layout ${id}`, version: SAVED_LAYOUT_VERSION, captured: capturedDeclaring(declares) };
}

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  cleanup();
});

describe("LayoutTidyConfirmation", () => {
  it("renders no dialog and clears the target when nothing would close", () => {
    const store = storeWith(
      {
        placement: { files: "left", [AGENT_PANEL]: "center" },
        order: { left: ["files"], center: [AGENT_PANEL] },
        expanded: { left: true },
      },
      // Declares the only open static (Files); the agent is multi-instance and never
      // in the closure, so nothing is left to close.
      makeUserLayout("declares-files", ["files"]),
    );

    render(withStore(store, <LayoutTidyConfirmation />));

    expect(screen.queryByTestId(ElementIds.LAYOUT_TIDY_DIALOG)).toBeNull();
    expect(store.get(layoutTidyTargetAtom)).toBeNull();
    // No panel closed — the workspace arrangement is untouched.
    expect(store.get(workspaceLayoutAtom).placement).toEqual({ files: "left", [AGENT_PANEL]: "center" });
  });

  it("renders the dialog with a singular count when one panel would close", () => {
    const store = storeWith(
      {
        placement: { files: "left", browser: "right" },
        order: { left: ["files"], right: ["browser"] },
        expanded: { left: true, right: true },
      },
      makeUserLayout("declares-files", ["files"]),
    );

    render(withStore(store, <LayoutTidyConfirmation />));

    expect(screen.getByTestId(ElementIds.LAYOUT_TIDY_DIALOG)).toBeTruthy();
    expect(screen.getByText("Close 1 panel?")).toBeTruthy();
    expect(screen.getByTestId(ElementIds.LAYOUT_TIDY_CONFIRM).textContent).toBe("Close 1 panel");
  });

  it("pluralizes the count when more than one panel would close", () => {
    const store = storeWith(
      {
        placement: { browser: "right", notes: "right" },
        order: { right: ["browser", "notes"] },
        expanded: { right: true },
      },
      makeUserLayout("declares-nothing", []),
    );

    render(withStore(store, <LayoutTidyConfirmation />));

    expect(screen.getByText("Close 2 panels?")).toBeTruthy();
    expect(screen.getByTestId(ElementIds.LAYOUT_TIDY_CONFIRM).textContent).toBe("Close 2 panels");
  });

  it("closes only the undeclared statics on confirm, sparing agents and terminals", async () => {
    const user = userEvent.setup();
    const store = storeWith(
      {
        placement: { files: "left", browser: "right", [AGENT_PANEL]: "center", [TERMINAL_PANEL]: "bottom" },
        order: { left: ["files"], right: ["browser"], center: [AGENT_PANEL], bottom: [TERMINAL_PANEL] },
        expanded: { left: true, right: true, bottom: true },
      },
      makeUserLayout("declares-files", ["files"]),
    );

    render(withStore(store, <LayoutTidyConfirmation />));
    await user.click(screen.getByTestId(ElementIds.LAYOUT_TIDY_CONFIRM));

    const { placement } = store.get(workspaceLayoutAtom);
    // Browser is the only undeclared static, so it is the only thing that closes.
    expect(placement.browser).toBeUndefined();
    expect(placement.files).toBe("left");
    expect(placement[AGENT_PANEL]).toBe("center");
    expect(placement[TERMINAL_PANEL]).toBe("bottom");
    expect(store.get(layoutTidyTargetAtom)).toBeNull();
    // No "don't show again" tick, so the global preference stays off.
    expect(store.get(tidyConfirmationSuppressedAtom)).toBe(false);
  });

  it("also sets the global suppression when 'Don't show this again' is ticked", async () => {
    const user = userEvent.setup();
    const store = storeWith(
      {
        placement: { files: "left", browser: "right" },
        order: { left: ["files"], right: ["browser"] },
        expanded: { left: true, right: true },
      },
      makeUserLayout("declares-files", ["files"]),
    );

    render(withStore(store, <LayoutTidyConfirmation />));
    await user.click(screen.getByTestId(ElementIds.LAYOUT_TIDY_SUPPRESS_CHECKBOX));
    await user.click(screen.getByTestId(ElementIds.LAYOUT_TIDY_CONFIRM));

    expect(store.get(tidyConfirmationSuppressedAtom)).toBe(true);
    expect(store.get(workspaceLayoutAtom).placement.browser).toBeUndefined();
    expect(store.get(layoutTidyTargetAtom)).toBeNull();
  });

  it("clears the target and closes nothing on cancel, leaving suppression off", async () => {
    const user = userEvent.setup();
    const placement = { files: "left" as SubSectionId, browser: "right" as SubSectionId };
    const store = storeWith(
      { placement, order: { left: ["files"], right: ["browser"] }, expanded: { left: true, right: true } },
      makeUserLayout("declares-files", ["files"]),
    );

    render(withStore(store, <LayoutTidyConfirmation />));
    await user.click(screen.getByTestId(ElementIds.LAYOUT_TIDY_CANCEL));

    expect(store.get(layoutTidyTargetAtom)).toBeNull();
    expect(store.get(workspaceLayoutAtom).placement).toEqual(placement);
    expect(store.get(tidyConfirmationSuppressedAtom)).toBe(false);
  });

  it("resets the checkbox when the target changes while the dialog stays mounted", async () => {
    const user = userEvent.setup();
    const store = storeWith(
      {
        placement: { files: "left", browser: "right" },
        order: { left: ["files"], right: ["browser"] },
        expanded: { left: true, right: true },
      },
      makeUserLayout("first", ["files"]),
    );

    render(withStore(store, <LayoutTidyConfirmation />));
    await user.click(screen.getByTestId(ElementIds.LAYOUT_TIDY_SUPPRESS_CHECKBOX));
    expect(screen.getByTestId(ElementIds.LAYOUT_TIDY_SUPPRESS_CHECKBOX)).toBeChecked();

    // Swapping to a different target id (dialog never unmounts) must drop the tick so a
    // fresh confirmation never inherits the previous one's "don't ask again".
    act(() => {
      store.set(layoutTidyTargetAtom, makeUserLayout("second", ["files"]));
    });

    expect(screen.getByTestId(ElementIds.LAYOUT_TIDY_SUPPRESS_CHECKBOX)).not.toBeChecked();
  });

  it("hides the edit link for a built-in (system) layout target", () => {
    const store = storeWith(
      {
        placement: { files: "left", changes: "left", commits: "left", browser: "right" },
        order: { left: ["files", "changes", "commits"], right: ["browser"] },
        expanded: { left: true, right: true },
      },
      // System Default declares Files/Changes/Commits; Browser is undeclared, so the
      // dialog still opens — but built-ins are read-only and offer no edit escape.
      SYSTEM_DEFAULT_LAYOUT,
    );

    render(withStore(store, <LayoutTidyConfirmation />));

    expect(screen.getByTestId(ElementIds.LAYOUT_TIDY_DIALOG)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.LAYOUT_TIDY_EDIT_LINK)).toBeNull();
  });

  it("hands a user layout target off to the edit form when the edit link is clicked", async () => {
    const user = userEvent.setup();
    const target = makeUserLayout("mine", ["files"]);
    const store = storeWith(
      {
        placement: { files: "left", browser: "right" },
        order: { left: ["files"], right: ["browser"] },
        expanded: { left: true, right: true },
      },
      target,
    );

    render(withStore(store, <LayoutTidyConfirmation />));
    await user.click(screen.getByTestId(ElementIds.LAYOUT_TIDY_EDIT_LINK));

    expect(store.get(saveLayoutModalRequestAtom)).toEqual({ mode: "edit", layout: target });
    expect(store.get(layoutTidyTargetAtom)).toBeNull();
  });
});
