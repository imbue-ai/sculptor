import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalStorageLayoutAdapter } from "./LocalStorageLayoutAdapter.ts";
import type { LayoutScope, WorkspaceLayoutState } from "./snapshot.ts";
import { LAYOUT_SNAPSHOT_VERSION } from "./snapshot.ts";

const WS_SCOPE: LayoutScope = { kind: "workspace", workspaceId: "ws-1" };
const GLOBAL_SCOPE: LayoutScope = { kind: "global" };

const makeWorkspaceLayout = (activePanel: string): WorkspaceLayoutState => {
  return {
    placement: { [activePanel]: "center" },
    order: { center: [activePanel] },
    activePanel: { center: activePanel },
    expanded: {},
    splits: {},
    activeSubSection: "center",
  };
};

describe("LocalStorageLayoutAdapter", () => {
  let adapter: LocalStorageLayoutAdapter;

  beforeEach(() => {
    localStorage.clear();
    adapter = new LocalStorageLayoutAdapter();
  });

  afterEach(() => {
    adapter.dispose();
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

  it("returns undefined for valid JSON of the wrong shape (missing required field)", () => {
    // Valid JSON, but a workspace snapshot missing `splits`/`activeSubSection` — a
    // stale or hand-edited entry must read as "nothing stored", not hydrate as valid.
    localStorage.setItem(
      "sculptor-layout-ws-ws-1",
      JSON.stringify({ placement: {}, order: {}, activePanel: {}, expanded: {} }),
    );
    expect(adapter.read(WS_SCOPE)).toBeUndefined();

    // Likewise for global: sectionSizes present but not the numeric/bool fields.
    localStorage.setItem(
      "sculptor-layout-global",
      JSON.stringify({ sectionSizes: { left: 20, right: 20, bottom: 30 } }),
    );
    expect(adapter.read(GLOBAL_SCOPE)).toBeUndefined();
  });

  it("stamps the current snapshot version on writes and strips it on reads", () => {
    const snapshot = makeWorkspaceLayout("agent:1");
    adapter.write(WS_SCOPE, snapshot);
    adapter.flush();

    // The stored payload carries the stamp…
    const stored = JSON.parse(localStorage.getItem("sculptor-layout-ws-ws-1") ?? "null") as Record<string, unknown>;
    expect(stored.version).toBe(LAYOUT_SNAPSHOT_VERSION);

    // …but the read-back snapshot does not: the stamp is storage metadata,
    // never in-memory layout state.
    expect(adapter.read(WS_SCOPE)).toEqual(snapshot);
    expect(adapter.read(WS_SCOPE)).not.toHaveProperty("version");
  });

  it("reads a versionless snapshot as the current version", () => {
    // Snapshots written before the version stamp existed have no `version`
    // field; they must still hydrate rather than being discarded.
    localStorage.setItem("sculptor-layout-ws-ws-1", JSON.stringify(makeWorkspaceLayout("files")));
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("files"));
  });

  it("rejects a future-version snapshot as nothing stored", () => {
    localStorage.setItem(
      "sculptor-layout-ws-ws-1",
      JSON.stringify({ ...makeWorkspaceLayout("files"), version: LAYOUT_SNAPSHOT_VERSION + 1 }),
    );
    expect(adapter.read(WS_SCOPE)).toBeUndefined();

    localStorage.setItem(
      "sculptor-layout-global",
      JSON.stringify({
        sectionSizes: { left: 20, right: 20, bottom: 30 },
        sidebarWidthPx: 240,
        sidebarCollapsed: false,
        explorerListWidthPx: 240,
        version: LAYOUT_SNAPSHOT_VERSION + 1,
      }),
    );
    expect(adapter.read(GLOBAL_SCOPE)).toBeUndefined();
  });

  it("remove clears a persisted scope and drops a pending write", () => {
    vi.useFakeTimers();
    // Persist a scope, then queue a debounced write and remove before it flushes.
    adapter.write(WS_SCOPE, makeWorkspaceLayout("files"));
    adapter.flush();
    expect(adapter.read(WS_SCOPE)).toBeDefined();

    adapter.write(WS_SCOPE, makeWorkspaceLayout("files-2"));
    adapter.remove(WS_SCOPE);
    // Draining the debounce must not resurrect the removed scope from the dropped write.
    vi.advanceTimersByTime(1000);
    expect(adapter.read(WS_SCOPE)).toBeUndefined();
    expect(localStorage.getItem("sculptor-layout-ws-ws-1")).toBeNull();
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

  it("isolates per-workspace snapshots from each other and from global", () => {
    const wsTwoScope: LayoutScope = { kind: "workspace", workspaceId: "ws-2" };
    const wsOne = makeWorkspaceLayout("agent:one");
    const wsTwo = makeWorkspaceLayout("agent:two");
    const global = {
      sectionSizes: { left: 25, right: 25, bottom: 25 },
      sidebarWidthPx: 300,
      sidebarCollapsed: true,
      explorerListWidthPx: 260,
    };

    adapter.write(WS_SCOPE, wsOne);
    adapter.write(wsTwoScope, wsTwo);
    adapter.write(GLOBAL_SCOPE, global);
    adapter.flush();

    // Each scope round-trips its OWN snapshot; no scope leaks into another.
    expect(adapter.read(WS_SCOPE)).toEqual(wsOne);
    expect(adapter.read(wsTwoScope)).toEqual(wsTwo);
    expect(adapter.read(GLOBAL_SCOPE)).toEqual(global);

    // Rewriting one workspace leaves the others and global untouched.
    const wsOneUpdated = makeWorkspaceLayout("agent:one-changed");
    adapter.write(WS_SCOPE, wsOneUpdated);
    adapter.flush();
    expect(adapter.read(WS_SCOPE)).toEqual(wsOneUpdated);
    expect(adapter.read(wsTwoScope)).toEqual(wsTwo);
    expect(adapter.read(GLOBAL_SCOPE)).toEqual(global);
  });

  it("remove clears only the targeted scope", () => {
    const wsTwoScope: LayoutScope = { kind: "workspace", workspaceId: "ws-2" };
    adapter.write(WS_SCOPE, makeWorkspaceLayout("a"));
    adapter.write(wsTwoScope, makeWorkspaceLayout("b"));
    adapter.flush();

    adapter.remove(WS_SCOPE);
    expect(adapter.read(WS_SCOPE)).toBeUndefined();
    // The other workspace's snapshot survives the targeted remove.
    expect(adapter.read(wsTwoScope)).toEqual(makeWorkspaceLayout("b"));
  });

  it("ignores legacy/prototype keys — reads only consolidated keys (no migration)", () => {
    // Old prototype scattered many per-aspect keys; the consolidated adapter must never
    // read them, so a workspace with only legacy keys present reads as "nothing stored".
    localStorage.setItem("sculptor-section-sizes", JSON.stringify({ left: 40 }));
    localStorage.setItem("sculptor-panel-visibility-ws-1", JSON.stringify({ files: true }));
    localStorage.setItem("sculptor-open-panels", JSON.stringify(["files", "changes"]));

    expect(adapter.read(WS_SCOPE)).toBeUndefined();
    expect(adapter.read(GLOBAL_SCOPE)).toBeUndefined();

    // Writing through the adapter never resurrects or rewrites the legacy keys.
    adapter.write(WS_SCOPE, makeWorkspaceLayout("files"));
    adapter.flush();
    expect(localStorage.getItem("sculptor-section-sizes")).toEqual(JSON.stringify({ left: 40 }));
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("files"));
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
    // Before the debounce window elapses nothing is committed to storage, but
    // read() already sees the pending snapshot (read-your-writes).
    expect(localStorage.getItem("sculptor-layout-ws-ws-1")).toBeNull();
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("x"));
    adapter.flush();
    expect(localStorage.getItem("sculptor-layout-ws-ws-1")).not.toBeNull();
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("x"));
    expect(adapter.read(GLOBAL_SCOPE)).toEqual({
      sectionSizes: { left: 25, right: 25, bottom: 25 },
      sidebarWidthPx: 300,
      sidebarCollapsed: true,
      explorerListWidthPx: 260,
    });
  });

  it("flushes pending writes when the window fires beforeunload, and stops after dispose", () => {
    vi.useFakeTimers();
    adapter.write(WS_SCOPE, makeWorkspaceLayout("x"));
    // Nothing is committed to storage before the debounce window elapses.
    expect(localStorage.getItem("sculptor-layout-ws-ws-1")).toBeNull();

    // The constructor wires flush to beforeunload, so quitting persists the pending write.
    window.dispatchEvent(new Event("beforeunload"));
    expect(localStorage.getItem("sculptor-layout-ws-ws-1")).not.toBeNull();
    expect(adapter.read(WS_SCOPE)).toEqual(makeWorkspaceLayout("x"));

    // After dispose the listener is gone, so a later beforeunload no longer flushes: the
    // second write stays pending and the persisted snapshot is still the first one.
    adapter.write(WS_SCOPE, makeWorkspaceLayout("y"));
    adapter.dispose();
    window.dispatchEvent(new Event("beforeunload"));
    const persisted = JSON.parse(localStorage.getItem("sculptor-layout-ws-ws-1") ?? "null");
    expect(persisted).toMatchObject(makeWorkspaceLayout("x"));
  });
});
