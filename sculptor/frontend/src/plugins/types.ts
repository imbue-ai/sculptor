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
 * hooks (`useWorkspaces`, `useCurrentWorkspace`) to react to app state —
 * there is no single workspace context, because an overlay outlives any one
 * workspace page.
 */
export type OverlayDefinition = {
  /** Stable id; registering twice with the same id replaces the previous one. */
  id: string;
  component: ComponentType;
};

/**
 * A compact, workspace-scoped contribution the host places in its workspace
 * chrome — today the workspace banner's action row, beside the PR button.
 * Deliberately named for the contribution (a small widget) rather than a
 * location: the same registration is what a future per-workspace vertical-tabs
 * layout would render too, so plugins don't re-register per surface.
 *
 * Like a panel (and unlike an app-global overlay) it is mounted inside the
 * host's `WorkspacePluginContext`, so the workspace SDK hooks
 * (`useCurrentWorkspace`, `useWorkspaceTasks`, per-workspace `usePluginSetting`
 * keys) resolve to the workspace it is rendered for.
 */
export type WorkspaceWidgetDefinition = {
  /** Stable id; registering twice with the same id replaces the previous one. */
  id: string;
  component: ComponentType;
  /**
   * Where the widget sits in the host's progressive-collapse order when the row
   * runs out of horizontal room: lower values are hidden first, higher values
   * survive longer (the banner's PR button is the most protected built-in). A
   * host without a collapsing container — e.g. the future vertical-tabs layout —
   * is free to ignore this. Built-in banner items occupy a few small integers,
   * so pick a value that orders the widget relative to them; omit it to collapse
   * before everything else.
   */
  collapsePriority?: number;
};

/**
 * A full-page contribution the host offers as an alternative homepage body. The
 * homepage shows a view switcher whenever at least one of these is registered;
 * picking one replaces the built-in recent-workspaces list with the plugin's
 * component, which owns the entire content area below the switcher. The user's
 * choice is remembered, and falls back to the built-in view if the selected
 * plugin is later unloaded.
 *
 * Like an app-global overlay (and unlike a panel/workspace widget) it is mounted
 * with no `WorkspacePluginContext`: the homepage is not scoped to a single
 * workspace, so a home view reads app state through the SDK hooks
 * (`useWorkspaces`, `useCurrentWorkspace`) instead of a fixed context.
 */
export type HomeViewDefinition = {
  /** Stable id; registering twice with the same id replaces the previous one. */
  id: string;
  /** Label shown for this view in the homepage switcher. */
  title: string;
  /**
   * Optional Lucide icon shown beside the title in the switcher. Typed to accept
   * a `size` prop so the switcher can render it at a consistent size rather than
   * Lucide's 24px default (which sits taller than the segmented-control text).
   */
  icon?: ComponentType<{ size?: number | string }>;
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
  /**
   * Registers a workspace-scoped widget the host renders in its workspace
   * chrome (the banner action row beside the PR button). Wrapped, like a panel,
   * in a per-plugin error boundary, the host's PluginContext, and the
   * WorkspacePluginContext for the workspace it is shown in. Returns a disposer.
   */
  registerWorkspaceWidget: (widget: WorkspaceWidgetDefinition) => () => void;
  /**
   * Registers a full-page home view selectable from the homepage switcher.
   * Wrapped, like an overlay, in a per-plugin error boundary and the host's
   * PluginContext (so `usePluginSetting` works), but with no
   * WorkspacePluginContext — the homepage is not workspace-scoped. Returns a
   * disposer.
   */
  registerHomeView: (view: HomeViewDefinition) => () => void;
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
