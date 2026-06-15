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
export const pluginOverlaysAtom = atom<ReadonlyArray<{ id: string; component: ComponentType }>>([]);

/**
 * User-added plugin sources, persisted to localStorage. A source is a URL or
 * directory that contains a `manifest.json` (e.g. `http://localhost:5174/my-plugin`
 * or `/plugins/my-plugin`). Built-in sources are loaded separately and are not
 * stored here. This list is the source of truth for what the user wants loaded;
 * the actual registration is re-derived from it on every boot.
 */
export const pluginSourcesAtom = atomWithStorage<ReadonlyArray<string>>("sculptor-plugin-sources", []);

/** Per-source load status, keyed by the source string (built-in + user). */
export type PluginSourceState =
  | { status: "loading"; isBuiltin: boolean }
  | { status: "loaded"; isBuiltin: boolean; manifest: PluginManifest }
  | { status: "error"; isBuiltin: boolean; phase: string; message: string };

/**
 * Runtime status for every source the manager has tried to load. Not
 * persisted — rebuilt as sources load on boot and when the user edits them.
 */
export const pluginSourceStatesAtom = atom<Readonly<Record<string, PluginSourceState>>>({});
