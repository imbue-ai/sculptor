import { atom } from "jotai";

import type { SkillType } from "~/common/utils/skillBadge";

export type InsertSkillArg = {
  name: string;
  description: string;
  type: SkillType;
};

export type ChatActions = {
  appendText: ((text: string) => void) | null;
  insertSkill: ((skill: InsertSkillArg) => void) | null;
  sendMessage: ((message: string) => Promise<void>) | null;
  isDisabled: boolean;
};

export const chatActionsAtom = atom<ChatActions>({
  appendText: null,
  insertSkill: null,
  sendMessage: null,
  isDisabled: true,
});
