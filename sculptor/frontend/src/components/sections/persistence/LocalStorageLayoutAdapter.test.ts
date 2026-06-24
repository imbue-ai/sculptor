import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalStorageLayoutAdapter } from "./LocalStorageLayoutAdapter.ts";
import type { LayoutScope, WorkspaceLayoutState } from "./types.ts";

const WS_SCOPE: LayoutScope = { kind: "workspace", workspaceId: "ws-1" };
const GLOBAL_SCOPE: LayoutScope = { kind: "global" };

function makeWorkspaceLayout(activePanel: string): WorkspaceLayoutState {
  return {
    placement: { [activePanel]: "center" },
    order: { center: [activePanel] },
    activePanel: { center: activePanel },
    expanded: {},
    splits: {},
    activeSubSection: "center",
  };
}

describe("LocalStorageLayoutAdapter", () => {
  let adapter: LocalStorageLayoutAdapter;

  beforeEach(() => {
    localStorage.clear();
    adapter = new LocalStorageLayoutAdapter();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("returns undefined for a missing key", () => {
    expect(adapter.read(WS_SCOPE)).toBeUndefined();
    expect(adapter.read(GLOBAL_SCOPE)).toBeUndefined();
  });

  it("round-trips a written snapshot after flush", () => {
    const snapshot = makeWorkspaceLayout("agent:1");
    adapter.write(WS_SCOPE, snapshot);
    adapter.flush();
    expect(adapter.read(WS_SCOPE)).toEqual(snapshot);
  });

  it("uses consolidated, scope-specific keys", () => {
    adapter.write(WS_SCOPE, makeWorkspaceLayout("files"));
    adapter.flush();
    expect(localStorage.getItem("sculptor-layout-ws-ws-1")).not.toBeNull();
    expect(localStorage.getItem("sculptor-layout-global")).toBeNull();
  });

  it("returns undefined and does not throw on corrupt JSON", () => {
    localStorage.setItem("sculptor-layout-ws-ws-1", "{not valid json");
    expect(() => adapter.read(WS_SCOPE)).not.toThrow();
    expect(adapter.read(WS_SCOPE)).toBeUndefined();
  });

  it("remove clears a persisted scope and drops a pending write", () => {
    adapter.write(WS_SCOPE, makeWorkspaceLayout("files"));
    adapter.flush();
    expect(adapter.read(WS_SCOPE)).toBeDefined();
    adapter.remove(WS_SCOPE);
    expect(adapter.read(WS_SCOPE)).toBeUndefined();
  });

  it("coalesces rapid writes to the same key into one setItem with the last value", () => {
    vi.useFakeTimers();
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    adapter.write(WS_SCOPE, makeWorkspaceLayout("a"));
    adapter.write(WS_SCOPE, makeWorkspaceLayout("b"));
    adapter.write(WS_SCOPE, makeWorkspaceLayout("c"));
    expect(setItemSpy).not.toHaveBeenCalled();
    vi.advanceTimersByTime(1000);
    expect(setItemSpy).toHaveBeenCalledTimes(1);
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("c"));
  });

  it("flush persists pending writes synchronously (e.g. on beforeunload)", () => {
    vi.useFakeTimers();
    adapter.write(WS_SCOPE, makeWorkspaceLayout("x"));
    adapter.write(GLOBAL_SCOPE, {
      sectionSizes: { left: 25, right: 25, bottom: 25 },
      sidebarWidthPx: 300,
      sidebarCollapsed: true,
      explorerListWidthPx: 260,
    });
    // Before the debounce window elapses, nothing is committed yet.
    expect(adapter.read(WS_SCOPE)).toBeUndefined();
    adapter.flush();
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("x"));
    expect(adapter.read(GLOBAL_SCOPE)).toEqual({
      sectionSizes: { left: 25, right: 25, bottom: 25 },
      sidebarWidthPx: 300,
      sidebarCollapsed: true,
      explorerListWidthPx: 260,
    });
  });
});
