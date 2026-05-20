import { atom } from "jotai";

import type { PanelDefinition } from "~/components/panels/types.ts";

import type { PluginLoadError, PluginManifest } from "./types.ts";

/**
 * Panels contributed by loaded plugins, ready to be merged into the host's
 * static `workspacePanels` list and handed to `PanelRegistryProvider`.
 */
export const pluginPanelsAtom = atom<ReadonlyArray<PanelDefinition>>([]);

/** Manifests for plugins that have successfully loaded. */
export const loadedPluginManifestsAtom = atom<ReadonlyArray<PluginManifest>>([]);

/** Errors from plugins that failed to load — surfaced for diagnostics. */
export const pluginLoadErrorsAtom = atom<ReadonlyArray<PluginLoadError>>([]);
