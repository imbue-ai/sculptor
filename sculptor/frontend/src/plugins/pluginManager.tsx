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

type ApiFactory = (manifest: PluginManifest) => PluginHostApi;
type LoaderFn = (
  manifestUrl: string,
  makeApi: ApiFactory,
  cacheBust?: string,
) => Promise<LoadedPlugin | PluginLoadError>;

/**
 * Built-in plugin sources, always loaded (when the frontend-plugins flag is
 * on) regardless of the user's saved list, and not removable from the
 * settings UI. Empty in the base scaffolding — no plugin ships bundled yet;
 * sources serve from `public/plugins/<id>/`.
 */
const BUILTIN_SOURCES: ReadonlyArray<string> = [];

/** SDK major version the host currently provides. */
const HOST_SDK_VERSION = 1;

const parseMajor = (range: string): number | null => {
  const match = range.match(/(\d+)/);
  return match ? Number(match[1]) : null;
};

/** Exported for unit testing; the loader calls it after fetching the manifest. */
export const validateManifest = (manifest: PluginManifest): Error | null => {
  // The manifest is parsed from untrusted JSON and only *cast* to the type, so
  // re-check the required fields are non-empty strings at runtime. This both
  // gives a clear "validate"-phase error for a malformed manifest and keeps a
  // non-string `entry`/`sdkVersion` from throwing inside parseMajor/resolveEntryUrl
  // (which would otherwise surface as the opaque catch-all "load" error).
  const fields = manifest as unknown as Record<string, unknown>;
  for (const key of ["id", "entry", "sdkVersion"] as const) {
    if (typeof fields[key] !== "string" || fields[key] === "") {
      return new Error(`Manifest field "${key}" must be a non-empty string`);
    }
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

/** Normalize a user-entered source for storage/comparison: trim and drop trailing slashes. */
const normalizeSource = (raw: string): string => raw.trim().replace(/\/+$/, "");

/** Turn a user-entered source (URL or directory) into a manifest URL. */
const normalizeManifestUrl = (source: string): string => {
  const trimmed = normalizeSource(source);
  return trimmed.endsWith(".json") ? trimmed : `${trimmed}/manifest.json`;
};

/**
 * Resolve a manifest's `entry` against the manifest's *own* URL. A path-only
 * source (`/plugins/foo/manifest.json`) resolves against the app origin; an
 * absolute cross-origin source (`http://127.0.0.1:8765/foo/manifest.json`)
 * resolves `entry` against that origin, so a plugin served from a local dev
 * server loads its `main.js` from the same place its manifest came from.
 */
export const resolveEntryUrl = (manifestUrl: string, entry: string): string =>
  new URL(entry, new URL(manifestUrl, window.location.origin)).toString();

/** Fetch + validate a manifest, dynamic-import the bundle, run `activate`. */
const loadOneFromNetwork: LoaderFn = async (manifestUrl, makeApi, cacheBust) => {
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

  const entryUrl = resolveEntryUrl(manifestUrl, manifest.entry);
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
    const result = await mod.default(makeApi(manifest));
    const dispose = typeof result === "function" ? result : undefined;
    return { manifest, dispose };
  } catch (e) {
    return { manifest, phase: "activate", error: e instanceof Error ? e : new Error(String(e)) };
  }
};

/**
 * Owns the runtime plugin lifecycle: bootstrapping built-in plus persisted
 * user sources, and add/remove/reload of individual sources.
 *
 * One instance exists per page load (`pluginManager` below). Plugins are
 * app-session singletons, so instance state survives React remounts and
 * StrictMode's dev double-invoke; the bootstrap guard makes the initial load
 * run exactly once.
 *
 * Every load attempt for a source takes a **sequence token**. Unload and
 * reload bump the token, so an in-flight load that loses the race detects it
 * is stale when its `await` resumes: it disposes anything it registered
 * during `activate()` and commits nothing — a source removed mid-load cannot
 * resurrect its panel or its status row.
 */
export class PluginManager {
  private readonly loadOne: LoaderFn;
  private readonly builtinSources: ReadonlyArray<string>;
  private readonly disposersBySource = new Map<string, Array<() => void>>();
  private readonly pluginIdBySource = new Map<string, string>();
  private readonly loadSeqBySource = new Map<string, number>();
  private hasBootstrapped = false;

  constructor(options?: { loadOne?: LoaderFn; builtinSources?: ReadonlyArray<string> }) {
    this.loadOne = options?.loadOne ?? loadOneFromNetwork;
    this.builtinSources = options?.builtinSources ?? BUILTIN_SOURCES;
  }

  /**
   * Loads built-in plugins plus every persisted user source. Runs once per
   * instance (and one instance per page load).
   */
  bootstrap(store: JotaiStore): void {
    installHostRuntime();
    if (this.hasBootstrapped) return;
    this.hasBootstrapped = true;
    this.installQueryKeyNamespaceGuard();

    const userSources = store.get(pluginSourcesAtom);
    for (const source of this.builtinSources) void this.loadSource(store, source, true);
    for (const source of userSources) void this.loadSource(store, source, false);
  }

  /** Adds a user source (persisted) and loads it immediately. No-op if duplicate. */
  async addSource(store: JotaiStore, rawSource: string): Promise<void> {
    // Normalize (trim + drop trailing slashes) so `/plugins/foo` and
    // `/plugins/foo/` can't be stored as distinct sources or slip past the
    // duplicate/builtin guard below.
    const source = normalizeSource(rawSource);
    if (!source) return;
    const existing = store.get(pluginSourcesAtom);
    if (existing.includes(source) || this.builtinSources.includes(source)) return;
    store.set(pluginSourcesAtom, [...existing, source]);
    await this.loadSource(store, source, false);
  }

  /** Removes a user source (persisted), unloads its contributions, and clears its status. */
  removeSource(store: JotaiStore, source: string): void {
    store.set(
      pluginSourcesAtom,
      store.get(pluginSourcesAtom).filter((s) => s !== source),
    );
    this.unloadSource(source);
    this.setSourceState(store, source, undefined);
  }

  /** Unloads then re-loads a source with a cache-busted import (dev iteration). */
  async reloadSource(store: JotaiStore, source: string): Promise<void> {
    const current = store.get(pluginSourceStatesAtom)[source];
    const isBuiltin = current?.isBuiltin ?? this.builtinSources.includes(source);
    this.unloadSource(source);
    await this.loadSource(store, source, isBuiltin, String(Date.now()));
  }

  private bumpSeq(source: string): number {
    const seq = (this.loadSeqBySource.get(source) ?? 0) + 1;
    this.loadSeqBySource.set(source, seq);
    return seq;
  }

  private async loadSource(store: JotaiStore, source: string, isBuiltin: boolean, cacheBust?: string): Promise<void> {
    const seq = this.bumpSeq(source);
    this.setSourceState(store, source, { status: "loading", isBuiltin });

    // Registrations made during this load attempt collect here and are only
    // committed if the attempt is still current once the import resolves.
    const loadDisposers: Array<() => void> = [];
    let outcome: LoadedPlugin | PluginLoadError;
    try {
      outcome = await this.loadOne(
        normalizeManifestUrl(source),
        (manifest) => this.makeApi(store, manifest, loadDisposers),
        cacheBust,
      );
    } catch (e) {
      // A loader is expected to *return* a PluginLoadError, never throw. Guard
      // against one that throws anyway (e.g. a synchronous URL-construction
      // failure) so the source settles into an error state instead of being
      // stranded in "loading" forever.
      outcome = {
        manifest: { id: source, name: source, version: "?", entry: "", sdkVersion: "?" },
        phase: "load",
        error: e instanceof Error ? e : new Error(String(e)),
      };
    }

    if (this.loadSeqBySource.get(source) !== seq) {
      // A newer load/unload/remove superseded this attempt while the import
      // was in flight. Roll back anything activate() registered and leave
      // all shared state alone.
      if (!("phase" in outcome) && outcome.dispose) loadDisposers.push(outcome.dispose);
      this.runDisposers(source, loadDisposers);
      return;
    }

    if ("phase" in outcome) {
      console.error(`Plugin load failed (${outcome.phase}) for "${source}"`, outcome.error);
      this.setSourceState(store, source, {
        status: "error",
        isBuiltin,
        phase: outcome.phase,
        message: outcome.error.message,
      });
      return;
    }

    if (outcome.dispose) loadDisposers.push(outcome.dispose);
    this.disposersBySource.set(source, loadDisposers);
    this.pluginIdBySource.set(source, outcome.manifest.id);
    this.setSourceState(store, source, { status: "loaded", isBuiltin, manifest: outcome.manifest });
  }

  private unloadSource(source: string): void {
    this.bumpSeq(source); // invalidate any in-flight load for this source
    this.runDisposers(source, this.disposersBySource.get(source) ?? []);
    this.disposersBySource.delete(source);
    this.pluginIdBySource.delete(source);
  }

  private runDisposers(source: string, disposers: ReadonlyArray<() => void>): void {
    for (const dispose of disposers) {
      try {
        dispose();
      } catch (e) {
        console.error(`Plugin disposer threw for "${source}"`, e);
      }
    }
  }

  /** Builds the per-plugin `api` handed to `activate()`, backed by the given store. */
  private makeApi(store: JotaiStore, manifest: PluginManifest, loadDisposers: Array<() => void>): PluginHostApi {
    return {
      registerPanel: (panel: PanelDefinition): (() => void) => {
        // Wrap the plugin's component in the error boundary plus context
        // providers exposing the plugin id (for settings hooks) and the
        // current workspace id (read fresh per render from the route params).
        const PluginComponent = panel.component;
        const Wrapped = (): ReactElement | null => {
          const { workspaceID } = useWorkspacePageParams();
          if (!workspaceID) return null;
          return (
            // Attribute crashes to the plugin, not the individual panel — one
            // plugin can contribute several panels, and the error UI/logs should
            // name the plugin that owns them.
            <PluginErrorBoundary pluginId={manifest.id} pluginName={manifest.name}>
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

        // Replace-by-id so a panel can only ever be registered once. The undo
        // removes by *instance*, not id — a stale load attempt rolling itself
        // back must not clobber a newer registration under the same id.
        store.set(pluginPanelsAtom, (prev) => [...prev.filter((p) => p.id !== panel.id), wrappedPanel]);
        const undo = (): void => {
          store.set(pluginPanelsAtom, (prev) => prev.filter((p) => p !== wrappedPanel));
        };
        loadDisposers.push(undo);
        return undo;
      },
      registerSettings: (component: ComponentType): (() => void) => {
        store.set(pluginSettingsComponentsAtom, (prev) => ({ ...prev, [manifest.id]: component }));
        const undo = (): void => {
          store.set(pluginSettingsComponentsAtom, (prev) => {
            // Identity-scoped for the same reason as the panel undo above.
            if (prev[manifest.id] !== component) return prev;
            const next = { ...prev };
            delete next[manifest.id];
            return next;
          });
        };
        loadDisposers.push(undo);
        return undo;
      },
    };
  }

  private setSourceState(store: JotaiStore, source: string, state: PluginSourceState | undefined): void {
    store.set(pluginSourceStatesAtom, (prev) => {
      const next = { ...prev };
      if (state === undefined) {
        delete next[source];
      } else {
        next[source] = state;
      }
      return next;
    });
  }

  /** Membership test over the live plugin ids without allocating — the guard below runs per dev cache event. */
  private isRegisteredPluginId(candidate: string): boolean {
    for (const pluginId of this.pluginIdBySource.values()) {
      if (pluginId === candidate) return true;
    }
    return false;
  }

  /**
   * Dev-only guard for the shared QueryClient's key-namespace convention:
   * host keys start with the reserved "sculptor" prefix, plugin keys with the
   * plugin id. Anything else is a query that invalidation can't reach by
   * namespace — warn so the author (host or plugin) fixes the key shape.
   */
  private installQueryKeyNamespaceGuard(): void {
    if (!import.meta.env.DEV) return;
    queryClient.getQueryCache().subscribe((event) => {
      if (event.type !== "added") return;
      const first = event.query.queryKey[0];
      if (first === SCULPTOR_QUERY_KEY_PREFIX) return;
      if (typeof first === "string" && this.isRegisteredPluginId(first)) return;
      console.warn(
        `[plugins] query key outside any namespace: ${JSON.stringify(event.query.queryKey)} — ` +
          `host keys must start with "${SCULPTOR_QUERY_KEY_PREFIX}", plugin keys with the plugin id.`,
      );
    });
  }
}

/** The app-session singleton instance the UI talks to. */
export const pluginManager = new PluginManager();
