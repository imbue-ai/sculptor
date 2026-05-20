import type { PanelDefinition } from "~/components/panels/types.ts";

/**
 * The manifest a plugin ships alongside its bundle. Loaded by the host before
 * the plugin's JavaScript is fetched, so that version compatibility can be
 * checked up front.
 */
export type PluginManifest = {
  id: string;
  name: string;
  version: string;
  /** Path (relative to /plugins/) to the plugin's ESM entry. */
  entry: string;
  /** Semver range of @sculptor/plugin-sdk the plugin was built against. */
  sdkVersion: string;
  /** Peer dependencies that resolve to host singletons via the import map. */
  peerDependencies?: Record<string, string>;
};

/**
 * Object passed to a plugin's `activate()` function. Plugins use this to
 * contribute panels, commands, etc. Returning a disposer from `activate` lets
 * the host unmount/remove contributions when the plugin is unloaded.
 */
export type PluginHostApi = {
  registerPanel: (panel: PanelDefinition) => () => void;
};

export type PluginActivate = (api: PluginHostApi) => void | (() => void) | Promise<void | (() => void)>;

export type PluginModule = {
  default: PluginActivate;
};

export type LoadedPlugin = {
  manifest: PluginManifest;
  dispose?: () => void;
};

export type PluginLoadError = {
  manifest: PluginManifest;
  phase: "manifest" | "validate" | "import" | "activate";
  error: Error;
};
