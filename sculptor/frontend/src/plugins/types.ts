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
/**
 * An always-on, app-global floating contribution. Unlike a panel, an overlay
 * is not tied to a zone or a single workspace: the host renders it above the
 * whole app (across every route) for as long as the plugin is loaded. The
 * component draws into a full-viewport, click-through layer, so it must opt
 * its own interactive box back into pointer events. Use the workspace SDK
 * hooks (`useWorkspaces`, `useCurrentWorkspaceId`) to react to app state —
 * there is no single workspace context, because an overlay outlives any one
 * workspace page.
 */
export type OverlayDefinition = {
  /** Stable id; registering twice with the same id replaces the previous one. */
  id: string;
  component: ComponentType;
};

export type PluginHostApi = {
  registerPanel: (panel: PanelDefinition) => () => void;
  /**
   * Registers a settings component shown under the plugin in the Plugins
   * settings section. Rendered inside the host's PluginContext (so SDK hooks
   * like `usePluginSetting` work) and a per-plugin error boundary. Returns a
   * disposer.
   */
  registerSettings: (component: ComponentType) => () => void;
  /**
   * Registers an always-on floating overlay rendered above the whole app.
   * Wrapped, like panels, in a per-plugin error boundary and the host's
   * PluginContext (so `usePluginSetting` works). Returns a disposer.
   */
  registerOverlay: (overlay: OverlayDefinition) => () => void;
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
