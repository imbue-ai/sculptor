import type { ComponentType } from "react";

import type { KeybindingId } from "~/common/keybindings/types.ts";

export type CommandId = string;

export type CommandGroupId = "navigation" | "workspaces" | "view" | "chat" | "terminal" | "help";

export type PageId =
  | "theme.appearance"
  | "settings.section"
  | "workspaces.switch"
  /** Agents in the current workspace. */
  | "agents.switch"
  /** Action list for the current workspace (set via `workspaceActionsTargetAtom`). */
  | "workspace.actions"
  /** External-app picker for the current workspace (Finder, VS Code, ...). */
  | "workspace.open_in"
  /** Action list for the current agent (set via `agentActionsTargetAtom`). */
  | "agent.actions"
  /** Layout toggles: Left/Right/Bottom panel zones + Focus/Zen modes. */
  | "view.layout"
  /** Individual panel toggles (Files, Actions, Terminal, Notes, …). */
  | "view.panels";

/**
 * Icon component reference. Wide on purpose so `lucide-react` icons (which
 * are `ForwardRefExoticComponent`s) and any other compatible icon
 * components both fit. Render site only passes `size`.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export type CommandIcon = ComponentType<any>;

export type PaletteRoute = {
  isHome: boolean;
  isWorkspace: boolean;
  isSettings: boolean;
  isAgent: boolean;
};

export type PaletteContext = {
  route: PaletteRoute;
  activeWorkspaceId: string | null;
  activeAgentId: string | null;
  hasChatPanel: boolean;
  hasTerminalPanel: boolean;
  isZenMode: boolean;
  /** The current sub-page id, or null for the root page. */
  page: PageId | null;
};

export type CommandRunArgs = {
  ctx: PaletteContext;
  /** Keep the palette open after run. The user can request this with Cmd+Enter. */
  keepOpen: boolean;
  /** Push a sub-page (only valid for commands that declare a `pageId`). */
  pushPage: (pageId: PageId) => void;
};

/**
 * Casing convention for user-facing strings on `Command` and
 * `PageDefinition`:
 *
 *   - **Sentence case** for `title`, `subtitle`, `placeholder`, and
 *     `disabledReason`. First word capitalized; subsequent words
 *     lowercase unless they are proper nouns (e.g. "Finder", "VS Code",
 *     "PR", "MR") or single-word value labels that read as labels in
 *     their own right (e.g. "Light", "Dark", "System" appearance modes).
 *   - **Title Case** is reserved for group `heading`s in `groups.ts`,
 *     which are categorical labels rather than commands.
 *
 * Examples:
 *   ✓ "Open settings", "Toggle bottom panel", "Show keyboard shortcuts"
 *   ✓ "Open in Finder", "Open in VS Code"  (proper nouns kept)
 *   ✗ "Open Settings", "Toggle Bottom Panel"
 *
 * Modern editor / launcher UIs (VS Code, Linear, Raycast) follow this
 * pattern; we match it for consistency with the rest of the product.
 */
export type Command = {
  id: CommandId;
  title: string;
  subtitle?: string;
  /** Extra tokens that should match in fuzzy search (synonyms, aliases). */
  keywords?: Array<string>;
  group: CommandGroupId;
  icon?: CommandIcon;
  /** Show the binding for an existing keybinding registry id alongside this command. */
  shortcut?: KeybindingId;
  /**
   * Compute the title at render time. Useful for toggles whose label
   * depends on current state (e.g. "Enable X" vs "Disable X"). When
   * provided, takes precedence over `title` for display only — `title`
   * is still used for fuzzy-search ranking, so keep it stable.
   */
  getTitle?: (ctx: PaletteContext) => string;
  /**
   * Compute the subtitle at render time. Same display-only contract as
   * `getTitle` — `subtitle` (if present) is used as the stable mental
   * model; this method overrides it for display.
   */
  getSubtitle?: (ctx: PaletteContext) => string;
  /**
   * Compute the icon at render time. Same display-only contract as
   * `getTitle`. Use for state-dependent icon swaps (e.g. ToggleLeft vs
   * ToggleRight).
   */
  getIcon?: (ctx: PaletteContext) => CommandIcon;
  /**
   * Predicate that decides whether the command is visible in the current context.
   * If omitted, the command is always visible. Errors are caught and the command is
   * hidden (logged once per session).
   */
  when?: (ctx: PaletteContext) => boolean;
  /**
   * The function executed when the user selects this command. May be async; the row
   * shows a spinner while the promise is pending. Errors surface as a Toast.
   */
  perform: (args: CommandRunArgs) => void | Promise<void>;
  /**
   * If true, the palette stays open after running this command. Useful for toggles
   * (e.g. flipping an experimental flag).
   */
  keepOpen?: boolean;
  /**
   * If set, selecting this command pushes the named sub-page instead of running.
   * `perform` is still invoked (for telemetry / setup) but its return value is ignored.
   */
  pageId?: PageId;
  /**
   * Render a trailing chevron on the row even when the command does not
   * push a sub-page. Use for entries that transition into a new surface
   * the user backs out of (e.g. "New workspace" opens a modal) — the
   * chevron signals the row is a doorway, not an in-place action.
   */
  showChevron?: boolean;
  /**
   * Restrict visibility to one or more sub-pages. Pass a single `PageId`
   * for a command that lives on exactly one page, or a `ReadonlyArray` of
   * `PageId`s to surface the same command on several pages without
   * duplicating its definition. Commands that omit `onPage` entirely are
   * root-page only.
   */
  onPage?: PageId | ReadonlyArray<PageId>;
  /**
   * Marks a command as a "primary" entry-point — typically a page-opener
   * like "Switch workspace…" or "Open Settings". Within a given match
   * tier the filter applies a small boost so primary commands rank above
   * same-tier siblings. Cannot promote across tiers.
   */
  primary?: boolean;
  /**
   * Explicit display order within a group. Lower numbers come first.
   * Used when alphabetical / primary sorting can't express the order
   * the team wants — e.g. "New Workspace, Open Workspace, Workspace
   * actions, Switch agent, Agent actions" doesn't follow N→O→S→W→A.
   * Sort precedence is: scope (root before page-scoped) → primary →
   * `order` (lower first) → alphabetical title.
   */
  order?: number;
  /**
   * If true, the command is rendered greyed-out and cannot be selected.
   * Use for entry points that should remain visible (so the user knows
   * the capability exists) but have nothing to do in the current
   * context — e.g. "Switch agent..." with fewer than two agents.
   */
  disabled?: boolean;
  /**
   * Optional explanation shown as a tooltip on hover when `disabled` is
   * true. Pair with every disabled state so the user knows WHY a row is
   * greyed-out (e.g. "No uncommitted changes" on a commit row, or
   * "An open pull request already exists" on Create PR). Omit when the
   * subtitle already conveys the reason.
   */
  disabledReason?: string;
  /**
   * Multiplicative score multiplier. Default 1 (no adjustment).
   *   - Values > 1 boost — e.g. dynamic panel toggles outrank same-tier
   *     Settings sub-page rows that share their name.
   *   - Values strictly between 0 and 1 demote — e.g. settings sub-page
   *     rows are pushed below any other matching row so that fuzzy
   *     searches surface action commands first.
   * Values ≤ 0 and exactly 1 are ignored. Use `when` to hide a row
   * entirely; this field only adjusts ranking among visible rows.
   */
  boost?: number;
};

export type CommandGroup = {
  id: CommandGroupId;
  heading: string;
  /** Smaller numbers sort earlier. */
  order: number;
};

export type DynamicProvider = {
  id: string;
  produce: (ctx: PaletteContext) => Array<Command>;
};

/**
 * Normalize `Command.onPage` into a single shape: an array of PageIds,
 * or null when the command lives at the root only. Centralizes the
 * branching that would otherwise leak into every consumer.
 */
export const pagesOf = (cmd: Command): ReadonlyArray<PageId> | null => {
  if (cmd.onPage == null) return null;
  return typeof cmd.onPage === "string" ? [cmd.onPage] : cmd.onPage;
};

/** True iff the command is scoped to one or more sub-pages (i.e. not root-only). */
export const isPageScoped = (cmd: Command): boolean => cmd.onPage != null;
