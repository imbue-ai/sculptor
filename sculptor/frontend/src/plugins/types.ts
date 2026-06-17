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
   * loader only enforces the major. There is still deliberately no peer
   * dependency declaration: shared libraries resolve to host singletons via
   * the import map. Enforceable peer ranges are now unblocked — the host's
   * real package versions are embedded at build time and exposed on
   * `window.__SCULPTOR_HOST__.versions` (see hostRuntime.ts) — but the
   * manifest field and loader check are left for a follow-up.
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
