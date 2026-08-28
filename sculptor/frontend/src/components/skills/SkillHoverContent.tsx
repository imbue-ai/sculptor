import { Badge, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { badgeColorForType, badgeLabelForType, type SkillType } from "../../common/utils/skillBadge";
import styles from "./SkillHoverContent.module.scss";

type SkillHoverContentProps = {
  id: string;
  skillDescription?: string | null;
  skillType?: SkillType | null;
};

export const SkillHoverContent = ({ id, skillDescription, skillType }: SkillHoverContentProps): ReactElement => (
  <Flex direction="column" gap="2" px="3" py="2" maxWidth="300px">
    {skillType && (
      <Badge variant="soft" color={badgeColorForType(skillType)} className={styles.badge}>
        {badgeLabelForType(skillType)}
      </Badge>
    )}
    <Text size="2" weight="medium" truncate className={styles.title}>
      {id}
    </Text>
    {skillDescription && (
      <Text as="div" className={styles.description}>
        {skillDescription}
      </Text>
    )}
  </Flex>
);
