import { atom } from "jotai";
import { atomWithStorage } from "jotai/utils";
import type { ComponentType } from "react";

import type { ExtensionManifest, ExtensionPanelDefinition } from "./types.ts";

/**
 * The pre-rename ("sculptor-plugin…") localStorage key behind each persisted
 * source-list key below. Read only by the one-time migration; new writes always
 * go to the current keys.
 */
const LEGACY_KEY_BY_NEW_KEY: Readonly<Record<string, string>> = {
  "sculptor-extension-sources": "sculptor-plugin-sources",
  "sculptor-extension-disabled-sources": "sculptor-plugin-disabled-sources",
  "sculptor-extension-enabled-sources": "sculptor-plugin-enabled-sources",
};

/** Legacy and current namespaces for per-extension settings (see the SDK's `useExtensionSetting`). */
const LEGACY_SETTING_KEY_PREFIX = "sculptor-plugin:";
const SETTING_KEY_PREFIX = "sculptor-extension:";

/**
 * Rewrite a persisted source-list value for the current backend mounts: an
 * app-origin-relative source under the old `/plugins/` static prefix now lives
 * under `/extensions/` (built-ins, installed local mounts, and dev mounts
 * alike). Absolute user URLs pass through untouched — a `/plugins/` path inside
 * a foreign origin's URL is that server's business, not ours. A value that
 * isn't a JSON string array is copied verbatim rather than dropped.
 */
const rewriteLegacySourceList = (value: string): string => {
  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return value;
    return JSON.stringify(
      parsed.map((entry) =>
        typeof entry === "string" && entry.startsWith("/plugins/")
          ? `/extensions/${entry.slice("/plugins/".length)}`
          : entry,
      ),
    );
  } catch {
    return value;
  }
};

/**
 * One-time copy of persisted extension state from the pre-rename localStorage
 * keys to the current ones, so users keep their sources, enable/disable
 * choices, and per-extension settings across the rename. A value is copied only
 * when the current key is absent (an already-written new value wins), and the
 * old keys are left in place so an older build sharing this origin still finds
 * its state. Exported for unit tests; production runs it once at module init.
 */
export const migrateLegacyExtensionStorage = (storage: Storage): void => {
  for (const [newKey, legacyKey] of Object.entries(LEGACY_KEY_BY_NEW_KEY)) {
    const legacyValue = storage.getItem(legacyKey);
    if (legacyValue === null || storage.getItem(newKey) !== null) continue;
    storage.setItem(newKey, rewriteLegacySourceList(legacyValue));
  }

  // Per-extension settings: sweep the whole legacy namespace. Collect the keys
  // before writing — setItem while indexing with storage.key(i) would shift the
  // iteration order mid-scan.
  const legacySettingKeys: Array<string> = [];
  for (let i = 0; i < storage.length; i++) {
    const key = storage.key(i);
    if (key !== null && key.startsWith(LEGACY_SETTING_KEY_PREFIX)) legacySettingKeys.push(key);
  }

  for (const legacyKey of legacySettingKeys) {
    const newKey = SETTING_KEY_PREFIX + legacyKey.slice(LEGACY_SETTING_KEY_PREFIX.length);
    const legacyValue = storage.getItem(legacyKey);
    if (legacyValue === null || storage.getItem(newKey) !== null) continue;
    storage.setItem(newKey, legacyValue);
  }
};

// Run the migration at module init: the storage-backed atoms below use
// `getOnInit: true`, which reads localStorage as soon as the atom is first
// touched, so the copied values must be in place before anything else in this
// module is used. localStorage may be unavailable or throw (privacy modes);
// extensions then start from defaults, matching how the atoms themselves degrade.
try {
  if (typeof localStorage !== "undefined") migrateLegacyExtensionStorage(localStorage);
} catch {
  // Nothing to migrate if storage is inaccessible.
}

/**
 * Panels contributed by loaded extensions. The extension manager merges these into the
 * new section shell's `panelRegistryAtom` (via the per-workspace registry sync) so
 * `SectionBody` can resolve and render them. Each entry's component is already
 * wrapped by the loader in an error boundary and the extension's contexts.
 */
export const extensionPanelsAtom = atom<ReadonlyArray<ExtensionPanelDefinition>>([]);

/**
 * Settings components contributed by extensions via `registerSettings`, keyed by
 * extension id. The Extensions settings section renders these under each extension.
 */
export const extensionSettingsComponentsAtom = atom<Readonly<Record<string, ComponentType>>>({});

/**
 * Always-on floating overlays contributed by extensions via `registerOverlay`.
 * `ExtensionOverlays` renders each one above the whole app, in registration
 * order. Each entry's component is already wrapped by the loader in an error
 * boundary and the extension's ExtensionContext.
 */
// `extensionId` attributes each overlay to its owning extension so `inspect` can list
// an extension's overlays; it's the manifest id, not the per-overlay contribution id.
export const extensionOverlaysAtom = atom<ReadonlyArray<{ id: string; component: ComponentType; extensionId: string }>>(
  [],
);

/**
 * Workspace-scoped widgets contributed by extensions via `registerWorkspaceWidget`.
 * The workspace banner renders each one in its action row, ordered by
 * `collapsePriority` (higher values rendered nearer the PR button). Each entry's component is
 * already wrapped by the loader in an error boundary and the extension's
 * ExtensionContext; the banner supplies the per-render WorkspaceExtensionContext.
 */
export const extensionWorkspaceWidgetsAtom = atom<
  ReadonlyArray<{ id: string; component: ComponentType; collapsePriority: number }>
>([]);

/**
 * Full-page home views contributed by extensions via `registerHomeView`. The
 * homepage shows a switcher (built-in recent-workspaces view plus each of
 * these) whenever this list is non-empty, and renders the selected one in place
 * of the built-in list. Each entry's component is already wrapped by the loader
 * in an error boundary and the extension's ExtensionContext (no WorkspaceExtensionContext
 * — the homepage is not workspace-scoped).
 */
export const extensionHomeViewsAtom = atom<
  ReadonlyArray<{ id: string; title: string; icon?: ComponentType; component: ComponentType }>
>([]);

/**
 * User-added extension sources, persisted to localStorage. A source is a URL or
 * directory that contains a `manifest.json` (e.g. `http://localhost:5174/my-extension`
 * or `/extensions/my-extension`). Built-in sources are loaded separately and are not
 * stored here. This list is the source of truth for what the user wants loaded;
 * the actual registration is re-derived from it on every boot.
 */
// `getOnInit: true` so the very first synchronous `store.get` (extensionManager
// bootstrap, before any React component mounts the atom) reads the persisted
// value from localStorage instead of returning the default `[]`. Without it,
// saved sources would silently fail to load on app startup.
export const extensionSourcesAtom = atomWithStorage<ReadonlyArray<string>>(
  "sculptor-extension-sources",
  [],
  undefined,
  {
    getOnInit: true,
  },
);

/**
 * Sources the user has explicitly disabled, persisted to localStorage. A
 * disabled source stays on the list (built-in, local, or user) but is not
 * loaded: its `activate()` never runs and it contributes no
 * panels/overlays/settings. This is what lets the user opt out of a built-in
 * extension, or silence a remotely-pulled-in source, without deleting the
 * reference entirely.
 *
 * `getOnInit: true` for the same reason as `extensionSourcesAtom`: the manager's
 * synchronous bootstrap (before any component mounts) must see the persisted
 * value, or a source the user disabled would load anyway on the next launch.
 */
export const extensionDisabledSourcesAtom = atomWithStorage<ReadonlyArray<string>>(
  "sculptor-extension-disabled-sources",
  [],
  undefined,
  { getOnInit: true },
);

/**
 * Sources the user has explicitly *enabled*, persisted to localStorage. Only
 * meaningful for built-ins shipped `disabledByDefault`: those start off, and a
 * source's presence here is what records the user opting *in* (so the choice
 * survives a reload, distinct from "never touched it"). For ordinary sources
 * — enabled-by-default built-ins, discovered local extensions, user URLs — this
 * set is irrelevant: absence from `extensionDisabledSourcesAtom` already means
 * enabled. `getOnInit: true` for the same bootstrap reason as the atoms above.
 */
export const extensionEnabledSourcesAtom = atomWithStorage<ReadonlyArray<string>>(
  "sculptor-extension-enabled-sources",
  [],
  undefined,
  { getOnInit: true },
);

/**
 * Where a source came from. `builtin` ships in the app bundle (served from
 * `/extensions/<id>`); `local` was discovered in the Sculptor extensions directory
 * (the data folder's `extensions/`) and is served by the backend; `url` is a
 * source the user added by hand. Only `url`
 * sources are user-removable and persisted in `extensionSourcesAtom`; `builtin`
 * and `local` are re-derived on every boot.
 */
export type ExtensionSourceKind = "builtin" | "local" | "url";

/** Per-source load status, keyed by the source string (built-in + local + user). */
export type ExtensionSourceState =
  | { status: "loading"; kind: ExtensionSourceKind }
  | { status: "loaded"; kind: ExtensionSourceKind; manifest: ExtensionManifest }
  // `extensionId` is the manifest id when the failure happened after the manifest
  // parsed (validate/import/activate); absent when even the manifest couldn't be
  // read. Retaining it lets `inspect`/`unload` address a failed extension by id
  // rather than only by its source path.
  | { status: "error"; kind: ExtensionSourceKind; phase: string; message: string; extensionId?: string }
  | { status: "disabled"; kind: ExtensionSourceKind }
  // Another source provides the same extension `id` and is the one that loaded;
  // this one is shown but not active. `activeSource` is that winner, named in
  // the conflict tooltip. Manifest is known (it fetched fine) so the row can
  // still show the extension's name/version.
  | { status: "shadowed"; kind: ExtensionSourceKind; manifest: ExtensionManifest; activeSource: string }
  // A discovered local source that a refresh found gone from disk, but whose
  // on/off choice the user had persisted — kept as a dead-trace row so that
  // choice is visible and re-applied if the extension returns. (A source with no
  // persisted choice is dropped outright instead.)
  | { status: "missing"; kind: ExtensionSourceKind };

/**
 * Runtime status for every source the manager has tried to load. Not
 * persisted — rebuilt as sources load on boot and when the user edits them.
 */
export const extensionSourceStatesAtom = atom<Readonly<Record<string, ExtensionSourceState>>>({});
