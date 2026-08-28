import type { PageId } from "../types/commandPalette.ts";

export type PageDefinition = {
  title: string;
  placeholder: string;
  /**
   * If true, this page's contents must NOT be revealed at the root via
   * fuzzy search. The user must explicitly enter the sub-menu to find
   * the entries — at scale (dozens of workspaces / agents) the root list
   * gets too cluttered if we surface them indiscriminately.
   */
  hideFromRootSearch?: boolean;
};

/** True iff the string is a registered PageId. Used to validate boundary inputs. */
export const isValidPageId = (id: string): id is PageId => Object.prototype.hasOwnProperty.call(PAGE_DEFINITIONS, id);

export const PAGE_DEFINITIONS: Record<PageId, PageDefinition> = {
  "theme.appearance": {
    title: "Switch theme",
    placeholder: "Pick an appearance...",
  },
  "settings.section": {
    title: "Go to settings",
    placeholder: "Jump to a settings section...",
  },
  "workspaces.switch": {
    title: "Go to workspace",
    placeholder: "Find a workspace...",
    hideFromRootSearch: true,
  },
  "agents.switch": {
    title: "Go to agent",
    placeholder: "Find an agent in this workspace...",
    hideFromRootSearch: true,
  },
  "workspace.actions": {
    title: "Workspace actions",
    placeholder: "Pick an action...",
  },
  "workspace.open_in": {
    title: "Open in...",
    placeholder: "Pick an application...",
  },
  "agent.actions": {
    title: "Agent actions",
    placeholder: "Pick an action...",
  },
  "view.layout": {
    title: "Toggle sections",
    placeholder: "Pick a section to toggle...",
  },
  "view.panels": {
    title: "Toggle panel visibility",
    placeholder: "Pick a panel to toggle...",
  },
  "addpanel.location": {
    title: "Add panel",
    placeholder: "Pick a section...",
  },
  "addpanel.panels": {
    title: "Add panel",
    placeholder: "Pick a panel...",
    // The panel list depends on the chosen location, so it must not be revealed
    // at the root via fuzzy search — the user picks a location first.
    hideFromRootSearch: true,
  },
};

/**
 * Push a sub-page onto the stack. Validates the id against PAGE_DEFINITIONS;
 * unknown ids are logged and ignored so a stray push doesn't render an
 * empty heading. The TypeScript signature already requires a PageId, so
 * this is defense-in-depth for callers who launder strings (e.g. URL
 * params, telemetry replay, future dynamic page sources).
 */
export const pushPageStack = (prev: ReadonlyArray<PageId>, pageId: PageId): Array<PageId> => {
  if (!isValidPageId(pageId)) {
    console.error(`[command-palette] pushPageStack: unknown page id "${pageId}" — ignored`);
    return [...prev];
  }
  return [...prev, pageId];
};

export const popPageStack = (prev: ReadonlyArray<PageId>): Array<PageId> => {
  if (prev.length === 0) return [];
  return prev.slice(0, -1);
};
