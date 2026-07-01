import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";
import type { ComponentType } from "react";

import type { PanelDefinition } from "~/components/panels/types.ts";

import type { PluginManifest } from "./types.ts";

/**
 * Panels contributed by loaded plugins, ready to be merged into the host's
 * static `workspacePanels` list and handed to `PanelRegistryProvider`.
 */
export const pluginPanelsAtom = atom<ReadonlyArray<PanelDefinition>>([]);

/**
 * Settings components contributed by plugins via `registerSettings`, keyed by
 * plugin id. The Plugins settings section renders these under each plugin.
 */
export const pluginSettingsComponentsAtom = atom<Readonly<Record<string, ComponentType>>>({});

/**
 * Always-on floating overlays contributed by plugins via `registerOverlay`.
 * `PluginOverlays` renders each one above the whole app, in registration
 * order. Each entry's component is already wrapped by the loader in an error
 * boundary and the plugin's PluginContext.
 */
// `pluginId` attributes each overlay to its owning plugin so `inspect` can list
// a plugin's overlays; it's the manifest id, not the per-overlay contribution id.
export const pluginOverlaysAtom = atom<ReadonlyArray<{ id: string; component: ComponentType; pluginId: string }>>([]);

/**
 * Workspace-scoped widgets contributed by plugins via `registerWorkspaceWidget`.
 * The workspace banner renders each one in its action row, ordered (and
 * progressively collapsed) by `collapsePriority`. Each entry's component is
 * already wrapped by the loader in an error boundary and the plugin's
 * PluginContext; the banner supplies the per-render WorkspacePluginContext.
 */
export const pluginWorkspaceWidgetsAtom = atom<
  ReadonlyArray<{ id: string; component: ComponentType; collapsePriority: number }>
>([]);

/**
 * Full-page home views contributed by plugins via `registerHomeView`. The
 * homepage shows a switcher (built-in recent-workspaces view plus each of
 * these) whenever this list is non-empty, and renders the selected one in place
 * of the built-in list. Each entry's component is already wrapped by the loader
 * in an error boundary and the plugin's PluginContext (no WorkspacePluginContext
 * — the homepage is not workspace-scoped).
 */
export const pluginHomeViewsAtom = atom<
  ReadonlyArray<{ id: string; title: string; icon?: ComponentType; component: ComponentType }>
>([]);

/**
 * User-added plugin sources, persisted to localStorage. A source is a URL or
 * directory that contains a `manifest.json` (e.g. `http://localhost:5174/my-plugin`
 * or `/plugins/my-plugin`). Built-in sources are loaded separately and are not
 * stored here. This list is the source of truth for what the user wants loaded;
 * the actual registration is re-derived from it on every boot.
 */
// `getOnInit: true` so the very first synchronous `store.get` (pluginManager
// bootstrap, before any React component mounts the atom) reads the persisted
// value from localStorage instead of returning the default `[]`. Without it,
// saved sources would silently fail to load on app startup.
export const pluginSourcesAtom = atomWithStorage<ReadonlyArray<string>>("sculptor-plugin-sources", [], undefined, {
  getOnInit: true,
});

/**
 * Sources the user has explicitly disabled, persisted to localStorage. A
 * disabled source stays on the list (built-in, local, or user) but is not
 * loaded: its `activate()` never runs and it contributes no
 * panels/overlays/settings. This is what lets the user opt out of a built-in
 * plugin, or silence a remotely-pulled-in source, without deleting the
 * reference entirely.
 *
 * `getOnInit: true` for the same reason as `pluginSourcesAtom`: the manager's
 * synchronous bootstrap (before any component mounts) must see the persisted
 * value, or a source the user disabled would load anyway on the next launch.
 */
export const pluginDisabledSourcesAtom = atomWithStorage<ReadonlyArray<string>>(
  "sculptor-plugin-disabled-sources",
  [],
  undefined,
  { getOnInit: true },
);

/**
 * Sources the user has explicitly *enabled*, persisted to localStorage. Only
 * meaningful for built-ins shipped `disabledByDefault`: those start off, and a
 * source's presence here is what records the user opting *in* (so the choice
 * survives a reload, distinct from "never touched it"). For ordinary sources
 * — enabled-by-default built-ins, discovered local plugins, user URLs — this
 * set is irrelevant: absence from `pluginDisabledSourcesAtom` already means
 * enabled. `getOnInit: true` for the same bootstrap reason as the atoms above.
 */
export const pluginEnabledSourcesAtom = atomWithStorage<ReadonlyArray<string>>(
  "sculptor-plugin-enabled-sources",
  [],
  undefined,
  { getOnInit: true },
);

/**
 * Where a source came from. `builtin` ships in the app bundle (served from
 * `/plugins/<id>`); `local` was discovered in the Sculptor plugins directory
 * (the data folder's `plugins/`) and is served by the backend; `url` is a
 * source the user added by hand. Only `url`
 * sources are user-removable and persisted in `pluginSourcesAtom`; `builtin`
 * and `local` are re-derived on every boot.
 */
export type PluginSourceKind = "builtin" | "local" | "url";

/** Per-source load status, keyed by the source string (built-in + local + user). */
export type PluginSourceState =
  | { status: "loading"; kind: PluginSourceKind }
  | { status: "loaded"; kind: PluginSourceKind; manifest: PluginManifest }
  // `pluginId` is the manifest id when the failure happened after the manifest
  // parsed (validate/import/activate); absent when even the manifest couldn't be
  // read. Retaining it lets `inspect`/`unload` address a failed plugin by id
  // rather than only by its source path.
  | { status: "error"; kind: PluginSourceKind; phase: string; message: string; pluginId?: string }
  | { status: "disabled"; kind: PluginSourceKind }
  // Another source provides the same plugin `id` and is the one that loaded;
  // this one is shown but not active. `activeSource` is that winner, named in
  // the conflict tooltip. Manifest is known (it fetched fine) so the row can
  // still show the plugin's name/version.
  | { status: "shadowed"; kind: PluginSourceKind; manifest: PluginManifest; activeSource: string }
  // A discovered local source that a refresh found gone from disk, but whose
  // on/off choice the user had persisted — kept as a dead-trace row so that
  // choice is visible and re-applied if the plugin returns. (A source with no
  // persisted choice is dropped outright instead.)
  | { status: "missing"; kind: PluginSourceKind };

/**
 * Runtime status for every source the manager has tried to load. Not
 * persisted — rebuilt as sources load on boot and when the user edits them.
 */
export const pluginSourceStatesAtom = atom<Readonly<Record<string, PluginSourceState>>>({});
