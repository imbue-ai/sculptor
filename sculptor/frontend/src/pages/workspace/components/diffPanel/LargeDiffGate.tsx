import { Button, Flex, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useMemo, useRef, useState } from "react";

import { truncateAtHunkBoundary } from "./truncateAtHunkBoundary";

const LARGE_DIFF_LINE_THRESHOLD = 500;

type LargeDiffGateProps = {
  diffString: string;
  children: (renderProps: { visibleDiff: string; isTruncated: boolean }) => ReactElement;
};

export const LargeDiffGate = ({ diffString, children }: LargeDiffGateProps): ReactElement => {
  const [isShowingFullDiff, setIsShowingFullDiff] = useState(false);

  // Reset gating state when the diff content changes (e.g., user navigates to a different file)
  const prevDiffRef = useRef(diffString);
  if (prevDiffRef.current !== diffString) {
    prevDiffRef.current = diffString;
    setIsShowingFullDiff(false);
  }

  const lineCount = useMemo(() => diffString.split("\n").length, [diffString]);
  const isLargeDiff = lineCount > LARGE_DIFF_LINE_THRESHOLD;

  const truncatedDiff = useMemo(() => {
    if (!isLargeDiff || isShowingFullDiff) return diffString;
    return truncateAtHunkBoundary(diffString, LARGE_DIFF_LINE_THRESHOLD);
  }, [diffString, isLargeDiff, isShowingFullDiff]);

  const handleShowFullDiff = useCallback((): void => {
    setIsShowingFullDiff(true);
  }, []);

  const isTruncated = isLargeDiff && !isShowingFullDiff;

  return (
    <>
      {children({ visibleDiff: truncatedDiff, isTruncated })}
      {isTruncated && (
        <Flex align="center" justify="center" py="3">
          <Button variant="soft" size="1" onClick={handleShowFullDiff}>
            <Text size="1">Show full diff ({lineCount} lines)</Text>
          </Button>
        </Flex>
      )}
    </>
  );
};
