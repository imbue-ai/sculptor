import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { activePanelPerZoneAtom, zoneAssignmentsAtom, zoneVisibilityAtom } from "~/components/panels/atoms.ts";

import { fileBrowserStateAtomFamily, focusFolderAtom, revealFolderAtom } from "./atoms.ts";

const WORKSPACE_ID = "workspace-1";

let store: ReturnType<typeof createStore>;

beforeEach(() => {
  localStorage.clear();
  store = createStore();
});

afterEach(() => {
  localStorage.clear();
  vi.useRealTimers();
});

describe("revealFolderAtom", () => {
  it("expands the target folder and all ancestor paths", () => {
    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src/components/chat" });

    const state = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));
    expect(new Set(state.expandedFolders)).toEqual(new Set(["src", "src/components", "src/components/chat"]));
  });

  it("strips trailing slashes before normalising", () => {
    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src/components/chat/" });

    const state = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));
    expect(new Set(state.expandedFolders)).toEqual(new Set(["src", "src/components", "src/components/chat"]));

    const focus = store.get(focusFolderAtom);
    expect(focus?.path).toBe("src/components/chat");
  });

  it("strips a leading './' prefix so path-mode mentions resolve against the tree", () => {
    // When the user drills into a folder via Tab in the @-mention picker,
    // the resulting chip id is "@./foo/bar/" (path-mode). The file tree's
    // node paths are workspace-relative without the "./" prefix, so the
    // prefix must be stripped or the reveal lookup will miss and the
    // "not viewable" toast will fire on a valid folder.
    store.set(revealFolderAtom, {
      workspaceId: WORKSPACE_ID,
      path: "./sculptor/agent_docs/chat_redesign/debug_view/",
    });

    const state = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));
    expect(new Set(state.expandedFolders)).toEqual(
      new Set([
        "sculptor",
        "sculptor/agent_docs",
        "sculptor/agent_docs/chat_redesign",
        "sculptor/agent_docs/chat_redesign/debug_view",
      ]),
    );

    const focus = store.get(focusFolderAtom);
    expect(focus?.path).toBe("sculptor/agent_docs/chat_redesign/debug_view");
  });

  it("is a no-op for empty paths", () => {
    const stateBefore = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "" });

    const stateAfter = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));
    expect(stateAfter.expandedFolders).toEqual(stateBefore.expandedFolders);
    expect(store.get(focusFolderAtom)).toBeNull();
  });

  it("is a no-op for slash-only paths", () => {
    const stateBefore = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "/" });

    const stateAfter = store.get(fileBrowserStateAtomFamily(WORKSPACE_ID));
    expect(stateAfter.expandedFolders).toEqual(stateBefore.expandedFolders);
    expect(store.get(focusFolderAtom)).toBeNull();
  });

  it("sets the files panel as active in its assigned zone", () => {
    store.set(zoneAssignmentsAtom, { files: "top-left" });
    store.set(activePanelPerZoneAtom, { "top-left": "info" });

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src" });

    expect(store.get(activePanelPerZoneAtom)["top-left"]).toBe("files");
  });

  it("marks the files panel's zone visible", () => {
    store.set(zoneAssignmentsAtom, { files: "top-left" });
    store.set(zoneVisibilityAtom, { "top-left": false });

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src" });

    expect(store.get(zoneVisibilityAtom)["top-left"]).toBe(true);
  });

  it("leaves zone state alone when the files panel is unassigned", () => {
    store.set(zoneAssignmentsAtom, {});
    const activeBefore = store.get(activePanelPerZoneAtom);
    const visibilityBefore = store.get(zoneVisibilityAtom);

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src" });

    expect(store.get(activePanelPerZoneAtom)).toBe(activeBefore);
    expect(store.get(zoneVisibilityAtom)).toBe(visibilityBefore);
  });

  it("does not overwrite zone state when already active and visible", () => {
    store.set(zoneAssignmentsAtom, { files: "top-left" });
    store.set(activePanelPerZoneAtom, { "top-left": "files" });
    store.set(zoneVisibilityAtom, { "top-left": true });

    const activeBefore = store.get(activePanelPerZoneAtom);
    const visibilityBefore = store.get(zoneVisibilityAtom);

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src" });

    expect(store.get(activePanelPerZoneAtom)).toBe(activeBefore);
    expect(store.get(zoneVisibilityAtom)).toBe(visibilityBefore);
  });

  it("emits a focus request with workspace id, normalised path, and numeric nonce", () => {
    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src/components/chat/" });

    const focus = store.get(focusFolderAtom);
    expect(focus).not.toBeNull();
    expect(focus?.workspaceId).toBe(WORKSPACE_ID);
    expect(focus?.path).toBe("src/components/chat");
    expect(typeof focus?.nonce).toBe("number");
  });

  it("emits a different nonce on each call", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date(1_700_000_000_000));

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src" });
    const firstNonce = store.get(focusFolderAtom)?.nonce;

    vi.advanceTimersByTime(1);

    store.set(revealFolderAtom, { workspaceId: WORKSPACE_ID, path: "src" });
    const secondNonce = store.get(focusFolderAtom)?.nonce;

    expect(firstNonce).toBeDefined();
    expect(secondNonce).toBeDefined();
    expect(secondNonce).not.toBe(firstNonce);
    expect(secondNonce!).toBeGreaterThan(firstNonce!);
  });
});
