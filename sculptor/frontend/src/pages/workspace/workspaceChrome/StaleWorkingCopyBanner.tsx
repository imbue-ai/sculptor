import { Button, Callout, Flex, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { TriangleAlert } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";

import { useUpdateStaleWorkingCopy } from "./hooks/useUpdateStaleWorkingCopy.ts";
import styles from "./StaleWorkingCopyBanner.module.scss";

const STALE_EXPLANATION =
  "This workspace's working copy is stale: another jj operation rewrote its revision, so jj will not record changes to its files until it is updated.";

/**
 * Shown while a jj workspace's working copy is stale: an operation elsewhere in
 * the repository rewrote the working-copy revision, so jj refuses to snapshot
 * the files until the working copy is updated. The update is only ever the
 * user's choice, because updating over edits jj has not snapshotted can leave a
 * divergent change behind.
 */
export const StaleWorkingCopyBanner = ({ workspaceId }: { workspaceId: string }): ReactElement | null => {
  const isStale = useAtomValue(workspaceJjStateAtomFamily(workspaceId))?.isWorkingCopyStale ?? false;
  const { updateWorkingCopy, isUpdating, errorMessage } = useUpdateStaleWorkingCopy(workspaceId);

  if (!isStale) {
    return null;
  }

  return (
    <Callout.Root color="amber" size="1" className={styles.banner} data-testid={ElementIds.JJ_STALE_BANNER}>
      <Callout.Icon>
        <TriangleAlert size={16} />
      </Callout.Icon>
      <Flex align="center" justify="between" gap="3" wrap="wrap">
        <Flex direction="column" gap="1">
          <Text size="2">{STALE_EXPLANATION}</Text>
          {errorMessage !== null && (
            <Text size="2" color="red">
              Could not update the working copy: {errorMessage}
            </Text>
          )}
        </Flex>
        <Button
          size="1"
          variant="solid"
          color="amber"
          onClick={updateWorkingCopy}
          loading={isUpdating}
          data-testid={ElementIds.JJ_UPDATE_STALE_BUTTON}
        >
          Update working copy
        </Button>
      </Flex>
    </Callout.Root>
  );
};
