import type { LucideIcon } from "lucide-react";
import type { ComponentType } from "react";

import type { SectionId } from "~/components/sections/sectionTypes.ts";

/**
 * A panel an extension contributes via `registerPanel`. The host renders the
 * `component` inside the section shell (the manager adapts this into the
 * host's internal registry shape). An extension panel is not auto-placed on load:
 * the user opens it from the section "+" / Cmd+K, which drops it into the
 * sub-section they pick. `defaultSection` is recorded on the registry entry but
 * no placement path reads it yet — it is reserved for a future default-placement
 * pass. The legacy `defaultZone` / `defaultShortcut` fields are accepted but
 * ignored — the docking shell they targeted is gone.
 */
export type ExtensionPanelDefinition = {
  /** Stable id; registering twice with the same id replaces the previous one. */
  id: string;
  displayName: string;
  icon: LucideIcon;
  component: ComponentType;
  /** Reserved: recorded on the registry entry, but no placement path reads it yet. */
  defaultSection?: SectionId;
  /** @deprecated Ignored — the zone/docking shell is gone. */
  defaultZone?: string;
  /** @deprecated Ignored — per-panel keybindings were removed. */
  defaultShortcut?: string;
  /** Secondary text shown under the panel's label in the add-panel dropdown. */
  description?: string;
  /** Set by the loader to the owning extension's id; not supplied by extensions. */
  extensionId?: string;
};

/**
 * The manifest an extension ships alongside its bundle. Loaded by the host before
 * the extension's JavaScript is fetched, so that version compatibility can be
 * checked up front.
 */
export type ExtensionManifest = {
  id: string;
  name: string;
  version: string;
  /** Path (relative to /extensions/) to the extension's ESM entry. */
  entry: string;
  /**
   * Semver range of @sculptor/extension-sdk the extension was built against. The
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
 * Object passed to an extension's `activate()` function. Extensions use this to
 * contribute panels, commands, etc. Returning a disposer from `activate` lets
 * the host unmount/remove contributions when the extension is unloaded.
 */
/**
 * An always-on, app-global floating contribution. Unlike a panel, an overlay
 * is not tied to a zone or a single workspace: the host renders it above the
 * whole app (across every route) for as long as the extension is loaded. The
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
 * layout would render too, so extensions don't re-register per surface.
 *
 * Like a panel (and unlike an app-global overlay) it is mounted inside the
 * host's `WorkspaceExtensionContext`, so the workspace SDK hooks
 * (`useCurrentWorkspace`, `useWorkspaceTasks`, per-workspace `useExtensionSetting`
 * keys) resolve to the workspace it is rendered for.
 */
export type WorkspaceWidgetDefinition = {
  /** Stable id; registering twice with the same id replaces the previous one. */
  id: string;
  component: ComponentType;
  /**
   * Orders extension widgets relative to one another within the action row: lower
   * values render first, higher values render nearer the PR button. It only
   * sorts extension widgets among themselves — built-in banner items are not part
   * of this ordering — and a host that lays the widgets out differently is free
   * to ignore it. Omit it to sort ahead of widgets that set a value.
   */
  collapsePriority?: number;
};

/**
 * A full-page contribution the host offers as an alternative homepage body. The
 * homepage shows a view switcher whenever at least one of these is registered;
 * picking one replaces the built-in recent-workspaces list with the extension's
 * component, which owns the entire content area below the switcher. The user's
 * choice is remembered, and falls back to the built-in view if the selected
 * extension is later unloaded.
 *
 * Like an app-global overlay (and unlike a panel/workspace widget) it is mounted
 * with no `WorkspaceExtensionContext`: the homepage is not scoped to a single
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

export type ExtensionHostApi = {
  registerPanel: (panel: ExtensionPanelDefinition) => () => void;
  /**
   * Registers a settings component shown under the extension in the Extensions
   * settings section. Rendered inside the host's ExtensionContext (so SDK hooks
   * like `useExtensionSetting` work) and a per-extension error boundary. Returns a
   * disposer.
   */
  registerSettings: (component: ComponentType) => () => void;
  /**
   * Registers an always-on floating overlay rendered above the whole app.
   * Wrapped, like panels, in a per-extension error boundary and the host's
   * ExtensionContext (so `useExtensionSetting` works). Returns a disposer.
   */
  registerOverlay: (overlay: OverlayDefinition) => () => void;
  /**
   * Registers a workspace-scoped widget the host renders in its workspace
   * chrome (the banner action row beside the PR button). Wrapped, like a panel,
   * in a per-extension error boundary, the host's ExtensionContext, and the
   * WorkspaceExtensionContext for the workspace it is shown in. Returns a disposer.
   */
  registerWorkspaceWidget: (widget: WorkspaceWidgetDefinition) => () => void;
  /**
   * Registers a full-page home view selectable from the homepage switcher.
   * Wrapped, like an overlay, in a per-extension error boundary and the host's
   * ExtensionContext (so `useExtensionSetting` works), but with no
   * WorkspaceExtensionContext — the homepage is not workspace-scoped. Returns a
   * disposer.
   */
  registerHomeView: (view: HomeViewDefinition) => () => void;
};

export type ExtensionActivate = (api: ExtensionHostApi) => void | (() => void) | Promise<void | (() => void)>;

export type ExtensionModule = {
  default: ExtensionActivate;
};

export type LoadedExtension = {
  manifest: ExtensionManifest;
  dispose?: () => void;
};

export type ExtensionLoadError = {
  manifest: ExtensionManifest;
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
