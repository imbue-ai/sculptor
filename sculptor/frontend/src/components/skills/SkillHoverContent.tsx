import { Badge, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { badgeColorForType, badgeLabelForType, type SkillType } from "../skillBadge";

type SkillHoverContentProps = {
  id: string;
  skillDescription?: string | null;
  skillType?: SkillType | null;
};

export const SkillHoverContent = ({ id, skillDescription, skillType }: SkillHoverContentProps): ReactElement => (
  <Flex direction="column" gap="2" style={{ padding: "var(--space-2) var(--space-3)", maxWidth: 300 }}>
    {skillType && (
      <Badge variant="soft" color={badgeColorForType(skillType)} style={{ alignSelf: "flex-start" }}>
        {badgeLabelForType(skillType)}
      </Badge>
    )}
    <Text
      size="2"
      weight="medium"
      truncate
      style={{ color: "var(--gray-12)", fontFamily: "var(--default-font-family)" }}
    >
      {id}
    </Text>
    {skillDescription && (
      <Text
        as="div"
        style={{
          color: "var(--gray-12)",
          fontFamily: "var(--default-font-family)",
          fontSize: "var(--font-size-1-5)",
        }}
      >
        {skillDescription}
      </Text>
    )}
  </Flex>
);
