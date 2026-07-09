// GENERATED FILE - do not edit. Regenerate with: just generate-extension-sdk-dts
// The public contract of "@sculptor/extension-sdk" (host SDK major 1), rolled up
// from sculptor/frontend/src/extensions/sdk/ in the Sculptor repo.
import { LucideIcon } from 'lucide-react';
import { ComponentType, ReactElement, ReactNode } from 'react';

export type SectionId = "left" | "center" | "right" | "bottom";
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
	icon?: ComponentType<{
		size?: number | string;
	}>;
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
/**
 * Imperative host actions extensions can call. Unlike the hooks in `hooks.ts`,
 * these are plain functions, callable from event handlers or anywhere outside
 * a React render. The generated SDK runtime stub (served at
 * `/extension-runtime/sculptor-extension-sdk.js`) re-exports them from the
 * `window.__SCULPTOR_HOST__.sdk` object the host populates at boot.
 */
/**
 * Open a URL in the user's browser. In the web build this is a new tab; in the
 * Electron desktop app a `_blank` target is routed to `shell.openExternal` by
 * the main process, so the link opens in the system browser rather than inside
 * the app window.
 *
 * Extensions should use this instead of calling `window.open` directly: it is the
 * single host-blessed seam for outbound links, so behaviour stays consistent
 * and can be upgraded (e.g. to a dedicated Electron bridge) in one place.
 * `noopener,noreferrer` prevents the opened page from reaching back through
 * `window.opener`.
 *
 * Only `http(s)` URLs are opened. A URL that doesn't parse or uses another
 * scheme (`javascript:`, `data:`, …) is refused — this is the blessed seam, so
 * it stays safe even when the URL comes from external data (e.g. a Linear issue
 * or attachment URL), mirroring the host's safe-URL policy for rendered links.
 */
export declare const openExternal: (url: string) => void;
export type PanelHeaderProps = {
	title: string;
	/** Optional content rendered to the right of the title (e.g. icon buttons). */
	actions?: ReactNode;
	/** Optional content rendered next to the title text (e.g. status indicators). */
	afterTitle?: ReactNode;
};
export declare const PanelHeader: ({ title, actions, afterTitle }: PanelHeaderProps) => ReactElement;
declare const MarkdownBlock: import("react").MemoExoticComponent<(props: {
	content: string;
}) => ReactElement>;
/**
 * CodingAgentTaskView
 *
 * messages are the primary way of interacting with an agent.
 *
 * this class is simply a way of deriving the current state of the agent based on the message log.
 *
 * because agents are run as idempotent tasks, consumers MUST be able to handle duplicate messages.
 * this is particularly tricky because you cannot deduplicate on message_id here --
 * the ids may be different between two different runs
 * (and that cannot be fixed because different things may have happened)
 * consumers *may* process messages in a "task aware" manner, eg,
 * by paying attention to the task start and stop messages in order to properly discard outdated messages.
 */
export type CodingAgentTaskView = {
	/**
	 * Objecttype
	 */
	objectType?: string;
	/**
	 * Id
	 */
	readonly id: string;
	/**
	 * Projectid
	 */
	readonly projectId: string;
	/**
	 * Createdat
	 */
	readonly createdAt: string;
	readonly taskStatus: TaskState;
	/**
	 * Isautocompacting
	 *
	 * True when the agent is auto-compacting context (detected via plugin hook).
	 */
	readonly isAutoCompacting: boolean;
	/**
	 * Artifactnames
	 */
	readonly artifactNames: Array<string>;
	/**
	 * Updatedat
	 */
	readonly updatedAt: string;
	/**
	 * Initialprompt
	 */
	readonly initialPrompt: string;
	/**
	 * Titleorsomethinglikeit
	 */
	readonly titleOrSomethingLikeIt: string;
	readonly interface: TaskInterface;
	readonly model: LlmModel | null;
	readonly harnessCapabilities: HarnessCapabilities;
	/**
	 * Availablemodels
	 *
	 * The switcher's catalog as the frontend gates on it: NOT_FETCHED_YET
	 * until the start-time probe lands, then the fetched list (empty = the
	 * harness sources none and the frontend falls back to its built-in list, or
	 * pi is authenticated with no providers and shows the empty state). Runtime
	 * callers that only offer models use `get_available_models`, which coalesces
	 * the sentinel to []; the switcher needs the distinction so it can show a
	 * loading state instead of flashing the empty state while the catalog loads.
	 */
	readonly availableModels: Array<ModelOption> | ModelCatalogState;
	/**
	 * Selectedmodelid
	 *
	 * The model_id the switcher should show as selected, or None when the
	 * harness tracks no per-task selection.
	 */
	readonly selectedModelId: string | null;
	/**
	 * Sourcesbackendmodels
	 *
	 * Whether the harness sources its switcher catalog from a backend (pi);
	 * when False the frontend uses its built-in Claude list.
	 */
	readonly sourcesBackendModels: boolean;
	/**
	 * Configurationsettingssection
	 *
	 * The Settings section the composer's "Go to harness configuration" CTA opens
	 * when this harness has no usable model — a frontend `SettingsSection` id, owned by
	 * the harness (pi -> "PI", otherwise "DEPENDENCIES") so the composer never branches
	 * on harness identity.
	 */
	readonly configurationSettingsSection: string;
	/**
	 * Acceptsautomatedprompts
	 */
	readonly acceptsAutomatedPrompts: boolean;
	/**
	 * Issmoothstreamingsupported
	 */
	readonly isSmoothStreamingSupported: boolean;
	/**
	 * Isdeleted
	 */
	readonly isDeleted: boolean;
	/**
	 * Lastreadat
	 */
	readonly lastReadAt: string | null;
	/**
	 * Title
	 */
	readonly title: string | null;
	readonly status: TaskStatus;
	/**
	 * Goal
	 */
	readonly goal: string;
	/**
	 * Workspaceid
	 *
	 * The workspace ID associated with this task.
	 *
	 * In Phase 1, workspaces are created implicitly 1:1 with tasks.
	 */
	readonly workspaceId: string | null;
	readonly workspacePeekStatus: WorkspacePeekAgentStatus;
	/**
	 * Currentactivity
	 */
	readonly currentActivity: string | null;
	/**
	 * Lastactivity
	 */
	readonly lastActivity: string | null;
	/**
	 * Taskcompleted
	 */
	readonly taskCompleted: number;
	/**
	 * Tasktotal
	 */
	readonly taskTotal: number;
	/**
	 * Currenttasksubject
	 */
	readonly currentTaskSubject: string | null;
	/**
	 * Waitingdetail
	 */
	readonly waitingDetail: string | null;
	/**
	 * Errordetail
	 */
	readonly errorDetail: string | null;
	[key: string]: unknown;
};
/**
 * HarnessCapabilities
 *
 * Coarse-grained, bool-typed capabilities a harness advertises.
 *
 * Read by backend feature gates and by the frontend (via the generated
 * TypeScript twin). Populated truthfully by each harness through
 * `Harness.capabilities()`. PHASE_5_NORTH_STAR §2 names this the
 * bool-field shape of the capability region; gated-method capabilities
 * (e.g. `Harness.is_ask_user_question_tool`) coexist on the `Harness`
 * interface for protocol-level questions no bool can express.
 *
 * Fields have **no Python defaults** — every constructor must list every
 * field. When a new capability lands, pydantic validation forces an edit
 * at every constructor site (the base `Harness.capabilities()` body,
 * every concrete harness's override, every hand-built test fixture), so
 * the harness↔capability matrix is grep-complete: `grep <field>` finds
 * every harness's stance.
 *
 * `supports_context_reset` and `supports_compaction` are distinct: context
 * reset is the `/clear` path that discards the session; compaction summarizes
 * the session in place at a threshold. They gate different surfaces.
 *
 * `supports_chat_interface` is the coarse main-panel switch (chat interface
 * vs terminal panel), distinct from the per-affordance bools below it.
 */
export type HarnessCapabilities = {
	/**
	 * Supportschatinterface
	 */
	supportsChatInterface: boolean;
	/**
	 * Supportsinteractivebackchannel
	 */
	supportsInteractiveBackchannel: boolean;
	/**
	 * Supportsskills
	 */
	supportsSkills: boolean;
	/**
	 * Supportssubagents
	 */
	supportsSubAgents: boolean;
	/**
	 * Supportsimageinput
	 */
	supportsImageInput: boolean;
	/**
	 * Supportsfastmode
	 */
	supportsFastMode: boolean;
	/**
	 * Supportscontextreset
	 */
	supportsContextReset: boolean;
	/**
	 * Supportscompaction
	 */
	supportsCompaction: boolean;
	/**
	 * Supportsbackgroundtasks
	 */
	supportsBackgroundTasks: boolean;
	/**
	 * Supportssessionresume
	 */
	supportsSessionResume: boolean;
	/**
	 * Supportstooluserendering
	 */
	supportsToolUseRendering: boolean;
	/**
	 * Supportsfileattachments
	 */
	supportsFileAttachments: boolean;
	/**
	 * Supportsinterruption
	 */
	supportsInterruption: boolean;
	/**
	 * Supportsfilereferences
	 */
	supportsFileReferences: boolean;
	/**
	 * Supportsmodelselection
	 */
	supportsModelSelection: boolean;
	[key: string]: unknown;
};
declare const LlmModel: {
	readonly CLAUDE_4_OPUS: "CLAUDE-4-OPUS";
	readonly CLAUDE_4_OPUS_200K: "CLAUDE-4-OPUS-200K";
	readonly CLAUDE_4_7_OPUS: "CLAUDE-4-7-OPUS";
	readonly CLAUDE_4_7_OPUS_200K: "CLAUDE-4-7-OPUS-200K";
	readonly CLAUDE_4_6_OPUS: "CLAUDE-4-6-OPUS";
	readonly CLAUDE_4_6_OPUS_200K: "CLAUDE-4-6-OPUS-200K";
	readonly CLAUDE_4_SONNET: "CLAUDE-4-SONNET";
	readonly CLAUDE_4_SONNET_200K: "CLAUDE-4-SONNET-200K";
	readonly CLAUDE_4_HAIKU: "CLAUDE-4-HAIKU";
	readonly CLAUDE_FABLE_5: "CLAUDE-FABLE-5";
	readonly FAKE_CLAUDE: "FAKE_CLAUDE";
	readonly FAKE_CLAUDE_2: "FAKE_CLAUDE_2";
};
/**
 * LLMModel
 */
export type LlmModel = typeof LlmModel[keyof typeof LlmModel];
declare const ModelCatalogState: {
	readonly NOT_FETCHED_YET: "not_fetched_yet";
};
/**
 * ModelCatalogState
 *
 * The catalog states a plain `list[ModelOption]` cannot express.
 *
 * `NOT_FETCHED_YET` is the birth state of a backend (pi) catalog on task state,
 * before the start-time probe runs — distinct from a fetched-but-empty `[]`
 * (authenticated, but no providers), which is what drives the empty state. Keeping
 * the two apart is what stops the switcher flashing that empty state during startup. A
 * StrEnum member is a value-less, interned singleton that survives serialization
 * by identity, so read sites use `is` rather than overloading `None`.
 */
export type ModelCatalogState = typeof ModelCatalogState[keyof typeof ModelCatalogState];
/**
 * ModelOption
 *
 * One model a harness offers in its switcher.
 *
 * `provider` and `model_id` identify the model on the harness's own terms
 * (pi sends them back as a `set_model` selection; for the Claude harness
 * `model_id` is the `LLMModel` value). `display_name` is the selector label.
 */
export type ModelOption = {
	/**
	 * Provider
	 */
	provider: string;
	/**
	 * Modelid
	 */
	modelId: string;
	/**
	 * Displayname
	 */
	displayName: string;
	[key: string]: unknown;
};
declare const TaskInterface: {
	readonly TERMINAL: "TERMINAL";
	readonly API: "API";
};
/**
 * TaskInterface
 */
export type TaskInterface = typeof TaskInterface[keyof typeof TaskInterface];
declare const TaskState: {
	readonly QUEUED: "QUEUED";
	readonly RUNNING: "RUNNING";
	readonly FAILED: "FAILED";
	readonly CANCELLED: "CANCELLED";
	readonly DELETED: "DELETED";
	readonly SUCCEEDED: "SUCCEEDED";
};
/**
 * TaskState
 *
 * The possible states of a server task.
 */
export type TaskState = typeof TaskState[keyof typeof TaskState];
declare const TaskStatus: {
	readonly BUILDING: "BUILDING";
	readonly RUNNING: "RUNNING";
	readonly READY: "READY";
	readonly WAITING: "WAITING";
	readonly ERROR: "ERROR";
	readonly REQUEST_ERROR: "REQUEST_ERROR";
};
/**
 * TaskStatus
 */
export type TaskStatus = typeof TaskStatus[keyof typeof TaskStatus];
declare const WorkspacePeekAgentStatus: {
	readonly WORKING: "WORKING";
	readonly WAITING: "WAITING";
	readonly ERROR: "ERROR";
	readonly COMPLETED: "COMPLETED";
	readonly IDLE: "IDLE";
};
/**
 * WorkspacePeekAgentStatus
 */
export type WorkspacePeekAgentStatus = typeof WorkspacePeekAgentStatus[keyof typeof WorkspacePeekAgentStatus];
/**
 * A curated, extension-facing view of a single workspace: identity, label, live git
 * branch, and code-host link. Deliberately a subset — not the host's full
 * `Workspace` model — so the extension contract doesn't couple to backend
 * internals. The element type of `useWorkspaces` and the return of
 * `useCurrentWorkspace`, so an extension reads the same shape whether it looks at
 * one workspace or all of them.
 */
export type WorkspaceView = {
	id: string;
	description: string;
	/** Live current branch, or `null` until the backend has reported it. */
	branch: string | null;
	targetBranch: string | null;
	/**
	 * Web URL of the workspace's pull/merge request, or `null` when there is none
	 * (or the backend hasn't reported PR status yet). The authoritative link
	 * between a Sculptor workspace and an external code host — useful when the
	 * branch name alone can't be resolved, since Sculptor-generated branch names
	 * carry no issue identifier and no host-side VCS link.
	 */
	pullRequestUrl: string | null;
};
/** @deprecated Use {@link WorkspaceView}; kept as an alias for the prior name. */
export type CurrentWorkspace = WorkspaceView;
/**
 * Every non-deleted workspace known to the host as a curated {@link
 * WorkspaceView} (including live branch and PR URL), or `undefined` until the
 * first batch has loaded. App-global: it needs no workspace context, so it
 * works in an overlay or home view as well as a panel.
 */
export declare const useWorkspaces: () => ReadonlyArray<WorkspaceView> | undefined;
/**
 * The workspace the user is currently in — the panel's workspace when mounted
 * in a panel, otherwise the current route — or `null` when there is none (e.g.
 * an overlay on the home or settings screen). Named for its nullability and to
 * avoid shadowing the host's by-id `useWorkspace`, which has different
 * semantics.
 *
 * Pass a `selector` to subscribe to one field and re-render only when that
 * field changes (backed by jotai's `selectAtom`):
 *
 *     const branch = useCurrentWorkspace((w) => w?.branch ?? null);
 *
 * The selector should be pure over the workspace (no external closure state):
 * its identity may change between renders, but its logic must not.
 */
export declare function useCurrentWorkspace<T = WorkspaceView | null>(selector?: (workspace: WorkspaceView | null) => T, equalityFn?: (a: T, b: T) => boolean): T;
/**
 * Returns a function that navigates to a workspace by id — the host's own
 * workspace-open behavior: it opens (or converts the home tab into) the
 * workspace's tab and jumps to its most-recently-used agent. The blessed seam
 * for an extension to send the user into a workspace (e.g. a home view opening the
 * workspace a ticket is being worked in), so the navigation stays consistent
 * with clicking a workspace in the host's own lists.
 */
export declare const useNavigateToWorkspace: () => ((workspaceId: string) => void);
/** Seeds and callback for {@link useOpenNewWorkspaceModal}. */
export type NewWorkspaceModalOptions = {
	/** Pre-fills the workspace title field. */
	initialTitle?: string;
	/** Pre-fills the first-agent prompt textarea. */
	initialPrompt?: string;
	/**
	 * Pre-fills the new-branch-name field; when omitted the host derives the
	 * branch from the title as usual. The host validates the name, and the user
	 * can edit it or re-roll back to the derived one.
	 */
	initialBranchName?: string;
	/**
	 * Called with the new workspace's id per successful create — keep-open mode
	 * lets the user create several workspaces from one open dialog, so this can
	 * fire more than once. Between such creates the form re-seeds its fields
	 * from the `initial*` options, so the dialog stays visibly about this open
	 * request and every report belongs to it.
	 */
	onCreated?: (workspaceId: string) => void;
};
/**
 * Returns a stable function that opens the host's own new-workspace dialog —
 * the same one behind Cmd/Meta+T — optionally pre-filled with a title, prompt,
 * and branch name. The user remains in control: they can edit every field or cancel
 * without creating anything. `onCreated` reports the created workspace's id
 * (e.g. to record an extension-side association, or to follow up with
 * `useNavigateToWorkspace`).
 */
export declare const useOpenNewWorkspaceModal: () => ((options?: NewWorkspaceModalOptions) => void);
/**
 * A persisted string setting scoped to the calling extension. Backed by
 * localStorage under a `sculptor-extension:<id>:<key>` namespace and shared
 * reactively across the extension's panel and its settings component.
 */
export declare const useExtensionSetting: (key: string) => [
	string,
	(value: string) => void
];
/**
 * Read several of the calling extension's persisted settings at once, reactively —
 * the multi-key companion to {@link useExtensionSetting} for when the set of keys
 * is dynamic, so you can't call `useExtensionSetting` once per key (e.g. one
 * per-workspace key, with the workspace list coming from `useWorkspaces`).
 * Returns a map from each requested key to its current value (the empty string
 * for an unset key) and re-renders when any of those keys changes — including a
 * write from another surface of the extension, since both share the same per-key
 * atoms.
 */
export declare const useExtensionSettings: (keys: ReadonlyArray<string>) => ReadonlyMap<string, string>;
/**
 * Returns a stable function that writes one of the calling extension's persisted
 * settings — the imperative companion to {@link useExtensionSetting} for keys only
 * known at event time (e.g. a per-workspace key for a workspace picked in a
 * menu), where the hook-per-key form can't be called. Writes land in the same
 * per-key atoms as the reading hooks, so `useExtensionSetting` and
 * `useExtensionSettings` see them reactively.
 */
export declare const useSetExtensionSetting: () => ((key: string, value: string) => void);
/** @deprecated Use {@link useExtensionSetting}. Kept for extensions compiled against the pre-rename SDK. */
export declare const usePluginSetting: (key: string) => [
	string,
	(value: string) => void
];
/** @deprecated Use {@link useExtensionSettings}. Kept for extensions compiled against the pre-rename SDK. */
export declare const usePluginSettings: (keys: ReadonlyArray<string>) => ReadonlyMap<string, string>;
/** @deprecated Use {@link useSetExtensionSetting}. Kept for extensions compiled against the pre-rename SDK. */
export declare const useSetPluginSetting: () => ((key: string, value: string) => void);
/**
 * All non-deleted tasks for the workspace the extension is mounted in. Returns
 * `undefined` until the host's task stream has produced its first batch.
 */
export declare const useWorkspaceTasks: () => ReadonlyArray<CodingAgentTaskView> | undefined;
/**
 * @deprecated Use {@link ExtensionPanelDefinition}. Kept as an alias so existing
 * extensions that import the old name still type-check; the section shell ignores
 * the legacy zone fields.
 */
export type PanelDefinition = ExtensionPanelDefinition;
/** @deprecated Use {@link ExtensionManifest}. */
export type PluginManifest = ExtensionManifest;
/** @deprecated Use {@link ExtensionHostApi}. */
export type PluginHostApi = ExtensionHostApi;
/** @deprecated Use {@link ExtensionPanelDefinition}. */
export type PluginPanelDefinition = ExtensionPanelDefinition;

export {
	MarkdownBlock as Markdown,
};

export {};
