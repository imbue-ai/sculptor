import type { CustomAction, CustomActionGroup } from "~/api";

export const SCULPTOR_BUILTIN_GROUP_ID = "__sculptor__";

const SCULPTOR_BUILTIN_ACTION_IDS = [
  `${SCULPTOR_BUILTIN_GROUP_ID}__fix_bug`,
  `${SCULPTOR_BUILTIN_GROUP_ID}__help`,
] as const;

export const BUILTIN_SCULPTOR_GROUP: CustomActionGroup = {
  id: SCULPTOR_BUILTIN_GROUP_ID,
  name: "Sculptor",
  order: -1,
};

export const BUILTIN_SCULPTOR_ACTIONS: ReadonlyArray<CustomAction> = [
  {
    id: SCULPTOR_BUILTIN_ACTION_IDS[1],
    name: "/help",
    prompt: "/sculptor:help",
    autoSubmit: false,
    groupId: SCULPTOR_BUILTIN_GROUP_ID,
    order: 0,
  },
  {
    id: SCULPTOR_BUILTIN_ACTION_IDS[0],
    name: "/fix-bug",
    prompt: "/sculptor-workflow:fix-bug",
    autoSubmit: false,
    groupId: SCULPTOR_BUILTIN_GROUP_ID,
    order: 1,
  },
];

const BUILTIN_GROUP_ID_SET = new Set<string>([SCULPTOR_BUILTIN_GROUP_ID]);
const BUILTIN_ACTION_ID_SET = new Set<string>(SCULPTOR_BUILTIN_ACTION_IDS);

export const isBuiltInGroup = (groupId: unknown): boolean => {
  return typeof groupId === "string" && BUILTIN_GROUP_ID_SET.has(groupId);
};

export const isBuiltInAction = (actionId: unknown): boolean => {
  return typeof actionId === "string" && BUILTIN_ACTION_ID_SET.has(actionId);
};
