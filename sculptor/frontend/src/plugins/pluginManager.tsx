import type { createStore } from "jotai";
import type { ComponentType, ReactElement } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "~/common/queryClient.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { installHostRuntime } from "./hostRuntime.ts";
import { PluginContext } from "./PluginContext.tsx";
import { PluginErrorBoundary } from "./PluginErrorBoundary.tsx";
import {
  pluginPanelsAtom,
  pluginSettingsComponentsAtom,
  pluginSourcesAtom,
  type PluginSourceState,
  pluginSourceStatesAtom,
} from "./pluginRegistry.ts";
import type { LoadedPlugin, PluginHostApi, PluginLoadError, PluginManifest, PluginModule } from "./types.ts";
import { WorkspacePluginContext } from "./WorkspaceContext.tsx";

type JotaiStore = ReturnType<typeof createStore>;

/**
 * Built-in plugin sources, always loaded (when the frontend-plugins flag is
 * on) regardless of the user's saved list, and not removable from the
 * settings UI. Sources serve from `public/plugins/<id>/`.
 */
const BUILTIN_SOURCES: ReadonlyArray<string> = ["/plugins/linear-issue"];

/** SDK major version the host currently provides. */
const HOST_SDK_VERSION = 1;

// Module-level bookkeeping. Plugins are app-session singletons, so these maps
// and the bootstrap guard live at module scope and survive React remounts /
// StrictMode's dev double-invoke.
const disposersByPluginId = new Map<string, Array<() => void>>();
const pluginIdBySource = new Map<string, string>();
let hasBootstrapped = false;

const addDisposer = (pluginId: string, fn: () => void): void => {
  const list = disposersByPluginId.get(pluginId) ?? [];
  list.push(fn);
  disposersByPluginId.set(pluginId, list);
};

/**
 * Dev-only guard for the shared QueryClient's key-namespace convention: host
 * keys start with the reserved "sculptor" prefix, plugin keys with the plugin
 * id. Anything else is a query that invalidation can't reach by namespace —
 * warn so the author (host or plugin) fixes the key shape.
 */
const installQueryKeyNamespaceGuard = (): void => {
  if (!import.meta.env.DEV) return;
  queryClient.getQueryCache().subscribe((event) => {
    if (event.type !== "added") return;
    const first = event.query.queryKey[0];
    if (first === SCULPTOR_QUERY_KEY_PREFIX) return;
    if (typeof first === "string" && [...pluginIdBySource.values()].includes(first)) return;
    console.warn(
      `[plugins] query key outside any namespace: ${JSON.stringify(event.query.queryKey)} — ` +
        `host keys must start with "${SCULPTOR_QUERY_KEY_PREFIX}", plugin keys with the plugin id.`,
    );
  });
};

const parseMajor = (range: string): number | null => {
  const match = range.match(/(\d+)/);
  return match ? Number(match[1]) : null;
};

const validateManifest = (manifest: PluginManifest): Error | null => {
  if (!manifest.id || !manifest.entry || !manifest.sdkVersion) {
    return new Error("Manifest missing required fields (id, entry, sdkVersion)");
  }
  const major = parseMajor(manifest.sdkVersion);
  if (major === null) {
    return new Error(`Unparseable sdkVersion "${manifest.sdkVersion}"`);
  }

  if (major !== HOST_SDK_VERSION) {
    return new Error(`Plugin requires SDK major ${major}, host provides ${HOST_SDK_VERSION}`);
  }
  return null;
};

/** Turn a user-entered source (URL or directory) into a manifest URL. */
const normalizeManifestUrl = (source: string): string => {
  const trimmed = source.trim().replace(/\/+$/, "");
  return trimmed.endsWith(".json") ? trimmed : `${trimmed}/manifest.json`;
};

/** Builds the per-plugin `api` handed to `activate()`, backed by the given store. */
const makeApi = (store: JotaiStore, manifest: PluginManifest): PluginHostApi => ({
  registerPanel: (panel: PanelDefinition): (() => void) => {
    // Wrap the plugin's component in the error boundary plus context providers
    // exposing the plugin id (for settings hooks) and the current workspace id
    // (read fresh per render from the route params).
    const PluginComponent = panel.component;
    const Wrapped = (): ReactElement | null => {
      const { workspaceID } = useWorkspacePageParams();
      if (!workspaceID) return null;
      return (
        <PluginErrorBoundary pluginId={panel.id} pluginName={panel.displayName}>
          <PluginContext.Provider value={{ pluginId: manifest.id }}>
            <WorkspacePluginContext.Provider value={{ workspaceId: workspaceID }}>
              <PluginComponent />
            </WorkspacePluginContext.Provider>
          </PluginContext.Provider>
        </PluginErrorBoundary>
      );
    };
    Wrapped.displayName = `PluginPanel(${panel.id})`;
    const wrappedPanel: PanelDefinition = { ...panel, component: Wrapped, pluginId: manifest.id };

    // Replace-by-id so a panel can only ever be registered once.
    store.set(pluginPanelsAtom, (prev) => [...prev.filter((p) => p.id !== panel.id), wrappedPanel]);
    const undo = (): void => {
      store.set(pluginPanelsAtom, (prev) => prev.filter((p) => p.id !== panel.id));
    };
    addDisposer(manifest.id, undo);
    return undo;
  },
  registerSettings: (component: ComponentType): (() => void) => {
    store.set(pluginSettingsComponentsAtom, (prev) => ({ ...prev, [manifest.id]: component }));
    const undo = (): void => {
      store.set(pluginSettingsComponentsAtom, (prev) => {
        const next = { ...prev };
        delete next[manifest.id];
        return next;
      });
    };
    addDisposer(manifest.id, undo);
    return undo;
  },
});

const loadOne = async (
  manifestUrl: string,
  makeApiForManifest: (manifest: PluginManifest) => PluginHostApi,
  cacheBust?: string,
): Promise<LoadedPlugin | PluginLoadError> => {
  let manifest: PluginManifest;
  try {
    const res = await fetch(manifestUrl, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    manifest = (await res.json()) as PluginManifest;
  } catch (e) {
    return {
      manifest: { id: manifestUrl, name: manifestUrl, version: "?", entry: "", sdkVersion: "?" },
      phase: "manifest",
      error: e instanceof Error ? e : new Error(String(e)),
    };
  }

  const validationError = validateManifest(manifest);
  if (validationError) {
    return { manifest, phase: "validate", error: validationError };
  }

  const entryBase = manifestUrl.slice(0, manifestUrl.lastIndexOf("/"));
  const entryUrl = new URL(manifest.entry, window.location.origin + entryBase + "/").toString();
  // A cache-bust token forces the browser to re-fetch the module instead of
  // returning the previously-imported (cached) one — used by reload.
  const importUrl = cacheBust ? `${entryUrl}?t=${cacheBust}` : entryUrl;

  let mod: PluginModule;
  try {
    mod = (await import(/* @vite-ignore */ importUrl)) as PluginModule;
  } catch (e) {
    return { manifest, phase: "import", error: e instanceof Error ? e : new Error(String(e)) };
  }

  if (typeof mod.default !== "function") {
    return {
      manifest,
      phase: "activate",
      error: new Error("Plugin entry has no default-exported activate() function"),
    };
  }

  try {
    const result = await mod.default(makeApiForManifest(manifest));
    const dispose = typeof result === "function" ? result : undefined;
    return { manifest, dispose };
  } catch (e) {
    return { manifest, phase: "activate", error: e instanceof Error ? e : new Error(String(e)) };
  }
};

const setSourceState = (store: JotaiStore, source: string, state: PluginSourceState | undefined): void => {
  store.set(pluginSourceStatesAtom, (prev) => {
    const next = { ...prev };
    if (state === undefined) {
      delete next[source];
    } else {
      next[source] = state;
    }
    return next;
  });
};

const loadSource = async (store: JotaiStore, source: string, isBuiltin: boolean, cacheBust?: string): Promise<void> => {
  setSourceState(store, source, { status: "loading", isBuiltin });
  const outcome = await loadOne(normalizeManifestUrl(source), (manifest) => makeApi(store, manifest), cacheBust);

  if ("phase" in outcome) {
    console.error(`Plugin load failed (${outcome.phase}) for "${source}"`, outcome.error);
    setSourceState(store, source, {
      status: "error",
      isBuiltin,
      phase: outcome.phase,
      message: outcome.error.message,
    });
    return;
  }

  pluginIdBySource.set(source, outcome.manifest.id);
  // The panel/settings registrations already self-tracked their disposers via
  // addDisposer during activate; also run any cleanup the plugin returned.
  if (outcome.dispose) addDisposer(outcome.manifest.id, outcome.dispose);
  setSourceState(store, source, { status: "loaded", isBuiltin, manifest: outcome.manifest });
};

const unloadSource = (source: string): void => {
  const pluginId = pluginIdBySource.get(source);
  if (!pluginId) return;
  for (const dispose of disposersByPluginId.get(pluginId) ?? []) {
    try {
      dispose();
    } catch (e) {
      console.error(`Plugin disposer threw for "${pluginId}"`, e);
    }
  }
  disposersByPluginId.delete(pluginId);
  pluginIdBySource.delete(source);
};

/**
 * Loads built-in plugins plus every persisted user source. Runs once per page
 * load (guarded at module scope so StrictMode's dev double-invoke and any
 * remount don't trigger duplicate loads).
 */
export const bootstrapPlugins = (store: JotaiStore): void => {
  installHostRuntime();
  if (hasBootstrapped) return;
  hasBootstrapped = true;
  installQueryKeyNamespaceGuard();

  const userSources = store.get(pluginSourcesAtom);
  for (const source of BUILTIN_SOURCES) void loadSource(store, source, true);
  for (const source of userSources) void loadSource(store, source, false);
};

/** Adds a user source (persisted) and loads it immediately. No-op if duplicate. */
export const addPluginSource = async (store: JotaiStore, rawSource: string): Promise<void> => {
  const source = rawSource.trim();
  if (!source) return;
  const existing = store.get(pluginSourcesAtom);
  if (existing.includes(source) || BUILTIN_SOURCES.includes(source)) return;
  store.set(pluginSourcesAtom, [...existing, source]);
  await loadSource(store, source, false);
};

/** Removes a user source (persisted), unloads its panel, and clears its status. */
export const removePluginSource = (store: JotaiStore, source: string): void => {
  store.set(
    pluginSourcesAtom,
    store.get(pluginSourcesAtom).filter((s) => s !== source),
  );
  unloadSource(source);
  setSourceState(store, source, undefined);
};

/** Unloads then re-loads a source with a cache-busted import (dev iteration). */
export const reloadPluginSource = async (store: JotaiStore, source: string): Promise<void> => {
  const current = store.get(pluginSourceStatesAtom)[source];
  const isBuiltin = current?.isBuiltin ?? BUILTIN_SOURCES.includes(source);
  unloadSource(source);
  await loadSource(store, source, isBuiltin, String(Date.now()));
};
