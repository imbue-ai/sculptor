import { Flex, Skeleton, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

const SKELETON_ROW_WIDTHS = ["70%", "50%", "80%", "60%", "45%", "75%", "55%", "65%"];
const SKELETON_ROW_INDENTS = [0, 16, 16, 32, 32, 16, 32, 16];
const SKELETON_ROW_HEIGHT = 28;

export const EmptyState = (): ReactElement => {
  return (
    <Flex align="center" justify="center" flexGrow="1" data-testid={ElementIds.FILE_BROWSER_EMPTY}>
      <Text size="2" color="gray">
        No files yet
      </Text>
    </Flex>
  );
};

export const SkeletonLoading = (): ReactElement => {
  return (
    <Flex direction="column" gap="1" p="2" data-testid={ElementIds.FILE_BROWSER_SKELETON}>
      {SKELETON_ROW_WIDTHS.map((width, index) => (
        <Flex
          key={index}
          align="center"
          style={{ height: SKELETON_ROW_HEIGHT, paddingLeft: SKELETON_ROW_INDENTS[index] }}
        >
          <Skeleton style={{ width, height: 14, borderRadius: 4 }} />
        </Flex>
      ))}
    </Flex>
  );
};
