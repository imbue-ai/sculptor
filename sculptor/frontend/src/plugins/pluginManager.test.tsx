import { createStore } from "jotai";
import { FolderOpen } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import type { PanelDefinition } from "~/components/panels/types.ts";

import { PluginManager, resolveEntryUrl, validateManifest } from "./pluginManager.tsx";
import {
  pluginDisabledSourcesAtom,
  pluginPanelsAtom,
  pluginSettingsComponentsAtom,
  pluginSourcesAtom,
  pluginSourceStatesAtom,
} from "./pluginRegistry.ts";
import type { LoadedPlugin, PluginHostApi, PluginLoadError, PluginManifest } from "./types.ts";

const manifestFor = (id: string): PluginManifest => ({
  id,
  name: id,
  version: "0.1.0",
  entry: "main.js",
  sdkVersion: "^1.0.0",
});

const panelFor = (id: string): PanelDefinition => ({
  id,
  displayName: id,
  description: "test panel",
  icon: FolderOpen,
  defaultZone: "top-right",
  defaultShortcut: "",
  component: () => null,
});

/**
 * A controllable fake for the network loader. Each `loadOne` call registers a
 * panel through the provided api (mimicking what a real plugin's `activate`
 * does) and then waits until the test releases it — letting tests interleave
 * remove/reload with an in-flight load.
 */
const makeDeferredLoader = (): {
  loadOne: (
    manifestUrl: string,
    makeApi: (m: PluginManifest) => PluginHostApi,
  ) => Promise<LoadedPlugin | PluginLoadError>;
  release: (index: number) => void;
  calls: Array<{ manifestUrl: string; activateDispose: ReturnType<typeof vi.fn> }>;
} => {
  const gates: Array<() => void> = [];
  const calls: Array<{ manifestUrl: string; activateDispose: ReturnType<typeof vi.fn> }> = [];

  const loadOne = async (
    manifestUrl: string,
    makeApi: (m: PluginManifest) => PluginHostApi,
  ): Promise<LoadedPlugin | PluginLoadError> => {
    const pluginId = manifestUrl.split("/").filter(Boolean).slice(-2)[0] ?? "plugin";
    const manifest = manifestFor(pluginId);
    // `activate` runs before the loader resolves, exactly like the real path.
    const api = makeApi(manifest);
    api.registerPanel(panelFor(pluginId));
    const activateDispose = vi.fn();
    calls.push({ manifestUrl, activateDispose });
    await new Promise<void>((resolve) => gates.push(resolve));
    return { manifest, dispose: activateDispose };
  };

  return { loadOne, release: (index: number): void => gates[index](), calls };
};

const flushMicrotasks = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

describe("PluginManager", () => {
  it("loads a source end-to-end: panel registered, state loaded", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ loadOne: loader.loadOne, builtinSources: [] });

    const pending = manager.addSource(store, "/plugins/alpha");
    loader.release(0);
    await pending;

    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "loaded" });
    expect(store.get(pluginSourcesAtom)).toEqual(["/plugins/alpha"]);
  });

  it("does not resurrect a source removed while its load is in flight", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ loadOne: loader.loadOne, builtinSources: [] });

    const pending = manager.addSource(store, "/plugins/alpha");
    // The fake activate already registered the panel synchronously.
    expect(store.get(pluginPanelsAtom)).toHaveLength(1);

    manager.removeSource(store, "/plugins/alpha");
    loader.release(0);
    await pending;
    await flushMicrotasks();

    // The stale load must roll back its own registration and commit nothing.
    expect(store.get(pluginPanelsAtom)).toEqual([]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toBeUndefined();
    expect(store.get(pluginSourcesAtom)).toEqual([]);
    expect(loader.calls[0].activateDispose).toHaveBeenCalled();
  });

  it("a reload supersedes an older in-flight load for the same source", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ loadOne: loader.loadOne, builtinSources: [] });

    const first = manager.addSource(store, "/plugins/alpha");
    const second = manager.reloadSource(store, "/plugins/alpha");

    // Resolve the OLD load after the reload started: it must detect it is
    // stale and roll back, leaving the newer load's registration in place.
    loader.release(0);
    await first;
    loader.release(1);
    await second;
    await flushMicrotasks();

    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "loaded" });
    // Only the first (stale) load's activate-dispose ran.
    expect(loader.calls[0].activateDispose).toHaveBeenCalled();
    expect(loader.calls[1].activateDispose).not.toHaveBeenCalled();
  });

  it("removing a loaded source runs its disposers and clears panels and settings", async () => {
    const store = createStore();
    const settingsComponent = (): null => null;
    const activateDispose = vi.fn();
    const loadOne = async (
      _url: string,
      makeApi: (m: PluginManifest) => PluginHostApi,
    ): Promise<LoadedPlugin | PluginLoadError> => {
      const api = makeApi(manifestFor("alpha"));
      api.registerPanel(panelFor("alpha"));
      api.registerSettings(settingsComponent);
      return { manifest: manifestFor("alpha"), dispose: activateDispose };
    };
    const manager = new PluginManager({ loadOne, builtinSources: [] });

    await manager.addSource(store, "/plugins/alpha");
    expect(store.get(pluginPanelsAtom)).toHaveLength(1);
    expect(store.get(pluginSettingsComponentsAtom)["alpha"]).toBe(settingsComponent);

    manager.removeSource(store, "/plugins/alpha");

    expect(store.get(pluginPanelsAtom)).toEqual([]);
    expect(store.get(pluginSettingsComponentsAtom)["alpha"]).toBeUndefined();
    expect(activateDispose).toHaveBeenCalledTimes(1);
    expect(store.get(pluginSourcesAtom)).toEqual([]);
  });

  it("bootstrap loads builtin and persisted sources exactly once", async () => {
    const store = createStore();
    store.set(pluginSourcesAtom, ["/plugins/user-one"]);
    const loaded: Array<string> = [];
    const loadOne = async (
      url: string,
      makeApi: (m: PluginManifest) => PluginHostApi,
    ): Promise<LoadedPlugin | PluginLoadError> => {
      loaded.push(url);
      void makeApi;
      return { manifest: manifestFor(url) };
    };
    const manager = new PluginManager({ loadOne, builtinSources: ["/plugins/builtin"] });

    manager.bootstrap(store);
    manager.bootstrap(store); // StrictMode-style double invoke
    await flushMicrotasks();

    expect(loaded).toEqual(["/plugins/builtin/manifest.json", "/plugins/user-one/manifest.json"]);
  });

  it("ignores duplicate adds for the same or builtin source", async () => {
    const store = createStore();
    const loaded: Array<string> = [];
    const loadOne = async (url: string): Promise<LoadedPlugin | PluginLoadError> => {
      loaded.push(url);
      return { manifest: manifestFor("x") };
    };
    const manager = new PluginManager({ loadOne, builtinSources: ["/plugins/builtin"] });

    await manager.addSource(store, "/plugins/builtin");
    await manager.addSource(store, "/plugins/alpha");
    await manager.addSource(store, "/plugins/alpha");
    // Trailing-slash and whitespace variants normalize to the same source.
    await manager.addSource(store, "/plugins/alpha/");
    await manager.addSource(store, "  /plugins/builtin/  ");

    expect(loaded).toEqual(["/plugins/alpha/manifest.json"]);
    expect(store.get(pluginSourcesAtom)).toEqual(["/plugins/alpha"]);
  });

  it("disabling a loaded source unloads it, keeps it on the list, and persists the choice", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ loadOne: loader.loadOne, builtinSources: [] });

    const pending = manager.addSource(store, "/plugins/alpha");
    loader.release(0);
    await pending;
    expect(store.get(pluginPanelsAtom)).toHaveLength(1);

    await manager.setSourceEnabled(store, "/plugins/alpha", false);

    // The panel is gone, but the source stays on the list and is marked
    // disabled (persisted so the next launch keeps it off).
    expect(store.get(pluginPanelsAtom)).toEqual([]);
    expect(store.get(pluginSourcesAtom)).toEqual(["/plugins/alpha"]);
    expect(store.get(pluginDisabledSourcesAtom)).toEqual(["/plugins/alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "disabled" });
    expect(loader.calls[0].activateDispose).toHaveBeenCalled();
  });

  it("re-enabling a disabled source loads it again", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ loadOne: loader.loadOne, builtinSources: [] });

    const pending = manager.addSource(store, "/plugins/alpha");
    loader.release(0);
    await pending;
    await manager.setSourceEnabled(store, "/plugins/alpha", false);

    const reEnable = manager.setSourceEnabled(store, "/plugins/alpha", true);
    loader.release(1);
    await reEnable;

    expect(store.get(pluginDisabledSourcesAtom)).toEqual([]);
    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "loaded" });
  });

  it("bootstrap parks a disabled source without loading it", async () => {
    const store = createStore();
    store.set(pluginSourcesAtom, ["/plugins/user-one"]);
    store.set(pluginDisabledSourcesAtom, ["/plugins/user-one", "/plugins/builtin"]);
    const loaded: Array<string> = [];
    const loadOne = async (url: string): Promise<LoadedPlugin | PluginLoadError> => {
      loaded.push(url);
      return { manifest: manifestFor(url) };
    };
    const manager = new PluginManager({ loadOne, builtinSources: ["/plugins/builtin"] });

    manager.bootstrap(store);
    await flushMicrotasks();

    // Neither the disabled builtin nor the disabled user source loads, yet both
    // appear in the status map as "disabled" so the settings UI can list them.
    expect(loaded).toEqual([]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/builtin"]).toMatchObject({
      status: "disabled",
      isBuiltin: true,
    });
    expect(store.get(pluginSourceStatesAtom)["/plugins/user-one"]).toMatchObject({
      status: "disabled",
      isBuiltin: false,
    });
  });

  it("removing a disabled source clears its disabled flag so a re-add starts enabled", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ loadOne: loader.loadOne, builtinSources: [] });

    const pending = manager.addSource(store, "/plugins/alpha");
    loader.release(0);
    await pending;
    await manager.setSourceEnabled(store, "/plugins/alpha", false);
    manager.removeSource(store, "/plugins/alpha");

    expect(store.get(pluginDisabledSourcesAtom)).toEqual([]);
    expect(store.get(pluginSourcesAtom)).toEqual([]);
  });

  it("settles a throwing loader into an error state instead of stuck loading", async () => {
    const store = createStore();
    // A loader is supposed to *return* a PluginLoadError; this one throws
    // outright, mimicking a synchronous fault (e.g. a bad URL construction).
    const loadOne = async (): Promise<LoadedPlugin | PluginLoadError> => {
      throw new TypeError("Invalid URL");
    };
    const manager = new PluginManager({ loadOne, builtinSources: [] });

    // The throw must not escape addSource: it resolves, and the source row
    // lands in "error" (with the catch-all phase) rather than "loading".
    await manager.addSource(store, "http://127.0.0.1:8765/hello");

    expect(store.get(pluginSourceStatesAtom)["http://127.0.0.1:8765/hello"]).toMatchObject({
      status: "error",
      phase: "load",
    });
    // The source stays persisted so the user can see and remove it.
    expect(store.get(pluginSourcesAtom)).toEqual(["http://127.0.0.1:8765/hello"]);
    expect(store.get(pluginPanelsAtom)).toEqual([]);
  });
});

describe("resolveEntryUrl", () => {
  it("resolves a path-only manifest against the app origin", () => {
    const url = resolveEntryUrl("/plugins/linear-issue/manifest.json", "main.js");
    expect(url).toBe(`${window.location.origin}/plugins/linear-issue/main.js`);
  });

  it("resolves a cross-origin manifest against the plugin's own origin, not the app's", () => {
    const url = resolveEntryUrl("http://127.0.0.1:8765/hello/manifest.json", "main.js");
    expect(url).toBe("http://127.0.0.1:8765/hello/main.js");
  });

  it("honors a nested entry path in the manifest", () => {
    const url = resolveEntryUrl("https://cdn.example/p/v2/manifest.json", "dist/main.js");
    expect(url).toBe("https://cdn.example/p/v2/dist/main.js");
  });
});

describe("validateManifest", () => {
  const valid = (): PluginManifest => ({
    id: "p",
    name: "P",
    version: "0.1.0",
    entry: "main.js",
    sdkVersion: "^1.0.0",
  });

  it("accepts a well-formed manifest", () => {
    expect(validateManifest(valid())).toBeNull();
  });

  it("rejects a missing required field", () => {
    const noEntry = { id: "p", name: "P", version: "0.1.0", sdkVersion: "^1.0.0" } as unknown as PluginManifest;
    expect(validateManifest(noEntry)?.message).toContain("entry");
  });

  it("rejects a non-string field (untrusted JSON cast to the type)", () => {
    // A plugin could serve `{ "sdkVersion": 1 }`; the cast lies, so the runtime
    // check must catch it here rather than letting parseMajor throw downstream.
    const bad = { ...valid(), sdkVersion: 1 } as unknown as PluginManifest;
    expect(validateManifest(bad)?.message).toContain("sdkVersion");
  });

  it("rejects an SDK major the host does not provide", () => {
    expect(validateManifest({ ...valid(), sdkVersion: "2.0.0" })?.message).toContain("SDK major");
  });
});
