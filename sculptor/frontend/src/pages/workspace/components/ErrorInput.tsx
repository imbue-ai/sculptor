import { Flex, Link, Text } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useState } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { useIsWorkspaceDeleted } from "~/common/state/hooks/useWorkspace.ts";
import { useRestoreTaskMutation } from "~/common/state/mutations";
import { Toast, type ToastContent, ToastType } from "~/components/Toast.tsx";

import styles from "./ErrorInput.module.scss";

type ErrorInputProps = {
  workspaceId: string;
  taskId: string;
};

export const ErrorInput = ({ workspaceId, taskId }: ErrorInputProps): ReactElement => {
  const [toast, setToast] = useState<ToastContent | null>(null);
  const isWorkspaceDeleted = useIsWorkspaceDeleted(workspaceId);
  const dangerColor = useThemeDangerColor();
  const { mutate: restoreMutate } = useRestoreTaskMutation();

  const handleRestore = (): void => {
    restoreMutate(
      { workspaceId, agentId: taskId },
      {
        onError: (error): void => {
          console.error("Failed to restore agent:", error);
          setToast({ title: "Failed to restore agent", type: ToastType.ERROR });
        },
      },
    );
  };

  return (
    <>
      <Flex
        px="4"
        py="3"
        gap="1"
        className={styles.statusBox}
        align="center"
        justify="center"
        wrap="wrap"
        data-testid={ElementIds.ERROR_INPUT}
        data-accent-color={dangerColor}
      >
        {isWorkspaceDeleted ? (
          <Text>The agent is in an error state. Its workspace has been deleted and cannot be restored.</Text>
        ) : (
          <>
            <Text>The agent is in an error state. </Text>
            <Link onClick={() => handleRestore()}>Click here to try to restore the agent.</Link>
          </>
        )}
      </Flex>
      <Toast open={!!toast} onOpenChange={(open) => !open && setToast(null)} title={toast?.title} type={toast?.type} />
    </>
  );
};
