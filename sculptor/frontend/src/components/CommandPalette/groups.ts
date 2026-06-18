import type { CommandGroup, CommandGroupId } from "./types.ts";

/**
 * Source of truth for command groups. Typed as `Record<CommandGroupId, CommandGroup>`
 * so that adding a new id to the `CommandGroupId` union in `types.ts` produces a
 * compile-time error here until a matching entry is supplied. This mirrors the
 * exhaustiveness contract used by `PAGE_DEFINITIONS` in `pages.ts`.
 */
const COMMAND_GROUPS_BY_ID: Record<CommandGroupId, CommandGroup> = {
  // Workspaces and the New Workspace entry are the most-used Cmd+K
  // affordances, so they lead everything else. Navigation falls
  // right after them. Chat sits above View because the user reaches for
  // chat actions much more often than panel toggles.
  workspaces: { id: "workspaces", heading: "Workspaces", order: 10 },
  navigation: { id: "navigation", heading: "Navigation", order: 20 },
  // Combined Theme + Layout: appearance toggles cluster with panel /
  // zone toggles since users think of them as one "look & feel"
  // surface. Theme rows lead within the group (low explicit `order`),
  // panel/layout rows follow. Sits above Chat — adjusting the
  // workspace's look is more universally invoked than chat affordances.
  view: { id: "view", heading: "Theme & Layout", order: 30 },
  chat: { id: "chat", heading: "Chat", order: 40 },
  terminal: { id: "terminal", heading: "Terminal", order: 50 },
  help: { id: "help", heading: "Help", order: 60 },
};

/**
 * Look up the sort order for a group id. For known `CommandGroupId`s this
 * always returns a real value because `COMMAND_GROUPS_BY_ID` is exhaustively
 * typed. The `999` fallback only fires for legacy callers that pass an
 * arbitrary string (e.g. ids that have been removed from the union).
 */
export const groupOrder = (id: CommandGroupId | string): number =>
  (COMMAND_GROUPS_BY_ID as Record<string, CommandGroup | undefined>)[id]?.order ?? 999;

/**
 * Look up the display heading for a group id. Falls back to the raw id for
 * unknown strings.
 */
export const groupHeading = (id: CommandGroupId | string): string =>
  (COMMAND_GROUPS_BY_ID as Record<string, CommandGroup | undefined>)[id]?.heading ?? id;
