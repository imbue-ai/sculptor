import type { KeybindingId } from "~/common/keybindings/types.ts";

import type { CodingAgentTaskView, ExternalApp, Workspace } from "../../../api";
import type { CommandIcon } from "../types.ts";

/** Convenience alias — agents are surfaced as `CodingAgentTaskView` rows. */
export type Agent = CodingAgentTaskView;

/**
 * Action descriptor — pure data describing one row in a context menu and
 * (transitively) one command in the palette's per-entity sub-page. The
 * single source of truth for "the things you can do to this entity."
 *
 * Adding a new entry here means it shows up in the right-click menu AND
 * in Cmd+K → Workspace/Agent actions… → <entity> automatically.
 *
 * Icons reuse the palette's `CommandIcon` shape so lucide-react components
 * fit without a separate adapter.
 */
type ActionIcon = CommandIcon;

export type ContextActionShared = {
  /** Stable id for telemetry / data-testid / palette command id. */
  id: string;
  /** Visible label. */
  title: string;
  icon?: ActionIcon;
  /** Visual treatment hint. Maps to red/danger color in both consumers. */
  destructive?: boolean;
  /** Render a separator above this row in the right-click menu. */
  separatorBefore?: boolean;
  /**
   * Optional data-testid to apply to the rendered row in the right-click
   * menu. Existing integration tests target these ids; preserving them
   * means tests don't have to move when we route through the registry.
   */
  testId?: string;
  /**
   * Subtitle shown in the command palette only (right-click menus don't
   * have room). Optional by design — most actions are self-evident.
   */
  paletteSubtitle?: string;
  /**
   * Sub-page sort order in the command palette. Lower numbers come first.
   * The right-click menu always uses the descriptor array order; this
   * field only affects the palette's sub-page where extra rows (e.g.
   * "Open in...") interleave with descriptor rows.
   */
  paletteOrder?: number;
  /**
   * Extra fuzzy-search tokens to attach to the palette row, beyond the
   * action id and the entity name (which the dynamic provider always
   * adds). Use for synonyms / aliases — e.g. "git", "save" on commit.
   */
  paletteKeywords?: ReadonlyArray<string>;
  /**
   * Keybinding registry id whose binding should render alongside the
   * palette row. Surfaces the close-workspace shortcut on the close row,
   * for example.
   */
  paletteShortcut?: KeybindingId;
  /**
   * Title-suffix policy in the palette. When "name", the dynamic provider
   * appends `: <entity name>` to the displayed title — used by Rename and
   * Delete so the row reads as a clear targeted action. Default is "none".
   */
  paletteTitleSuffix?: "name" | "none";
};

export type WorkspaceAction = ContextActionShared & {
  /**
   * Hide the action for this workspace. Returning false omits the row in
   * BOTH the right-click menu and the palette. Used e.g. for "Close
   * others" with only one workspace open — the row would never apply,
   * so it should disappear entirely.
   */
  visible?: (workspace: Workspace) => boolean;
  /**
   * Show the action as greyed-out and non-selectable. Use for capabilities
   * the user should still see exist but that don't apply right now (e.g.
   * "Open pull request" with no PR yet). The row stays put so its position
   * is predictable across renders.
   */
  disabled?: (workspace: Workspace) => boolean;
  /**
   * Reason a disabled row is greyed-out — e.g. "No uncommitted changes",
   * "An open merge request already exists". Surfaced inline as the
   * palette row's subtitle when the row is disabled (so the user sees
   * the explanation without hovering); the right-click menu has no
   * tooltip slot, so this is palette-only.
   */
  disabledReason?: (workspace: Workspace) => string;
  /**
   * Render-time title override. Used when the label depends on workspace
   * state — e.g. "Create pull request" vs "Create merge request" based on
   * the git provider. `title` remains the stable identifier for testing;
   * `getTitle` only affects display.
   */
  getTitle?: (workspace: Workspace) => string;
  /**
   * Render-time subtitle override. Mirrors `getTitle` for the subtitle
   * slot — used when the line beneath the title depends on workspace
   * state (e.g. PR/MR verb flips by git provider). Static
   * `paletteSubtitle` remains the fallback / right-click-menu-side text.
   */
  getPaletteSubtitle?: (workspace: Workspace) => string;
  /**
   * Render-time fuzzy-search keyword override. Mirrors `getTitle` for
   * the keyword slot — used when the synonym set depends on workspace
   * state (e.g. drop "merge"/"mr" on GitHub repos so typing "merge"
   * doesn't surface "Create pull request"). Static `paletteKeywords`
   * remains the fallback.
   */
  getPaletteKeywords?: (workspace: Workspace) => ReadonlyArray<string>;
  perform: (workspace: Workspace) => void | Promise<void>;
};

export type AgentAction = ContextActionShared & {
  visible?: (agent: Agent) => boolean;
  disabled?: (agent: Agent) => boolean;
  disabledReason?: (agent: Agent) => string;
  getTitle?: (agent: Agent) => string;
  getPaletteSubtitle?: (agent: Agent) => string;
  getPaletteKeywords?: (agent: Agent) => ReadonlyArray<string>;
  perform: (agent: Agent) => void | Promise<void>;
};

/**
 * Runtime services workspace actions need. Implementations differ between
 * the right-click menu (which has access to local handlers) and the
 * command palette (which works through atoms), but the shape is the same.
 */
export type WorkspaceActionRuntime = {
  beginRename: (workspace: Workspace) => void;
  closeWorkspace: (workspace: Workspace) => void;
  closeOtherWorkspaces: (workspace: Workspace) => void;
  closeAllWorkspaces: () => void;
  beginDelete: (workspace: Workspace) => void;
  /** True when there is more than one workspace tab open. */
  canCloseOthers: () => boolean;

  /** Send the user's commit prompt to chat for the active agent. */
  commitChanges: (workspace: Workspace) => void;
  /** Send the PR-creation prompt to chat (with target branch hint). */
  createMergeRequest: (workspace: Workspace) => void;
  /** Open the existing PR/MR's web URL in a new tab. */
  openMergeRequest: (workspace: Workspace) => void;
  /** Reveal the workspace's repo path in the chosen external app. */
  openInApp: (workspace: Workspace, app: ExternalApp) => void;

  /** True when the workspace has uncommitted changes (for "Commit" enable). */
  hasUncommittedChanges: (workspace: Workspace) => boolean;
  /** True when there's an open PR/MR with a web URL ("Open" enable). */
  hasOpenPr: (workspace: Workspace) => boolean;
  /** True when no open PR/MR exists yet ("Create" enable). */
  canCreatePr: (workspace: Workspace) => boolean;
  /** "merge request" for GitLab, "pull request" otherwise. Drives labels. */
  prTerm: (workspace: Workspace) => "merge request" | "pull request";
  /** Backend exposes the open-in-app endpoint (false on remote backends). */
  canOpenInOS: () => boolean;
  /** True when the UI runs on macOS (Open-in is mac-only for now). */
  isMacUi: () => boolean;
};

export type AgentActionRuntime = {
  beginRename: (agent: Agent) => void;
  markUnread: (agent: Agent) => void;
  beginDelete: (agent: Agent) => void;
};
