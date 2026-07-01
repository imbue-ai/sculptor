import { createStore } from "jotai";
import { FolderOpen } from "lucide-react";
import { describe, expect, it, vi } from "vitest";

import type { PluginCommandUiAction } from "~/api";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { type LocalPluginRef, PluginManager, resolveEntryUrl, validateManifest } from "./pluginManager.tsx";
import {
  pluginDisabledSourcesAtom,
  pluginEnabledSourcesAtom,
  pluginPanelsAtom,
  pluginSettingsComponentsAtom,
  pluginSourcesAtom,
  pluginSourceStatesAtom,
  pluginWorkspaceWidgetsAtom,
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

/** The plugin id a fake manifest fetch derives from a URL: its directory name. */
const idFromManifestUrl = (manifestUrl: string): string =>
  manifestUrl.split("/").filter(Boolean).slice(-2)[0] ?? "plugin";

const noLocalPlugins = async (): Promise<ReadonlyArray<LocalPluginRef>> => [];

/**
 * An immediate fake loader: the manifest fetch derives the plugin id from the
 * URL's directory, and `activate` registers a panel and records the manifest URL
 * (so tests can assert which sources actually loaded, in order).
 */
const makeRecordingLoader = (): {
  fetchManifest: (manifestUrl: string) => Promise<{ manifest: PluginManifest }>;
  activate: (
    manifestUrl: string,
    manifest: PluginManifest,
    makeApi: (m: PluginManifest) => PluginHostApi,
  ) => Promise<LoadedPlugin>;
  activated: Array<string>;
} => {
  const activated: Array<string> = [];
  return {
    fetchManifest: async (manifestUrl) => ({ manifest: manifestFor(idFromManifestUrl(manifestUrl)) }),
    activate: async (manifestUrl, manifest, makeApi): Promise<LoadedPlugin> => {
      activated.push(manifestUrl);
      makeApi(manifest).registerPanel(panelFor(manifest.id));
      return { manifest, dispose: vi.fn() };
    },
    activated,
  };
};

/**
 * A controllable fake loader whose `activate` blocks until released — letting
 * tests interleave remove/reload with an in-flight activation. `started(i)`
 * resolves once the i-th activation has begun (panel registered), so a test can
 * wait for that point before releasing or superseding it.
 */
const makeDeferredLoader = (): {
  fetchManifest: (manifestUrl: string) => Promise<{ manifest: PluginManifest }>;
  activate: (
    manifestUrl: string,
    manifest: PluginManifest,
    makeApi: (m: PluginManifest) => PluginHostApi,
  ) => Promise<LoadedPlugin>;
  release: (index: number) => void;
  started: (index: number) => Promise<void>;
  calls: Array<{ manifestUrl: string; activateDispose: ReturnType<typeof vi.fn> }>;
} => {
  const gates: Array<() => void> = [];
  const startedResolvers: Array<() => void> = [];
  const startedPromises: Array<Promise<void>> = [];
  const calls: Array<{ manifestUrl: string; activateDispose: ReturnType<typeof vi.fn> }> = [];

  const started = (index: number): Promise<void> => {
    if (!startedPromises[index]) {
      startedPromises[index] = new Promise<void>((resolve) => (startedResolvers[index] = resolve));
    }
    return startedPromises[index];
  };

  return {
    fetchManifest: async (manifestUrl) => ({ manifest: manifestFor(idFromManifestUrl(manifestUrl)) }),
    activate: async (manifestUrl, manifest, makeApi): Promise<LoadedPlugin> => {
      const index = calls.length;
      makeApi(manifest).registerPanel(panelFor(manifest.id));
      const activateDispose = vi.fn();
      calls.push({ manifestUrl, activateDispose });
      void started(index);
      startedResolvers[index]?.();
      await new Promise<void>((resolve) => (gates[index] = resolve));
      return { manifest, dispose: activateDispose };
    },
    release: (index) => gates[index](),
    started,
    calls,
  };
};

const flushMicrotasks = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

/** A discovered local plugin ref, as the backend lists it (relative manifest URL). */
const localRef = (id: string): LocalPluginRef => ({ id, manifestUrl: `/plugins/local/${id}/manifest.json` });

/** The port-stable source string the manager stores for a discovered local plugin. */
const localSourceFor = (id: string): string => `/plugins/local/${id}`;

/**
 * A `discoverLocal` whose result can be changed between calls — mimics plugins
 * appearing/disappearing under `~/.sculptor/plugins/` between bootstrap and a
 * manual refresh.
 */
const makeMutableDiscovery = (
  initial: ReadonlyArray<LocalPluginRef> = [],
): {
  discoverLocal: () => Promise<ReadonlyArray<LocalPluginRef>>;
  set: (refs: ReadonlyArray<LocalPluginRef>) => void;
} => {
  let refs = initial;
  return {
    discoverLocal: async () => refs,
    set: (next): void => {
      refs = next;
    },
  };
};

describe("PluginManager", () => {
  it("loads a source end-to-end: panel registered, state loaded", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [] });

    await manager.addSource(store, "/plugins/alpha");

    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "loaded", kind: "url" });
    expect(store.get(pluginSourcesAtom)).toEqual(["/plugins/alpha"]);
  });

  it("does not resurrect a source removed while its activation is in flight", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [] });

    const pending = manager.addSource(store, "/plugins/alpha");
    await loader.started(0); // activation has begun, panel registered
    expect(store.get(pluginPanelsAtom)).toHaveLength(1);

    manager.removeSource(store, "/plugins/alpha");
    loader.release(0);
    await pending;
    await flushMicrotasks();

    // The stale activation must roll back its own registration and commit nothing.
    expect(store.get(pluginPanelsAtom)).toEqual([]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toBeUndefined();
    expect(store.get(pluginSourcesAtom)).toEqual([]);
    expect(loader.calls[0].activateDispose).toHaveBeenCalled();
  });

  it("a reload supersedes an older in-flight activation for the same source", async () => {
    const store = createStore();
    const loader = makeDeferredLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [] });

    const first = manager.addSource(store, "/plugins/alpha");
    await loader.started(0);
    const second = manager.reloadSource(store, "/plugins/alpha");

    // Resolve the OLD activation after the reload started: it must detect it is
    // stale and roll back, leaving the newer one's registration in place.
    loader.release(0);
    await first;
    await loader.started(1);
    loader.release(1);
    await second;
    await flushMicrotasks();

    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "loaded" });
    // Only the first (stale) activation's dispose ran.
    expect(loader.calls[0].activateDispose).toHaveBeenCalled();
    expect(loader.calls[1].activateDispose).not.toHaveBeenCalled();
  });

  it("removing a loaded source runs its disposers and clears panels, settings, and widgets", async () => {
    const store = createStore();
    const settingsComponent = (): null => null;
    const widgetComponent = (): null => null;
    const activateDispose = vi.fn();
    const manager = new PluginManager({
      fetchManifest: async (): Promise<{ manifest: PluginManifest }> => ({ manifest: manifestFor("alpha") }),
      activate: async (_url, manifest, makeApi): Promise<LoadedPlugin> => {
        const api = makeApi(manifest);
        api.registerPanel(panelFor("alpha"));
        api.registerSettings(settingsComponent);
        api.registerWorkspaceWidget({ id: "alpha", component: widgetComponent, collapsePriority: 3 });
        return { manifest, dispose: activateDispose };
      },
      builtinSources: [],
    });

    await manager.addSource(store, "/plugins/alpha");
    expect(store.get(pluginPanelsAtom)).toHaveLength(1);
    expect(store.get(pluginSettingsComponentsAtom)["alpha"]).toBe(settingsComponent);
    const widgets = store.get(pluginWorkspaceWidgetsAtom);
    expect(widgets.map((w) => w.id)).toEqual(["alpha"]);
    expect(widgets[0].collapsePriority).toBe(3);

    manager.removeSource(store, "/plugins/alpha");

    expect(store.get(pluginPanelsAtom)).toEqual([]);
    expect(store.get(pluginSettingsComponentsAtom)["alpha"]).toBeUndefined();
    expect(store.get(pluginWorkspaceWidgetsAtom)).toEqual([]);
    expect(activateDispose).toHaveBeenCalledTimes(1);
    expect(store.get(pluginSourcesAtom)).toEqual([]);
  });

  it("bootstrap loads builtin and persisted sources exactly once", async () => {
    const store = createStore();
    store.set(pluginSourcesAtom, ["/plugins/user-one"]);
    const loader = makeRecordingLoader();
    const manager = new PluginManager({
      ...loader,
      builtinSources: [{ path: "/plugins/builtin" }],
      discoverLocal: noLocalPlugins,
    });

    manager.bootstrap(store);
    manager.bootstrap(store); // StrictMode-style double invoke
    await flushMicrotasks();

    expect(loader.activated).toEqual(["/plugins/builtin/manifest.json", "/plugins/user-one/manifest.json"]);
  });

  it("ignores duplicate adds for the same or builtin source", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [{ path: "/plugins/builtin" }] });

    await manager.addSource(store, "/plugins/builtin");
    await manager.addSource(store, "/plugins/alpha");
    await manager.addSource(store, "/plugins/alpha");
    // Trailing-slash and whitespace variants normalize to the same source.
    await manager.addSource(store, "/plugins/alpha/");
    await manager.addSource(store, "  /plugins/builtin/  ");

    expect(loader.activated).toEqual(["/plugins/alpha/manifest.json"]);
    expect(store.get(pluginSourcesAtom)).toEqual(["/plugins/alpha"]);
  });

  it("drops a built-in squatting a reserved dynamic-mount path", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({
      ...loader,
      builtinSources: [{ path: "/plugins/local" }, { path: "/plugins/from-workspace" }, { path: "/plugins/ok" }],
      discoverLocal: noLocalPlugins,
    });

    manager.bootstrap(store);
    await flushMicrotasks();

    // The reserved ones never load; only the legitimately-named built-in does.
    expect(loader.activated).toEqual(["/plugins/ok/manifest.json"]);
  });

  it("disabling a loaded source unloads it, keeps it on the list, and persists the choice", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [] });

    await manager.addSource(store, "/plugins/alpha");
    expect(store.get(pluginPanelsAtom)).toHaveLength(1);

    await manager.setSourceEnabled(store, "/plugins/alpha", false);

    // The panel is gone, but the source stays on the list and is marked
    // disabled (persisted so the next launch keeps it off).
    expect(store.get(pluginPanelsAtom)).toEqual([]);
    expect(store.get(pluginSourcesAtom)).toEqual(["/plugins/alpha"]);
    expect(store.get(pluginDisabledSourcesAtom)).toEqual(["/plugins/alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "disabled" });
  });

  it("re-enabling a disabled source loads it again", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [] });

    await manager.addSource(store, "/plugins/alpha");
    await manager.setSourceEnabled(store, "/plugins/alpha", false);
    await manager.setSourceEnabled(store, "/plugins/alpha", true);

    expect(store.get(pluginDisabledSourcesAtom)).toEqual([]);
    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["alpha"]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "loaded" });
  });

  it("bootstrap parks a disabled source without loading it", async () => {
    const store = createStore();
    store.set(pluginSourcesAtom, ["/plugins/user-one"]);
    store.set(pluginDisabledSourcesAtom, ["/plugins/user-one", "/plugins/builtin"]);
    const loader = makeRecordingLoader();
    const manager = new PluginManager({
      ...loader,
      builtinSources: [{ path: "/plugins/builtin" }],
      discoverLocal: noLocalPlugins,
    });

    manager.bootstrap(store);
    await flushMicrotasks();

    // Neither the disabled builtin nor the disabled user source loads, yet both
    // appear in the status map as "disabled" so the settings UI can list them.
    expect(loader.activated).toEqual([]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/builtin"]).toMatchObject({
      status: "disabled",
      kind: "builtin",
    });
    expect(store.get(pluginSourceStatesAtom)["/plugins/user-one"]).toMatchObject({ status: "disabled", kind: "url" });
  });

  it("removing a disabled source clears its disabled flag so a re-add starts enabled", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({ ...loader, builtinSources: [] });

    await manager.addSource(store, "/plugins/alpha");
    await manager.setSourceEnabled(store, "/plugins/alpha", false);
    manager.removeSource(store, "/plugins/alpha");

    expect(store.get(pluginDisabledSourcesAtom)).toEqual([]);
    expect(store.get(pluginSourcesAtom)).toEqual([]);
  });

  it("a disabledByDefault builtin stays off on bootstrap, then loads (and stays on) once enabled", async () => {
    const store = createStore();
    const builtinSources = [{ path: "/plugins/optin", disabledByDefault: true }];
    const loader = makeRecordingLoader();
    const manager = new PluginManager({ ...loader, builtinSources, discoverLocal: noLocalPlugins });

    manager.bootstrap(store);
    await flushMicrotasks();

    // Off by default: not loaded, parked "disabled", and NOT in the disabled set
    // (nothing was explicitly disabled — being off is the shipped default).
    expect(loader.activated).toEqual([]);
    expect(store.get(pluginSourceStatesAtom)["/plugins/optin"]).toMatchObject({ status: "disabled", kind: "builtin" });
    expect(store.get(pluginDisabledSourcesAtom)).toEqual([]);

    // Enabling loads it and records the opt-in so a relaunch keeps it on.
    await manager.setSourceEnabled(store, "/plugins/optin", true);
    expect(loader.activated).toEqual(["/plugins/optin/manifest.json"]);
    expect(store.get(pluginEnabledSourcesAtom)).toEqual(["/plugins/optin"]);

    // Relaunch: a fresh manager over the same persisted store honors the opt-in.
    const reloaded = makeRecordingLoader();
    const manager2 = new PluginManager({ ...reloaded, builtinSources, discoverLocal: noLocalPlugins });
    manager2.bootstrap(store);
    await flushMicrotasks();
    expect(reloaded.activated).toEqual(["/plugins/optin/manifest.json"]);
  });

  it("discovers local plugins and loads them as read-only 'local' sources", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const manager = new PluginManager({
      ...loader,
      builtinSources: [],
      discoverLocal: async (): Promise<ReadonlyArray<LocalPluginRef>> => [
        { id: "foo", manifestUrl: "/plugins/local/foo/manifest.json" },
      ],
    });

    manager.bootstrap(store);
    await flushMicrotasks();

    // Identity is the RELATIVE plugin dir (port-stable); the manifest is fetched
    // by resolving it against the backend origin (baseUrl is unset in the test,
    // so it falls back to the renderer origin). Tagged "local", not persisted to
    // the user source list.
    const source = "/plugins/local/foo";
    expect(loader.activated).toEqual([`${window.location.origin}/plugins/local/foo/manifest.json`]);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded", kind: "local" });
    expect(store.get(pluginSourcesAtom)).toEqual([]);

    // A discovered local source cannot be re-added by hand as a user URL.
    await manager.addSource(store, source);
    expect(store.get(pluginSourcesAtom)).toEqual([]);
  });

  it("settles a throwing manifest fetch into an error state instead of stuck loading", async () => {
    const store = createStore();
    const manager = new PluginManager({
      // A fetcher is supposed to *return* a PluginLoadError; this one throws
      // outright, mimicking a synchronous fault (e.g. a bad URL construction).
      fetchManifest: async (): Promise<{ manifest: PluginManifest }> => {
        throw new TypeError("Invalid URL");
      },
      activate: async (_url: string, manifest: PluginManifest): Promise<LoadedPlugin> => ({ manifest }),
      builtinSources: [],
    });

    await manager.addSource(store, "http://127.0.0.1:8765/hello");

    expect(store.get(pluginSourceStatesAtom)["http://127.0.0.1:8765/hello"]).toMatchObject({
      status: "error",
      phase: "load",
    });
    // The source stays persisted so the user can see and remove it.
    expect(store.get(pluginSourcesAtom)).toEqual(["http://127.0.0.1:8765/hello"]);
    expect(store.get(pluginPanelsAtom)).toEqual([]);
  });

  it("activates the highest-priority source when several share a plugin id; shadows the rest", async () => {
    const store = createStore();
    store.set(pluginSourcesAtom, ["http://remote/remote-ver"]);
    const activated: Array<string> = [];
    const localSource = "/plugins/local/local-ver";
    const manager = new PluginManager({
      // All three sources report the same plugin id, so they compete.
      fetchManifest: async (): Promise<{ manifest: PluginManifest }> => ({ manifest: manifestFor("shared") }),
      activate: async (manifestUrl, manifest): Promise<LoadedPlugin> => {
        activated.push(manifestUrl);
        return { manifest };
      },
      builtinSources: [{ path: "/plugins/bundled-ver" }],
      discoverLocal: async (): Promise<ReadonlyArray<LocalPluginRef>> => [
        { id: "local-ver", manifestUrl: "/plugins/local/local-ver/manifest.json" },
      ],
    });

    manager.bootstrap(store);
    await flushMicrotasks();

    // Priority local > url > builtin: only the local version activates. Its
    // identity is the relative dir; the fetched manifest resolves to the backend
    // origin (the renderer origin in this test).
    expect(activated).toEqual([`${window.location.origin}/plugins/local/local-ver/manifest.json`]);
    const states = store.get(pluginSourceStatesAtom);
    expect(states[localSource]).toMatchObject({ status: "loaded", kind: "local" });
    expect(states["http://remote/remote-ver"]).toMatchObject({
      status: "shadowed",
      kind: "url",
      activeSource: localSource,
    });
    expect(states["/plugins/bundled-ver"]).toMatchObject({
      status: "shadowed",
      kind: "builtin",
      activeSource: localSource,
    });
  });

  it("won't enable a competitor while another version is loaded; a manual switch persists", async () => {
    const store = createStore();
    // Relative (port-stable) identity: the persisted disable below must survive a
    // backend-port change, which a port-bearing source string would not.
    const localSource = "/plugins/local/local-ver";
    const makeManager = (): { manager: PluginManager; activated: Array<string> } => {
      const activated: Array<string> = [];
      const manager = new PluginManager({
        fetchManifest: async (): Promise<{ manifest: PluginManifest }> => ({ manifest: manifestFor("shared") }),
        activate: async (manifestUrl, manifest): Promise<LoadedPlugin> => {
          activated.push(manifestUrl);
          return { manifest };
        },
        builtinSources: [{ path: "/plugins/bundled-ver" }],
        discoverLocal: async (): Promise<ReadonlyArray<LocalPluginRef>> => [
          { id: "local-ver", manifestUrl: "/plugins/local/local-ver/manifest.json" },
        ],
      });
      return { manager, activated };
    };

    const { manager } = makeManager();
    manager.bootstrap(store);
    await flushMicrotasks();
    expect(store.get(pluginSourceStatesAtom)[localSource]).toMatchObject({ status: "loaded" });
    expect(store.get(pluginSourceStatesAtom)["/plugins/bundled-ver"]).toMatchObject({ status: "shadowed" });

    // Enabling the shadowed built-in while local holds the id is refused — it
    // stays shadowed (the manager never lets two be active for one id).
    await manager.setSourceEnabled(store, "/plugins/bundled-ver", true);
    expect(store.get(pluginSourceStatesAtom)["/plugins/bundled-ver"]).toMatchObject({ status: "shadowed" });

    // Disable the active local version → frees the id → enable the built-in.
    await manager.setSourceEnabled(store, localSource, false);
    await manager.setSourceEnabled(store, "/plugins/bundled-ver", true);
    expect(store.get(pluginSourceStatesAtom)["/plugins/bundled-ver"]).toMatchObject({ status: "loaded" });
    expect(store.get(pluginDisabledSourcesAtom)).toEqual([localSource]);

    // Persistence: a fresh manager over the same store keeps local disabled, so
    // the built-in wins (it's the only enabled candidate for the id).
    const relaunch = makeManager();
    relaunch.manager.bootstrap(store);
    await flushMicrotasks();
    expect(store.get(pluginSourceStatesAtom)["/plugins/bundled-ver"]).toMatchObject({ status: "loaded" });
    expect(relaunch.activated).toEqual(["/plugins/bundled-ver/manifest.json"]);
  });

  it("falls through to the next-priority source when the chosen winner fails to activate", async () => {
    const store = createStore();
    store.set(pluginSourcesAtom, ["http://remote/remote-ver"]);
    const localSource = "/plugins/local/local-ver";
    const manager = new PluginManager({
      fetchManifest: async (): Promise<{ manifest: PluginManifest }> => ({ manifest: manifestFor("shared") }),
      // The local copy (highest priority) fails to activate; resolution must
      // fall through to the next source rather than leaving the id unowned.
      activate: async (manifestUrl, manifest): Promise<LoadedPlugin | PluginLoadError> =>
        manifestUrl.includes("/plugins/local/")
          ? { manifest, phase: "activate", error: new Error("boom") }
          : { manifest },
      builtinSources: [{ path: "/plugins/bundled-ver" }],
      discoverLocal: async (): Promise<ReadonlyArray<LocalPluginRef>> => [
        { id: "local-ver", manifestUrl: "/plugins/local/local-ver/manifest.json" },
      ],
    });

    manager.bootstrap(store);
    await flushMicrotasks();

    const states = store.get(pluginSourceStatesAtom);
    // Local errored; the next-priority source (remote url) became active; the
    // built-in is shadowed behind it.
    expect(states[localSource]).toMatchObject({ status: "error", phase: "activate" });
    expect(states["http://remote/remote-ver"]).toMatchObject({ status: "loaded", kind: "url" });
    expect(states["/plugins/bundled-ver"]).toMatchObject({
      status: "shadowed",
      kind: "builtin",
      activeSource: "http://remote/remote-ver",
    });
  });

  it("rolls back registrations when activate registers and then fails", async () => {
    const store = createStore();
    const manager = new PluginManager({
      fetchManifest: async (): Promise<{ manifest: PluginManifest }> => ({ manifest: manifestFor("alpha") }),
      // Register a panel, then fail: the panel must not survive the error state.
      activate: async (_url, manifest, makeApi): Promise<PluginLoadError> => {
        makeApi(manifest).registerPanel(panelFor("alpha"));
        return { manifest, phase: "activate", error: new Error("boom") };
      },
      builtinSources: [],
    });

    await manager.addSource(store, "/plugins/alpha");

    expect(store.get(pluginSourceStatesAtom)["/plugins/alpha"]).toMatchObject({ status: "error", phase: "activate" });
    expect(store.get(pluginPanelsAtom)).toEqual([]);
  });

  it("refresh picks up a local plugin added after bootstrap, and is a no-op for one already loaded", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const discovery = makeMutableDiscovery();
    const manager = new PluginManager({ ...loader, builtinSources: [], discoverLocal: discovery.discoverLocal });

    manager.bootstrap(store);
    await flushMicrotasks();
    expect(loader.activated).toEqual([]); // nothing under ~/.sculptor/plugins/ yet

    // A plugin folder appears; refresh loads it without a full reload.
    discovery.set([localRef("foo")]);
    await manager.refreshLocalSources(store);
    const source = localSourceFor("foo");
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded", kind: "local" });
    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["foo"]);

    // A second refresh with the same plugin still present must not re-activate it.
    const activatedCount = loader.activated.length;
    await manager.refreshLocalSources(store);
    expect(loader.activated.length).toBe(activatedCount);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded" });
  });

  it("refresh keeps a disappeared-but-chosen local plugin as a 'missing' dead-trace and re-applies the choice on return", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const discovery = makeMutableDiscovery([localRef("foo")]);
    const manager = new PluginManager({ ...loader, builtinSources: [], discoverLocal: discovery.discoverLocal });

    manager.bootstrap(store);
    await flushMicrotasks();
    const source = localSourceFor("foo");
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded" });

    // A persisted on/off choice (here: disabled) is what earns a dead-trace row.
    await manager.setSourceEnabled(store, source, false);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "disabled" });

    // The folder vanishes. It isn't loaded (disabled) and has a kept choice, so
    // it stays as a "missing" row and the choice survives.
    discovery.set([]);
    await manager.refreshLocalSources(store);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "missing", kind: "local" });
    expect(store.get(pluginDisabledSourcesAtom)).toEqual([source]);

    // It comes back: the remembered "disabled" choice is re-applied (not auto-loaded).
    discovery.set([localRef("foo")]);
    await manager.refreshLocalSources(store);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "disabled", kind: "local" });
    expect(store.get(pluginPanelsAtom)).toEqual([]);
  });

  it("refresh drops a disappeared local plugin that has no persisted choice", async () => {
    const store = createStore();
    const discovery = makeMutableDiscovery([localRef("foo")]);
    const manager = new PluginManager({
      // The manifest fails to fetch, so foo settles into an error row — present in
      // the status map but with no user enable/disable choice behind it.
      fetchManifest: async (): Promise<PluginLoadError> => ({
        manifest: manifestFor("foo"),
        phase: "manifest",
        error: new Error("not found"),
      }),
      activate: async (_url, manifest): Promise<LoadedPlugin> => ({ manifest }),
      builtinSources: [],
      discoverLocal: discovery.discoverLocal,
    });

    manager.bootstrap(store);
    await flushMicrotasks();
    const source = localSourceFor("foo");
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "error" });

    discovery.set([]);
    await manager.refreshLocalSources(store);
    // No choice to remember → no dead-trace; the row is removed entirely.
    expect(store.get(pluginSourceStatesAtom)[source]).toBeUndefined();
  });

  it("refresh retries a previously-errored local plugin once its manifest is fixed", async () => {
    const store = createStore();
    let isManifestOk = false;
    const activated: Array<string> = [];
    const discovery = makeMutableDiscovery([localRef("foo")]);
    const manager = new PluginManager({
      fetchManifest: async (): Promise<{ manifest: PluginManifest } | PluginLoadError> =>
        isManifestOk
          ? { manifest: manifestFor("foo") }
          : { manifest: manifestFor("foo"), phase: "manifest", error: new Error("broken") },
      activate: async (manifestUrl, manifest): Promise<LoadedPlugin> => {
        activated.push(manifestUrl);
        return { manifest };
      },
      builtinSources: [],
      discoverLocal: discovery.discoverLocal,
    });

    manager.bootstrap(store);
    await flushMicrotasks();
    const source = localSourceFor("foo");
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "error" });
    expect(activated).toEqual([]);

    // The manifest is fixed in place; a refresh re-attempts the still-present source.
    isManifestOk = true;
    await manager.refreshLocalSources(store);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded", kind: "local" });
    expect(activated).toHaveLength(1);
  });

  it("refresh shadows a newcomer that competes with an already-active plugin (no auto-promote)", async () => {
    const store = createStore();
    const activated: Array<string> = [];
    const discovery = makeMutableDiscovery();
    const manager = new PluginManager({
      // Both the bundled built-in and the late-arriving local plugin report the
      // same id, so they compete for it.
      fetchManifest: async (): Promise<{ manifest: PluginManifest }> => ({ manifest: manifestFor("shared") }),
      activate: async (manifestUrl, manifest): Promise<LoadedPlugin> => {
        activated.push(manifestUrl);
        return { manifest };
      },
      builtinSources: [{ path: "/plugins/bundled-ver" }],
      discoverLocal: discovery.discoverLocal,
    });

    manager.bootstrap(store);
    await flushMicrotasks();
    expect(store.get(pluginSourceStatesAtom)["/plugins/bundled-ver"]).toMatchObject({ status: "loaded" });

    // A local plugin for the same id appears later. Even though local outranks
    // builtin in bootstrap priority, refresh must NOT promote it over the active
    // built-in — it settles shadowed, leaving the switch to the user.
    discovery.set([localRef("late")]);
    await manager.refreshLocalSources(store);
    const source = localSourceFor("late");
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({
      status: "shadowed",
      kind: "local",
      activeSource: "/plugins/bundled-ver",
    });
    expect(store.get(pluginSourceStatesAtom)["/plugins/bundled-ver"]).toMatchObject({ status: "loaded" });
  });

  it("refresh leaves a still-loaded local plugin running even after it disappears from disk", async () => {
    const store = createStore();
    const loader = makeRecordingLoader();
    const discovery = makeMutableDiscovery([localRef("foo")]);
    const manager = new PluginManager({ ...loader, builtinSources: [], discoverLocal: discovery.discoverLocal });

    manager.bootstrap(store);
    await flushMicrotasks();
    const source = localSourceFor("foo");
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded" });

    // We deliberately don't tear down a live plugin that vanishes mid-session —
    // it keeps running (and its panel stays) until the next full reload.
    discovery.set([]);
    await manager.refreshLocalSources(store);
    expect(store.get(pluginSourceStatesAtom)[source]).toMatchObject({ status: "loaded", kind: "local" });
    expect(store.get(pluginPanelsAtom).map((p) => p.id)).toEqual(["foo"]);
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

describe("PluginManager sculpt-command handling", () => {
  // A served dev-mount source path (as `sculpt plugin load <dir>` produces); the
  // fake loader derives the plugin id "alpha" from the directory name.
  const DEV_SOURCE = "/plugins/local/dev/ws1/alpha/manifest.json";

  const command = (
    op: PluginCommandUiAction["op"],
    extra: Partial<PluginCommandUiAction> = {},
  ): PluginCommandUiAction => ({ workspaceId: "ws1", correlationId: "c1", op, ...extra });

  // A loader that fetches the manifest fine but throws from activate — the
  // common "uploaded + dispatched, then failed to run" case.
  const failingActivateManager = (): PluginManager =>
    new PluginManager({
      builtinSources: [],
      fetchManifest: async (manifestUrl) => ({ manifest: manifestFor(idFromManifestUrl(manifestUrl)) }),
      activate: async (_url, manifest): Promise<PluginLoadError> => ({
        manifest,
        phase: "activate",
        error: new Error("activate blew up"),
      }),
    });

  it("reports ok:false when a load dispatches but the plugin then fails to activate", async () => {
    const store = createStore();
    const manager = failingActivateManager();

    const result = await manager.handlePluginCommand(store, command("load", { source: DEV_SOURCE }));

    expect(result.ok).toBe(false);
    expect(result.error).toContain("activate");
    expect(result.plugins?.[0]).toMatchObject({ pluginId: "alpha", status: "error", origin: "dev" });
  });

  it("makes a failed plugin addressable by id: inspect finds it, unload clears the stale row", async () => {
    const store = createStore();
    const manager = failingActivateManager();
    await manager.handlePluginCommand(store, command("load", { source: DEV_SOURCE }));

    const inspected = await manager.handlePluginCommand(store, command("inspect", { pluginId: "alpha" }));
    expect((inspected.plugins ?? []).map((p) => p.pluginId)).toEqual(["alpha"]);
    expect(inspected.plugins?.[0]?.status).toBe("error");

    const unloaded = await manager.handlePluginCommand(store, command("unload", { pluginId: "alpha" }));
    expect(unloaded.ok).toBe(true);
    // The stale error row is gone immediately — no app reload needed.
    expect(store.get(pluginSourceStatesAtom)[DEV_SOURCE]).toBeUndefined();
    const listed = await manager.handlePluginCommand(store, command("list"));
    expect(listed.plugins ?? []).toEqual([]);
  });

  it("also addresses a failed plugin by its source path", async () => {
    const store = createStore();
    const manager = failingActivateManager();
    await manager.handlePluginCommand(store, command("load", { source: DEV_SOURCE }));

    const inspected = await manager.handlePluginCommand(store, command("inspect", { pluginId: DEV_SOURCE }));
    expect((inspected.plugins ?? []).map((p) => p.pluginId)).toEqual(["alpha"]);
  });

  it("attributes a plugin's overlays in inspect registrations", async () => {
    const store = createStore();
    const manager = new PluginManager({
      builtinSources: [],
      fetchManifest: async (manifestUrl): Promise<{ manifest: PluginManifest }> => ({
        manifest: manifestFor(idFromManifestUrl(manifestUrl)),
      }),
      activate: async (_url, manifest, makeApi): Promise<LoadedPlugin> => {
        makeApi(manifest).registerOverlay({ id: `${manifest.id}-overlay`, component: (): null => null });
        return { manifest, dispose: vi.fn() };
      },
    });

    await manager.addSource(store, "/plugins/beta");
    const inspected = await manager.handlePluginCommand(store, command("inspect", { pluginId: "beta" }));

    expect(inspected.plugins?.[0]?.registrations?.overlays).toEqual(["beta-overlay"]);
  });

  it("keeps a manifest-phase failure addressable by its source key, not the manifest url", async () => {
    const store = createStore();
    // A manifest fetch/parse failure yields a synthetic manifest whose id is the
    // URL, not a real plugin id — so the snapshot must fall back to the source
    // key, and the failure must be addressable by it.
    const manager = new PluginManager({
      builtinSources: [],
      fetchManifest: async (manifestUrl): Promise<PluginLoadError> => ({
        manifest: { id: manifestUrl, name: manifestUrl, version: "?", entry: "", sdkVersion: "?" },
        phase: "manifest",
        error: new Error("not valid JSON"),
      }),
      activate: async (_url, manifest): Promise<LoadedPlugin> => ({ manifest, dispose: vi.fn() }),
    });
    const source = "/plugins/local/dev/ws1/broken/manifest.json";

    const result = await manager.handlePluginCommand(store, command("load", { source }));
    expect(result.ok).toBe(false);
    expect(result.plugins?.[0]?.pluginId).toBe(source);

    const inspected = await manager.handlePluginCommand(store, command("inspect", { pluginId: source }));
    expect((inspected.plugins ?? []).map((p) => p.pluginId)).toEqual([source]);
  });
});
