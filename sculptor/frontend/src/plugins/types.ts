import type { ComponentType } from "react";

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
  /**
   * Semver range of @sculptor/plugin-sdk the plugin was built against. The
   * loader only enforces the major. Note there is deliberately no peer
   * dependency declaration: shared libraries resolve to host singletons via
   * the import map, and unenforced version ranges would be false confidence.
   * Versioned peers can return once the runtime stubs are generated from the
   * host's actual module namespaces.
   */
  sdkVersion: string;
};

/**
 * Object passed to a plugin's `activate()` function. Plugins use this to
 * contribute panels, commands, etc. Returning a disposer from `activate` lets
 * the host unmount/remove contributions when the plugin is unloaded.
 */
export type PluginHostApi = {
  registerPanel: (panel: PanelDefinition) => () => void;
  /**
   * Registers a settings component shown under the plugin in the Plugins
   * settings section. Rendered inside the host's PluginContext (so SDK hooks
   * like `usePluginSetting` work) and a per-plugin error boundary. Returns a
   * disposer.
   */
  registerSettings: (component: ComponentType) => () => void;
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
  /**
   * Where the load failed. `manifest`/`validate`/`import`/`activate` are the
   * known stages the loader returns. `load` is the catch-all the manager
   * assigns when the loader *throws* outright instead of returning one of the
   * above — so an unexpected loader fault still surfaces as an error state
   * rather than a stuck "loading" row.
   */
  phase: "manifest" | "validate" | "import" | "activate" | "load";
  error: Error;
};
