import type { createStore } from "jotai";
import type { ComponentType, ReactElement } from "react";

import { getLocalPlugins } from "~/api";
import { baseUrl } from "~/apiClient.ts";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { queryClient, SCULPTOR_QUERY_KEY_PREFIX } from "~/common/queryClient.ts";
import type { PanelDefinition } from "~/components/panels/types.ts";

import { installHostRuntime } from "./hostRuntime.ts";
import { PluginContext } from "./PluginContext.tsx";
import { PluginErrorBoundary } from "./PluginErrorBoundary.tsx";
import {
  pluginDisabledSourcesAtom,
  pluginEnabledSourcesAtom,
  pluginOverlaysAtom,
  pluginPanelsAtom,
  pluginSettingsComponentsAtom,
  type PluginSourceKind,
  pluginSourcesAtom,
  type PluginSourceState,
  pluginSourceStatesAtom,
} from "./pluginRegistry.ts";
import type {
  LoadedPlugin,
  OverlayDefinition,
  PluginHostApi,
  PluginLoadError,
  PluginManifest,
  PluginModule,
} from "./types.ts";
import { WorkspacePluginContext } from "./WorkspaceContext.tsx";

type JotaiStore = ReturnType<typeof createStore>;

type ApiFactory = (manifest: PluginManifest) => PluginHostApi;

/**
 * The loader runs in two phases so the manager can resolve conflicts between
 * sources that provide the same plugin id *before* any of them activates. A
 * loser that activated first would clobber the winner's contributions
 * (registration is replace-by-id) and rolling it back would leave a hole, so
 * the id must be claimed between fetch and activate:
 *   1. `ManifestFetcher` — fetch + validate the manifest only (no plugin code runs).
 *   2. `Activator` — import the entry module and run `activate()`.
 */
type ManifestResult = { manifest: PluginManifest } | PluginLoadError;
type ManifestFetcher = (manifestUrl: string) => Promise<ManifestResult>;
type Activator = (
  manifestUrl: string,
  manifest: PluginManifest,
  makeApi: ApiFactory,
  cacheBust?: string,
) => Promise<LoadedPlugin | PluginLoadError>;

/**
 * When several sources provide the same plugin id, only one may be active; the
 * higher-priority one (lower number) wins and the rest are shadowed. Local dev
 * plugins beat a remotely-added URL, which beats the bundled built-in — so a
 * developer's working copy wins by default, while the choice stays overridable
 * by disabling the winner (which persists, so it survives a reload).
 */
const KIND_PRIORITY: Record<PluginSourceKind, number> = { local: 0, url: 1, builtin: 2 };

/**
 * Source paths the backend reserves for its own dynamic plugin mounts
 * (`/plugins/local/…`, `/plugins/from-workspace/…`). A built-in must never live
 * at one of these, or it would shadow the mount. The build enforces this; the
 * manager drops any offending built-in as defense in depth.
 */
const RESERVED_BUILTIN_PATHS: ReadonlySet<string> = new Set(["/plugins/local", "/plugins/from-workspace"]);

/**
 * Cap on a single manifest fetch during bootstrap. Bootstrap waits for every
 * source's manifest before resolving conflicts by priority; a slow or hung
 * remote URL must not stall built-in/local plugins forever, so it loses the
 * race after this timeout and the others resolve without it.
 */
const MANIFEST_FETCH_TIMEOUT_MS = 5000;

/**
 * A built-in plugin shipped in the app bundle. `path` is the app-origin-relative
 * source it loads from (served from `public/plugins/<id>/`). `disabledByDefault`
 * ships the plugin off until the user opts in via the settings toggle — use it
 * for built-ins that need configuration before they do anything useful (e.g. an
 * API key) so they don't clutter a fresh install. The opt-in is remembered
 * across launches (see `pluginEnabledSourcesAtom`).
 */
type BuiltinSource = { path: string; disabledByDefault?: boolean };

/**
 * Built-in plugin sources, loaded on boot (when the frontend-plugins flag is
 * on) regardless of the user's saved list, and not removable from the settings
 * UI. They serve from `public/plugins/<id>/`.
 */
const BUILTIN_SOURCES: ReadonlyArray<BuiltinSource> = [
  { path: "/plugins/sculpty" },
  { path: "/plugins/pomodoro" },
  { path: "/plugins/linear-issue" },
];

/** A plugin the backend discovered in the Sculptor plugins directory (the data folder's `plugins/`). */
export type LocalPluginRef = { id: string; manifestUrl: string };

/**
 * Ask the backend which plugins live in the Sculptor plugins directory. Read-only, so
 * it skips the websocket-ack round-trip. Returns `[]` on any failure — a
 * discovery hiccup must not block built-in or user sources from loading.
 */
const discoverLocalPluginsFromBackend = async (): Promise<ReadonlyArray<LocalPluginRef>> => {
  const { data } = await getLocalPlugins({ meta: { skipWsAck: true } });
  return data ?? [];
};

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

/** Phase 1: fetch + validate the manifest (no plugin code runs). */
const fetchManifestFromNetwork: ManifestFetcher = async (manifestUrl) => {
  let manifest: PluginManifest;
  try {
    const res = await fetch(manifestUrl, { cache: "no-store", signal: AbortSignal.timeout(MANIFEST_FETCH_TIMEOUT_MS) });
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
  return { manifest };
};

/** Phase 2: dynamic-import the bundle and run `activate`. */
const activateFromNetwork: Activator = async (manifestUrl, manifest, makeApi, cacheBust) => {
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
  private readonly fetchManifest: ManifestFetcher;
  private readonly activate: Activator;
  private readonly discoverLocal: () => Promise<ReadonlyArray<LocalPluginRef>>;
  /** Built-in definitions keyed by their normalized source path. */
  private readonly builtinByPath: ReadonlyMap<string, BuiltinSource>;
  /** Normalized source strings discovered in the Sculptor plugins directory this session. */
  private readonly localSources = new Set<string>();
  private readonly disposersBySource = new Map<string, Array<() => void>>();
  /** Plugin id each source has claimed (set when claimed, before activation). Inverse of activeByPluginId. */
  private readonly pluginIdBySource = new Map<string, string>();
  /** Which source currently owns each plugin id — at most one; the active (or activating) source. */
  private readonly activeByPluginId = new Map<string, string>();
  private readonly loadSeqBySource = new Map<string, number>();
  private hasBootstrapped = false;

  constructor(options?: {
    fetchManifest?: ManifestFetcher;
    activate?: Activator;
    builtinSources?: ReadonlyArray<BuiltinSource>;
    discoverLocal?: () => Promise<ReadonlyArray<LocalPluginRef>>;
  }) {
    this.fetchManifest = options?.fetchManifest ?? fetchManifestFromNetwork;
    this.activate = options?.activate ?? activateFromNetwork;
    this.discoverLocal = options?.discoverLocal ?? discoverLocalPluginsFromBackend;
    // Drop any built-in squatting a reserved dynamic-mount path — it could never
    // load (the backend mount shadows it) and would mask that mount.
    this.builtinByPath = new Map(
      (options?.builtinSources ?? BUILTIN_SOURCES)
        .map((b) => [normalizeSource(b.path), b] as const)
        .filter(([path]) => {
          if (RESERVED_BUILTIN_PATHS.has(path)) {
            console.error(`[plugins] ignoring built-in at reserved path "${path}"`);
            return false;
          }
          return true;
        }),
    );
  }

  /** Classify a source so its state row and edit affordances match its origin. */
  private kindOf(source: string): PluginSourceKind {
    if (this.builtinByPath.has(source)) return "builtin";
    if (this.localSources.has(source)) return "local";
    return "url";
  }

  /**
   * The absolute manifest URL to fetch/import for a source. Local plugins are
   * served by the backend, whose origin (host:port) differs from the renderer's
   * in the packaged build and can change between launches — so their source is
   * stored *relative* (a stable identity for persisted enable/disable choices)
   * and resolved against the backend origin here, at load time. Built-in and
   * user sources are used as-is (built-ins resolve against the renderer origin;
   * user URLs are already absolute).
   */
  private manifestUrlForLoad(source: string): string {
    const manifestPath = normalizeManifestUrl(source);
    if (this.localSources.has(source)) {
      return new URL(manifestPath, baseUrl || window.location.origin).toString();
    }
    return manifestPath;
  }

  /** Record `source` as the active owner of `pluginId` (claimed before activation). */
  private claim(pluginId: string, source: string): void {
    this.activeByPluginId.set(pluginId, source);
    this.pluginIdBySource.set(source, pluginId);
  }

  /** Drop `source`'s claim on whatever plugin id it owns, if any. */
  private release(source: string): void {
    const pluginId = this.pluginIdBySource.get(source);
    if (pluginId === undefined) return;
    this.pluginIdBySource.delete(source);
    if (this.activeByPluginId.get(pluginId) === source) {
      this.activeByPluginId.delete(pluginId);
    }
  }

  /**
   * Loads built-in, persisted-user, and discovered-local sources, resolving any
   * that provide the same plugin id down to a single active one. Runs once per
   * instance (one instance per page load).
   *
   * Two phases, because the winner among same-id sources is chosen by priority
   * and we must know every candidate's id before deciding: (1) fetch all
   * manifests, then (2) per id, activate the highest-priority source and shadow
   * the rest. A manifest that fails to fetch (or times out) simply loses. The
   * work runs off the synchronous call so callers aren't blocked on the network.
   */
  bootstrap(store: JotaiStore): void {
    installHostRuntime();
    if (this.hasBootstrapped) return;
    this.hasBootstrapped = true;
    this.installQueryKeyNamespaceGuard();
    void this.bootstrapAsync(store);
  }

  private async bootstrapAsync(store: JotaiStore): Promise<void> {
    // Dedupe by source, keeping the first (highest-precedence) kind, so a path
    // that is both a built-in and a stale persisted user source can't appear
    // twice and compete with itself.
    const seenSources = new Set<string>();
    const candidates: Array<{ source: string; kind: PluginSourceKind }> = [];
    const addCandidate = (source: string, kind: PluginSourceKind): void => {
      if (!source || seenSources.has(source)) return;
      seenSources.add(source);
      candidates.push({ source, kind });
    };
    for (const path of this.builtinByPath.keys()) addCandidate(path, "builtin");
    for (const s of store.get(pluginSourcesAtom)) addCandidate(normalizeSource(s), "url");
    for (const c of await this.discoverLocalCandidates()) addCandidate(c.source, c.kind);

    // Disabled sources never fetch — they settle straight into a "disabled" row.
    // Everything else shows "loading" until phase 2 resolves it.
    const toFetch: Array<{ source: string; kind: PluginSourceKind }> = [];
    for (const c of candidates) {
      if (this.isDisabled(store, c.source, c.kind)) {
        this.setSourceState(store, c.source, { status: "disabled", kind: c.kind });
      } else {
        this.setSourceState(store, c.source, { status: "loading", kind: c.kind });
        toFetch.push(c);
      }
    }

    // Phase 1: fetch every manifest concurrently.
    const fetched = await Promise.all(
      toFetch.map(async (c) => ({ ...c, result: await this.fetchManifest(this.manifestUrlForLoad(c.source)) })),
    );

    // Phase 2: drop fetch failures, group the rest by plugin id, resolve each.
    const byId = new Map<string, Array<{ source: string; kind: PluginSourceKind; manifest: PluginManifest }>>();
    for (const f of fetched) {
      if ("phase" in f.result) {
        this.setSourceState(store, f.source, {
          status: "error",
          kind: f.kind,
          phase: f.result.phase,
          message: f.result.error.message,
        });
        continue;
      }
      const id = f.result.manifest.id;
      const group = byId.get(id) ?? [];
      group.push({ source: f.source, kind: f.kind, manifest: f.result.manifest });
      byId.set(id, group);
    }
    await Promise.all([...byId.values()].map((group) => this.resolveGroup(store, group)));
  }

  /**
   * Discover local plugin sources (the Sculptor plugins directory) and register them so `kindOf` knows
   * they're local. Returns [] (logged) on discovery failure so the rest of
   * bootstrap proceeds. Each is stored as the RELATIVE plugin directory (e.g.
   * `/plugins/local/foo`) — a port-stable identity; it's resolved against the
   * backend origin at load time (see `manifestUrlForLoad`).
   */
  private async discoverLocalCandidates(): Promise<Array<{ source: string; kind: PluginSourceKind }>> {
    let refs: ReadonlyArray<LocalPluginRef>;
    try {
      refs = await this.discoverLocal();
    } catch (e) {
      console.error("[plugins] failed to discover local plugins", e);
      return [];
    }
    const out: Array<{ source: string; kind: PluginSourceKind }> = [];
    for (const ref of refs) {
      // Strip the manifest filename so the source is the plugin directory:
      // matches how built-in/user sources are stored, keeps the identity port-
      // independent, and makes the settings row show the id, not "manifest.json".
      const source = normalizeSource(ref.manifestUrl.replace(/\/manifest\.json$/, ""));
      if (!source) {
        console.error(`[plugins] skipping local plugin "${ref.id}" — empty manifest URL "${ref.manifestUrl}"`);
        continue;
      }
      this.localSources.add(source);
      out.push({ source, kind: "local" });
    }
    return out;
  }

  /**
   * Re-scan the Sculptor plugins directory on demand (the settings Refresh button) and
   * reconcile against what's currently tracked, so a plugin dropped in (or a
   * broken manifest fixed) is picked up without a full reload. Discovery is a
   * one-shot imperative fetch — there's a single consumer (this manager) and a
   * WS push is the eventual plan — so it deliberately doesn't go through
   * TanStack.
   *
   * - Newly-appeared, returned-from-missing, or previously-errored sources are
   *   (re)loaded, honoring any persisted disable and the conflict rules (a new
   *   arrival that competes with an already-active source is shadowed, not
   *   promoted over it — same no-auto-promote contract as a manual enable).
   * - A source gone from disk that is still loaded is left running (we don't
   *   handle live disappearance). One that isn't loaded is dropped — but if the
   *   user had a persisted on/off choice, it stays as a `missing` dead-trace row
   *   so that choice is visible and re-applied if the plugin returns.
   * - Built-in and user URL sources are untouched; this only re-scans local.
   */
  async refreshLocalSources(store: JotaiStore): Promise<void> {
    let refs: ReadonlyArray<LocalPluginRef>;
    try {
      refs = await this.discoverLocal();
    } catch (e) {
      console.error("[plugins] refresh: failed to discover local plugins", e);
      return;
    }
    const discovered = new Set<string>();
    for (const ref of refs) {
      const source = normalizeSource(ref.manifestUrl.replace(/\/manifest\.json$/, ""));
      if (source) discovered.add(source);
    }

    // (Re)load the ones not already settled: brand new (undefined), back after
    // going missing, or previously errored (a fixed manifest). Leave loaded /
    // loading / disabled / shadowed rows as they are. `loadSource` is the
    // interactive path — if another source already holds the plugin id it
    // settles into "shadowed" rather than promoting over it, which is exactly
    // the no-auto-promote contract we want for a newcomer.
    const toLoad: Array<string> = [];
    for (const source of discovered) {
      this.localSources.add(source);
      const status = store.get(pluginSourceStatesAtom)[source]?.status;
      if (status === undefined || status === "missing" || status === "error") toLoad.push(source);
    }
    await Promise.all(
      toLoad.map((source) => {
        // A persisted disable means it should settle straight into a "disabled"
        // row without fetching — `loadSource` doesn't consult the disabled set.
        if (this.isDisabled(store, source, "local")) {
          this.setSourceState(store, source, { status: "disabled", kind: "local" });
          return Promise.resolve();
        }
        return this.loadSource(store, source, "local");
      }),
    );

    for (const source of [...this.localSources]) {
      if (discovered.has(source)) continue;
      const status = store.get(pluginSourceStatesAtom)[source]?.status;
      if (status === "loaded") continue; // leave a still-loaded plugin running
      if (this.hasPersistedChoice(store, source)) {
        this.unloadSource(source);
        this.setSourceState(store, source, { status: "missing", kind: "local" });
      } else {
        this.localSources.delete(source);
        this.unloadSource(source);
        this.setSourceState(store, source, undefined);
      }
    }
  }

  /** Whether the user has an explicit, persisted enable/disable choice for a source. */
  private hasPersistedChoice(store: JotaiStore, source: string): boolean {
    return (
      store.get(pluginDisabledSourcesAtom).includes(source) || store.get(pluginEnabledSourcesAtom).includes(source)
    );
  }

  /**
   * Activate the highest-priority source in a same-id group and shadow the rest.
   * If the chosen one fails to activate, fall through to the next by priority
   * (so a broken local dev copy doesn't block the bundled version). Sources
   * after the active one are shadowed and point at it for the conflict tooltip.
   */
  private async resolveGroup(
    store: JotaiStore,
    group: Array<{ source: string; kind: PluginSourceKind; manifest: PluginManifest }>,
  ): Promise<void> {
    // Primary order: kind priority. Tie-break on discovery order (index within
    // the group) so the winner is deterministic without relying on Array.sort
    // stability — e.g. two local plugins with the same id resolve to the one the
    // backend listed first (directories are sorted by name).
    const ordered = group
      .map((item, index) => ({ item, index }))
      .sort((a, b) => KIND_PRIORITY[a.item.kind] - KIND_PRIORITY[b.item.kind] || a.index - b.index)
      .map((entry) => entry.item);
    let activeSource: string | undefined;
    for (const item of ordered) {
      if (activeSource !== undefined) {
        this.setSourceState(store, item.source, {
          status: "shadowed",
          kind: item.kind,
          manifest: item.manifest,
          activeSource,
        });
        continue;
      }
      const seq = this.bumpSeq(item.source);
      this.claim(item.manifest.id, item.source);
      const didLoad = await this.activateClaimed(store, item.source, item.kind, item.manifest, seq);
      if (didLoad) {
        activeSource = item.source;
      } else if (this.loadSeqBySource.get(item.source) === seq) {
        this.release(item.source);
      }
    }
  }

  /**
   * Whether this source should stay unloaded. An explicit user choice wins
   * (disabled set, then enabled set, both persisted across launches); absent
   * any choice, a built-in shipped `disabledByDefault` stays off and everything
   * else loads.
   */
  private isDisabled(store: JotaiStore, source: string, kind: PluginSourceKind = this.kindOf(source)): boolean {
    if (store.get(pluginDisabledSourcesAtom).includes(source)) return true;
    if (store.get(pluginEnabledSourcesAtom).includes(source)) return false;
    return kind === "builtin" && this.builtinByPath.get(source)?.disabledByDefault === true;
  }

  /**
   * Enables or disables a source without removing it from the list. Disabling
   * unloads its contributions and parks the row in a "disabled" state;
   * enabling re-loads it from scratch. The disabled set is persisted, so the
   * choice survives a reload — this is the opt-out for built-in plugins and the
   * mute switch for remotely-pulled-in sources.
   */
  async setSourceEnabled(store: JotaiStore, source: string, enabled: boolean): Promise<void> {
    const normalized = normalizeSource(source);
    const kind = this.kindOf(normalized);
    const status = store.get(pluginSourceStatesAtom)[normalized]?.status;

    // Keep the source in at most one of the two override sets, so the chosen
    // state is unambiguous and survives a reload (the enabled set is what holds
    // a `disabledByDefault` built-in — or a user-promoted competitor — on).
    const disabled = store.get(pluginDisabledSourcesAtom).filter((s) => s !== normalized);
    const enabledOverrides = store.get(pluginEnabledSourcesAtom).filter((s) => s !== normalized);

    if (enabled) {
      if (status === "loaded") return; // already active
      store.set(pluginDisabledSourcesAtom, disabled);
      store.set(pluginEnabledSourcesAtom, [...enabledOverrides, normalized]);
      // (Re)attempt the load. If another source still holds this plugin id, the
      // load settles into a "shadowed" row rather than activating — the manager
      // never lets two sources be active for one id.
      await this.loadSource(store, normalized, kind);
    } else {
      if (status === "disabled") return;
      store.set(pluginDisabledSourcesAtom, [...disabled, normalized]);
      store.set(pluginEnabledSourcesAtom, enabledOverrides);
      this.unloadSource(normalized); // frees its plugin id so a shadowed sibling can be enabled
      this.setSourceState(store, normalized, { status: "disabled", kind });
    }
  }

  /** Adds a user source (persisted) and loads it immediately. No-op if duplicate. */
  async addSource(store: JotaiStore, rawSource: string): Promise<void> {
    // Normalize (trim + drop trailing slashes) so `/plugins/foo` and
    // `/plugins/foo/` can't be stored as distinct sources or slip past the
    // duplicate/builtin guard below.
    const source = normalizeSource(rawSource);
    if (!source) return;
    const existing = store.get(pluginSourcesAtom);
    // Reject anything already managed under another origin — a built-in path or
    // a discovered local source — so it can't be duplicated as a user URL.
    if (existing.includes(source) || this.builtinByPath.has(source) || this.localSources.has(source)) return;
    store.set(pluginSourcesAtom, [...existing, source]);
    await this.loadSource(store, source, "url");
  }

  /** Removes a user source (persisted), unloads its contributions, and clears its status. */
  removeSource(store: JotaiStore, source: string): void {
    store.set(
      pluginSourcesAtom,
      store.get(pluginSourcesAtom).filter((s) => s !== source),
    );
    // Drop any enable/disable override too, so re-adding the same source later
    // starts from its default state rather than inheriting a stale choice.
    store.set(
      pluginDisabledSourcesAtom,
      store.get(pluginDisabledSourcesAtom).filter((s) => s !== source),
    );
    store.set(
      pluginEnabledSourcesAtom,
      store.get(pluginEnabledSourcesAtom).filter((s) => s !== source),
    );
    // Also forget it as a discovered-local source: this is the path that clears
    // a `missing` dead-trace row (a present local source is read-only and has no
    // remove control; a re-scan would re-add a still-present one anyway).
    this.localSources.delete(source);
    this.unloadSource(source);
    this.setSourceState(store, source, undefined);
  }

  /** Unloads then re-loads a source with a cache-busted import (dev iteration). */
  async reloadSource(store: JotaiStore, source: string): Promise<void> {
    const kind = this.kindOf(source);
    this.unloadSource(source);
    await this.loadSource(store, source, kind, String(Date.now()));
  }

  private bumpSeq(source: string): number {
    const seq = (this.loadSeqBySource.get(source) ?? 0) + 1;
    this.loadSeqBySource.set(source, seq);
    return seq;
  }

  /**
   * Interactive load (add / enable / reload): fetch the manifest, then claim the
   * plugin id. If another source already holds that id, settle into a "shadowed"
   * row instead of activating — so loading a competing version never clobbers the
   * active one. Bootstrap uses `resolveGroup` instead (priority among a known set).
   */
  private async loadSource(
    store: JotaiStore,
    source: string,
    kind: PluginSourceKind,
    cacheBust?: string,
  ): Promise<void> {
    const seq = this.bumpSeq(source);
    this.setSourceState(store, source, { status: "loading", kind });

    // `fetchManifest` shouldn't throw, but a synchronous fault (e.g. bad URL)
    // in an injected/edge implementation would; treat it as a load-phase error.
    const result = await this.fetchManifest(this.manifestUrlForLoad(source)).catch(
      (e): PluginLoadError => ({
        manifest: { id: source, name: source, version: "?", entry: "", sdkVersion: "?" },
        phase: "load",
        error: e instanceof Error ? e : new Error(String(e)),
      }),
    );
    if (this.loadSeqBySource.get(source) !== seq) return; // superseded while fetching

    if ("phase" in result) {
      console.error(`Plugin manifest load failed (${result.phase}) for "${source}"`, result.error);
      this.setSourceState(store, source, { status: "error", kind, phase: result.phase, message: result.error.message });
      return;
    }

    const manifest = result.manifest;
    const owner = this.activeByPluginId.get(manifest.id);
    if (owner !== undefined && owner !== source) {
      this.setSourceState(store, source, { status: "shadowed", kind, manifest, activeSource: owner });
      return;
    }

    this.claim(manifest.id, source);
    const didLoad = await this.activateClaimed(store, source, kind, manifest, seq, cacheBust);
    // Release only if this attempt is still current — a same-source reload that
    // superseded us has re-claimed the id under the same string and owns it now.
    if (!didLoad && this.loadSeqBySource.get(source) === seq) this.release(source);
  }

  /**
   * Phase 2 for a source whose plugin id is already claimed: import + activate,
   * honoring the sequence token so a load superseded mid-flight rolls back and
   * commits nothing. Returns whether the plugin ended up loaded.
   */
  private async activateClaimed(
    store: JotaiStore,
    source: string,
    kind: PluginSourceKind,
    manifest: PluginManifest,
    seq: number,
    cacheBust?: string,
  ): Promise<boolean> {
    // Registrations made during this attempt collect here and are only committed
    // if the attempt is still current once activate() resolves.
    const loadDisposers: Array<() => void> = [];
    let outcome: LoadedPlugin | PluginLoadError;
    try {
      outcome = await this.activate(
        this.manifestUrlForLoad(source),
        manifest,
        (m) => this.makeApi(store, m, loadDisposers),
        cacheBust,
      );
    } catch (e) {
      outcome = { manifest, phase: "load", error: e instanceof Error ? e : new Error(String(e)) };
    }

    if (this.loadSeqBySource.get(source) !== seq) {
      // A newer load/unload/remove superseded this attempt. Roll back anything
      // activate() registered and leave all shared state alone.
      if (!("phase" in outcome) && outcome.dispose) loadDisposers.push(outcome.dispose);
      this.runDisposers(source, loadDisposers);
      return false;
    }

    if ("phase" in outcome) {
      console.error(`Plugin load failed (${outcome.phase}) for "${source}"`, outcome.error);
      // A plugin can register panels/settings/overlays and *then* throw (or
      // return an error) from activate(); roll those back so an errored source
      // leaves no live contributions behind.
      this.runDisposers(source, loadDisposers);
      this.setSourceState(store, source, {
        status: "error",
        kind,
        phase: outcome.phase,
        message: outcome.error.message,
      });
      return false;
    }

    if (outcome.dispose) loadDisposers.push(outcome.dispose);
    this.disposersBySource.set(source, loadDisposers);
    // The plugin id was already recorded by `claim`; activation just confirms it.
    this.setSourceState(store, source, { status: "loaded", kind, manifest: outcome.manifest });
    return true;
  }

  private unloadSource(source: string): void {
    this.bumpSeq(source); // invalidate any in-flight load for this source
    this.release(source); // free its plugin id so a shadowed sibling can claim it
    this.runDisposers(source, this.disposersBySource.get(source) ?? []);
    this.disposersBySource.delete(source);
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
      registerOverlay: (overlay: OverlayDefinition): (() => void) => {
        // Like a panel, wrap in the error boundary and PluginContext, but with
        // no WorkspacePluginContext: an overlay is app-global, so it reads the
        // current workspace through the SDK hooks instead of a fixed context.
        const PluginComponent = overlay.component;
        // Attribute crashes to the owning plugin (manifest), matching the panel
        // path — not to the overlay contribution id.
        const Wrapped = (): ReactElement => (
          <PluginErrorBoundary pluginId={manifest.id} pluginName={manifest.name}>
            <PluginContext.Provider value={{ pluginId: manifest.id }}>
              <PluginComponent />
            </PluginContext.Provider>
          </PluginErrorBoundary>
        );
        Wrapped.displayName = `PluginOverlay(${overlay.id})`;
        const entry = { id: overlay.id, component: Wrapped };

        // Replace-by-id; undo by instance (see the panel undo above).
        store.set(pluginOverlaysAtom, (prev) => [...prev.filter((o) => o.id !== overlay.id), entry]);
        const undo = (): void => {
          store.set(pluginOverlaysAtom, (prev) => prev.filter((o) => o !== entry));
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
