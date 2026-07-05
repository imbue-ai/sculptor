import { PluginKey } from "@tiptap/pm/state";
import type { SuggestionOptions } from "@tiptap/suggestion";
import { Bot, FolderGit2, Layers, type LucideIcon } from "lucide-react";
import type { MutableRefObject } from "react";

import type { CodingAgentTaskView, Project, Workspace } from "~/api";
import { formatRelativeTime } from "~/common/formatRelativeTime";
import { formatRepoUrl } from "~/common/formatRepoUrl";

import { EntityMentionList } from "./editor/EntityMentionList";
import { renderSuggestion, SuggestionItem } from "./editor/utils/suggestion";

export type EntityType = "repository" | "workspace" | "agent";

// Lucide-react icon used to mark each entity type in the picker, in chips, and
// in chip hover cards. Matches the `+` prefilter picker (MentionPickerList) so the
// visual language stays consistent across every surface where these types
// appear. Kept here next to TYPE_LABELS so a new entity type only needs one
// touch.
export const TYPE_ICONS: Record<EntityType, LucideIcon> = {
  repository: FolderGit2,
  workspace: Layers,
  agent: Bot,
};

export type EntityMentionItem = SuggestionItem & {
  entityType: EntityType;
  entityId: string;
  entityDisplayName: string;
  subtitle: string;
  // ID of the conceptual parent entity, used for hierarchical filtering.
  // Workspaces carry their projectId; agents carry their workspaceId; repos
  // have no parent. Lets the picker filter agents to a single workspace
  // when the user drills into a workspace row, without re-deriving the
  // parent link from atoms.
  parentId?: string;
};

// Non-selectable row rendered as a section title in the shared
// `SuggestionListContainer`. Arrow-key navigation skips these so Enter
// commits the next real item below the header.
type SectionHeaderItem = SuggestionItem & {
  isSectionHeader: true;
  isFirstInList?: boolean;
};

// Top-level "pick a type" row. Selectable via arrow-keys; Tab / Enter /
// click drills the picker into that type's entities. Filtering and
// drill-in state are owned by `EntityMentionList` — this row is just a
// tagged payload that the List's wrapped `command` handler intercepts.
export type TypeRowItem = SuggestionItem & {
  isTypeRow: true;
  entityType: EntityType;
  description: string;
};

export type EntityPickerRow = EntityMentionItem | SectionHeaderItem | TypeRowItem;

export type EntityDataRef = MutableRefObject<{
  repositories: ReadonlyArray<Project>;
  workspaces: ReadonlyArray<Workspace>;
  agents: ReadonlyArray<CodingAgentTaskView>;
}>;

// Type-row order for the top-level type picker. Agents are intentionally
// absent: the picker treats workspaces as the parent category for both,
// and a user drills into a specific workspace (Tab on the row) to reach
// its agents. Top-level fuzzy search across agents still works through the
// AGENTS section below — the type-row drill is just one of three ways in.
export const TYPE_ROW_ORDER: ReadonlyArray<EntityType> = ["repository", "workspace"];

export const TYPE_LABELS: Record<EntityType, string> = {
  repository: "Repositories",
  workspace: "Workspaces",
  agent: "Agents",
};

export const TYPE_DESCRIPTIONS: Record<EntityType, string> = {
  repository: "Git projects connected to Sculptor",
  workspace: "Task workspaces — drill in for their agents",
  agent: "Running or completed coding agents",
};

const makeEntityItem = (fields: {
  entityType: EntityType;
  entityId: string;
  entityDisplayName: string;
  subtitle: string;
  parentId?: string;
}): EntityMentionItem => ({
  ...new SuggestionItem(fields.entityId, fields.entityDisplayName),
  ...fields,
});

const makeTypeRow = (entityType: EntityType): TypeRowItem => ({
  ...new SuggestionItem(`__type-${entityType}`, TYPE_LABELS[entityType]),
  isTypeRow: true,
  entityType,
  description: TYPE_DESCRIPTIONS[entityType],
});

// Maximum number of characters of an agent's goal to show as its display name
// when the agent has no explicit title; longer goals are truncated to keep the
// picker row scannable.
const AGENT_GOAL_PREVIEW_LENGTH = 60;

const formatAgentCount = (count: number): string => {
  if (count === 0) return "no agents";
  if (count === 1) return "1 agent";
  return `${count} agents`;
};

const getAgentDisplayName = (task: CodingAgentTaskView): string =>
  task.title ?? (task.goal ? task.goal.slice(0, AGENT_GOAL_PREVIEW_LENGTH) : "Untitled");

export const createEntitySuggestion = (entityDataRef: EntityDataRef): Omit<SuggestionOptions, "editor"> => ({
  pluginKey: new PluginKey("entityMention"),
  char: "+",
  startOfLine: false,
  allowedPrefixes: null,

  allow: ({ state, range }): boolean => {
    const $from = state.doc.resolve(range.from);
    if ($from.parent.type.name === "codeBlock") {
      return false;
    }
    const codeMark = state.schema.marks.code;
    if (codeMark && state.doc.rangeHasMark(range.from, range.from + 1, codeMark)) {
      return false;
    }
    return true;
  },

  items: ({ query }): Array<EntityPickerRow> => {
    const { repositories, workspaces, agents } = entityDataRef.current;
    const lowerQuery = query.toLowerCase();

    const matchesQuery = (displayName: string, subtitle: string): boolean => {
      if (query === "") {
        return true;
      }
      return displayName.toLowerCase().includes(lowerQuery) || subtitle.toLowerCase().includes(lowerQuery);
    };

    // Map repositories. Subtitle is the trimmed git URL (e.g.
    // `imbue-ai/sculptor` rather than the full https URL) so the row stays
    // scannable; the raw URL is still used for the search match so a user
    // typing a fragment of the host or org name finds the project.
    const repoItems: Array<EntityMentionItem> = repositories
      .filter((project) => matchesQuery(project.name, project.userGitRepoUrl ?? ""))
      .map((project) =>
        makeEntityItem({
          entityType: "repository",
          entityId: project.objectId,
          entityDisplayName: project.name,
          subtitle: formatRepoUrl(project.userGitRepoUrl),
        }),
      );

    // Map workspaces — sort by createdAt descending. Subtitle leads with the
    // agent count (folder-style "size hint"), then the parent repo. Search
    // still matches against name + repo only so a query for "agent" doesn't
    // light up every workspace row.
    const workspaceItems: Array<EntityMentionItem> = [...workspaces]
      .sort((a, b) => (b.createdAt ?? "").localeCompare(a.createdAt ?? ""))
      .filter((workspace) => {
        const displayName = workspace.description ?? "Untitled";
        const parentProject = repositories.find((p) => p.objectId === workspace.projectId);
        return matchesQuery(displayName, parentProject?.name ?? "");
      })
      .map((workspace) => {
        const displayName = workspace.description ?? "Untitled";
        const parentProject = repositories.find((p) => p.objectId === workspace.projectId);
        const repoName = parentProject?.name ?? "";
        const agentCount = agents.filter((a) => a.workspaceId === workspace.objectId).length;
        const agentLabel = formatAgentCount(agentCount);
        const subtitle = repoName ? `${agentLabel} · ${repoName}` : agentLabel;
        return makeEntityItem({
          entityType: "workspace",
          entityId: workspace.objectId,
          entityDisplayName: displayName,
          subtitle,
          parentId: workspace.projectId,
        });
      });

    // Map agents — sort by createdAt descending. Subtitle is just the
    // relative time; the parent workspace is reachable via the workspace
    // drill-in chevron and the explicit AGENTS section listing, so
    // surfacing it on every row would be redundant noise.
    const agentItems: Array<EntityMentionItem> = [...agents]
      .sort((a, b) => b.createdAt.localeCompare(a.createdAt))
      .filter((task) => matchesQuery(getAgentDisplayName(task), ""))
      .map((task) =>
        makeEntityItem({
          entityType: "agent",
          entityId: task.id,
          entityDisplayName: getAgentDisplayName(task),
          subtitle: formatRelativeTime(task.createdAt),
          parentId: task.workspaceId ?? undefined,
        }),
      );

    // Type rows pinned at the top, fuzzy-matched against their labels so the
    // user can type "work" and land on "Workspaces". The List post-hoc
    // drops these when the user has drilled into a specific type. Agents
    // are deliberately omitted from `TYPE_ROW_ORDER` — to filter to a
    // workspace's agents the user drills into a specific workspace row.
    const typeRows: Array<TypeRowItem> = TYPE_ROW_ORDER.filter((entityType) =>
      query === "" ? true : TYPE_LABELS[entityType].toLowerCase().includes(lowerQuery),
    ).map(makeTypeRow);

    // Interleave section headers between non-empty groups so the shared
    // SuggestionListContainer can render + skip them uniformly. The first
    // header on the list carries `isFirstInList` so the layout can tighten
    // its top padding for that row only. When type rows sit above, no
    // header is ever "first in list" — the type rows own the top edge.
    const rows: Array<EntityPickerRow> = [...typeRows];
    const sectionHeader = (label: string): SectionHeaderItem => ({
      ...new SuggestionItem(`__section-${label}`, label),
      isSectionHeader: true,
      isFirstInList: rows.length === 0,
    });
    // Labels are kept uppercase so existing integration-test DOM assertions
    // (e.g. `to_contain_text("REPOSITORIES")`) still pass; the CSS
    // text-transform is a visual belt-and-braces on top.
    if (repoItems.length > 0) {
      rows.push(sectionHeader("REPOSITORIES"), ...repoItems);
    }

    if (workspaceItems.length > 0) {
      rows.push(sectionHeader("WORKSPACES"), ...workspaceItems);
    }

    if (agentItems.length > 0) {
      rows.push(sectionHeader("AGENTS"), ...agentItems);
    }
    return rows;
  },

  command: ({ editor, range, props: item }): void => {
    // Type-row clicks reach here too (SuggestionListContainer routes all
    // `selectItem` calls through `props.command`). `EntityMentionList`
    // wraps our command at render time and intercepts type rows there so
    // it can update its local state; by the time a row reaches this
    // handler it is guaranteed to be a concrete `EntityMentionItem`.
    const mentionItem = item as unknown as EntityMentionItem;
    editor
      .chain()
      .focus()
      .deleteRange(range)
      .insertContent([
        {
          type: "mention",
          attrs: {
            entityType: mentionItem.entityType,
            entityId: mentionItem.entityId,
            entityDisplayName: mentionItem.entityDisplayName,
          },
        },
        { type: "text", text: " " },
      ])
      .run();
  },

  render: renderSuggestion(EntityMentionList),
});
