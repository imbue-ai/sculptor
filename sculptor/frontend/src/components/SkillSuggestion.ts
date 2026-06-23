import { PluginKey } from "@tiptap/pm/state";
import type { SuggestionOptions } from "@tiptap/suggestion";

import { BUILTIN_SKILLS } from "~/common/builtinSkills";
import { PSEUDO_SKILLS } from "~/common/pseudoSkills";
import { fetchFreshProjectSkills } from "~/common/state/hooks/useProjectSkills";
import { fetchFreshWorkspaceSkills } from "~/common/state/hooks/useWorkspaceSkills";

import { scoreFilePath } from "./fuzzyFileScorer";
import { badgeLabelForType, type SkillType } from "./skillBadge";
import { SkillList } from "./SkillList";
import { isPositionDismissed } from "./SuggestionDismissalPlugin";
import { renderSuggestion, showSuggestionOnlyWhenTyping, SuggestionItem } from "./SuggestionUtils";

export class SkillItem extends SuggestionItem {
  description: string;
  skillType: SkillType;

  constructor(id: string, label: string, description: string, skillType: SkillType) {
    super(id, label);
    this.description = description;
    this.skillType = skillType;
  }
}

type SkillSource = { workspaceID: string } | { projectID: string };

export const createSkillSuggestion = (source: SkillSource): Omit<SuggestionOptions, "editor"> => {
  const fetchApiSkillItems = async (): Promise<Array<SkillItem>> => {
    try {
      const apiSkills =
        "workspaceID" in source
          ? await fetchFreshWorkspaceSkills(source.workspaceID)
          : await fetchFreshProjectSkills(source.projectID);
      return apiSkills.map((skill) => new SkillItem(`/${skill.name}`, skill.name, skill.description, skill.type));
    } catch (error: unknown) {
      console.error("Error fetching skills for /-command:", error);
      return [];
    }
  };

  const getAllSkills = async (): Promise<Array<SkillItem>> => {
    const customSkills = await fetchApiSkillItems();
    const pseudoSkillItems = PSEUDO_SKILLS.map((s) => new SkillItem(`/${s.name}`, s.name, s.description, "builtin"));
    const builtinSkillItems = BUILTIN_SKILLS.map((s) => new SkillItem(`/${s.name}`, s.name, s.description, "builtin"));
    return [...customSkills, ...pseudoSkillItems, ...builtinSkillItems].sort((a, b) => a.label.localeCompare(b.label));
  };

  // Eagerly warm the shared TanStack Query cache so the list is ready by the
  // time the user types "/". Without this, the first "/" on the Open
  // Workspace page feels slow because the fetch only starts on keystroke.
  if ("workspaceID" in source) {
    void fetchFreshWorkspaceSkills(source.workspaceID);
  } else {
    void fetchFreshProjectSkills(source.projectID);
  }

  const pluginKey = new PluginKey("skill");
  return {
    pluginKey,
    char: "/",
    startOfLine: false,
    allowedPrefixes: [" "],
    allow: ({ state, range }): boolean => {
      const $from = state.doc.resolve(range.from);
      if ($from.parent.type.name === "codeBlock") {
        return false;
      }
      const codeMark = state.schema.marks.code;
      if (codeMark && state.doc.rangeHasMark(range.from, range.from + 1, codeMark)) {
        return false;
      }

      if (isPositionDismissed(state, range.from)) {
        return false;
      }
      return true;
    },
    // Don't reopen on a pure cursor move into an existing `/path` (SCU-1298).
    shouldShow: showSuggestionOnlyWhenTyping(pluginKey),
    items: async ({ query }): Promise<Array<SkillItem>> => {
      const allSkills = await getAllSkills();
      if (!query) {
        return allSkills;
      }
      // Match against the type label too so users can filter by type — typing
      // "sculptor", "built-in" / "builtin", or "custom" surfaces every skill
      // of that type. Take the max so a strong name match still outranks a
      // type match.
      return allSkills
        .map((skill) => {
          const labelScore = scoreFilePath(query, skill.label);
          const typeScore = scoreFilePath(query, badgeLabelForType(skill.skillType));
          return { skill, score: Math.max(labelScore, typeScore) };
        })
        .filter(({ score }) => score > 0)
        .sort((a, b) => b.score - a.score)
        .map(({ skill }) => skill);
    },
    command: ({ editor, range, props: item }): void => {
      const skillItem = item as SkillItem;
      editor
        .chain()
        .focus()
        .deleteRange(range)
        .insertContent([
          {
            type: "mention",
            attrs: {
              id: skillItem.id,
              label: skillItem.label,
              mentionSuggestionChar: "/",
              skillDescription: skillItem.description,
              skillType: skillItem.skillType,
            },
          },
          { type: "text", text: " " },
        ])
        .run();
    },
    render: renderSuggestion(SkillList),
  };
};
