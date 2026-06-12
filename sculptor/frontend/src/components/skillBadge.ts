import type { Badge } from "@radix-ui/themes";
import type { ComponentProps } from "react";

export type SkillType = "builtin" | "custom" | "sculptor";
export type BadgeColor = ComponentProps<typeof Badge>["color"];

// `undefined` falls back to the theme's accent color (used for user-authored
// "custom" skills, which are most of the list).
export const badgeColorForType = (skillType: SkillType | null | undefined): BadgeColor => {
  if (skillType === "builtin") return "indigo";
  if (skillType === "sculptor") return "green";
  return undefined;
};

export const badgeLabelForType = (skillType: SkillType | null | undefined): string => {
  if (skillType === "builtin") return "built-in";
  if (skillType === "sculptor") return "Sculptor";
  return "custom";
};
