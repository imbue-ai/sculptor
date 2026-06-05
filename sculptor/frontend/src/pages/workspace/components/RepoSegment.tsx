import { AlertDialog, Badge, Button, DropdownMenu, Flex, Tooltip } from "@radix-ui/themes";
import { ClipboardIcon, FolderIcon, FolderOpenIcon } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useState } from "react";

import { ElementIds, type ExternalApp, openPathInApp, WorkspaceInitializationStrategy } from "~/api";
import { useKeybindingDisplayText, useKeybindingHandler } from "~/common/keybindings/hooks";
import { getOpenWithItems, getPreferredApp, savePreferredApp } from "~/common/openInApp/items";
import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities";

import styles from "./RepoSegment.module.scss";

type RepoSegmentProps = {
  sourcePath: string;
  environmentPath: string | null;
  strategy: WorkspaceInitializationStrategy;
  shouldShowModeBadge: boolean;
  projectName: string;
  /** Collapse to just the folder icon (the dropdown still opens). (REQ-TOPBAR-4) */
  iconOnly?: boolean;
  "data-testid"?: string;
};

const MODE_BADGE_LABEL: Record<WorkspaceInitializationStrategy, string> = {
  [WorkspaceInitializationStrategy.IN_PLACE]: "in-place",
  [WorkspaceInitializationStrategy.CLONE]: "clone",
  [WorkspaceInitializationStrategy.WORKTREE]: "worktree",
};

export const RepoSegment = ({
  sourcePath,
  environmentPath,
  strategy,
  shouldShowModeBadge,
  projectName,
  iconOnly = false,
}: RepoSegmentProps): ReactElement => {
  const isInPlace = strategy === WorkspaceInitializationStrategy.IN_PLACE;
  const badgeLabel = MODE_BADGE_LABEL[strategy];
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [preferredApp, setPreferredApp] = useState<ExternalApp | null>(getPreferredApp);
  const canOpenInOS = getBackendCapabilities().canOpenInOS;
  const openWithItems = canOpenInOS ? getOpenWithItems() : [];

  const codePath = environmentPath ? `${environmentPath}/code` : null;
  const openWithPath = isInPlace ? sourcePath : (codePath ?? sourcePath);
  const copyPath = openWithPath;
  const relativePath = openWithPath.split("/").pop() ?? openWithPath;

  const handleOpenWithApp = useCallback(
    (app: ExternalApp): void => {
      savePreferredApp(app);
      setPreferredApp(app);
      openPathInApp({
        body: { path: openWithPath, app },
        meta: { skipWsAck: true },
      })
        .then((response) => {
          if (!response.data.success) {
            const appItem = getOpenWithItems().find((item) => item.app === app);
            const appLabel = appItem?.label ?? app;
            setErrorMessage(response.data.errorMessage ?? `Failed to open ${appLabel}. Please try again.`);
          }
        })
        .catch(() => {
          const appItem = getOpenWithItems().find((item) => item.app === app);
          const appLabel = appItem?.label ?? app;
          setErrorMessage(`Failed to open ${appLabel}. Please try again.`);
        });
    },
    [openWithPath],
  );

  const handleCopyPath = useCallback((): void => {
    navigator.clipboard.writeText(copyPath);
  }, [copyPath]);

  const handleCopyRelativePath = useCallback((): void => {
    navigator.clipboard.writeText(relativePath);
  }, [relativePath]);

  const handleOpenFolder = useCallback((): void => {
    handleOpenWithApp("finder");
  }, [handleOpenWithApp]);

  useKeybindingHandler(
    "open_in_app",
    useCallback(() => {
      if (canOpenInOS && preferredApp) {
        handleOpenWithApp(preferredApp);
      }
    }, [canOpenInOS, preferredApp, handleOpenWithApp]),
  );

  const openInAppDisplayText = useKeybindingDisplayText("open_in_app");

  return (
    <>
      <Flex align="center" gap="2">
        <DropdownMenu.Root>
          <Tooltip content={iconOnly ? projectName : "Repo name and environment"} side="bottom">
            <DropdownMenu.Trigger>
              <Button
                variant="ghost"
                size="1"
                color="gray"
                className={styles.segment}
                data-testid={ElementIds.REPO_PATH_DROPDOWN_TRIGGER}
              >
                <FolderIcon size={12} className={styles.icon} />
                {!iconOnly && (
                  <>
                    <span className={styles.repoName}>{projectName}</span>
                    <DropdownMenu.TriggerIcon />
                  </>
                )}
              </Button>
            </DropdownMenu.Trigger>
          </Tooltip>
          <DropdownMenu.Content size="1">
            {canOpenInOS && (
              <DropdownMenu.Item onSelect={handleOpenFolder}>
                <Flex align="center" gap="2">
                  <FolderOpenIcon size={14} />
                  Open folder
                </Flex>
              </DropdownMenu.Item>
            )}
            <DropdownMenu.Item onSelect={handleCopyRelativePath}>
              <Flex align="center" gap="2">
                <ClipboardIcon size={14} />
                Copy relative path
              </Flex>
            </DropdownMenu.Item>
            <DropdownMenu.Item onSelect={handleCopyPath} data-testid={ElementIds.REPO_PATH_DROPDOWN_COPY_PATH}>
              <Flex align="center" gap="2">
                <ClipboardIcon size={14} />
                Copy path
              </Flex>
            </DropdownMenu.Item>
            {openWithItems.length > 0 && <DropdownMenu.Separator />}
            {openWithItems.map((item) => (
              <DropdownMenu.Item
                key={item.app}
                onSelect={() => handleOpenWithApp(item.app)}
                data-testid={ElementIds.REPO_PATH_DROPDOWN_APP_ITEM}
              >
                <Flex align="center" gap="2" className={styles.menuItemContent}>
                  <img src={item.icon} alt="" width={14} height={14} className={styles.appIcon} />
                  {item.label}
                  {preferredApp === item.app && openInAppDisplayText && (
                    <span className={styles.shortcutHint} data-testid={ElementIds.REPO_PATH_DROPDOWN_SHORTCUT_HINT}>
                      {openInAppDisplayText}
                    </span>
                  )}
                </Flex>
              </DropdownMenu.Item>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Root>
        {shouldShowModeBadge && (
          <Badge size="1" color="gray" variant="solid" data-testid={ElementIds.TASK_MODE_BADGE}>
            {badgeLabel}
          </Badge>
        )}
      </Flex>
      <AlertDialog.Root open={errorMessage !== null} onOpenChange={(open) => !open && setErrorMessage(null)}>
        <AlertDialog.Content maxWidth="400px">
          <AlertDialog.Title>Could not open application</AlertDialog.Title>
          <AlertDialog.Description>{errorMessage}</AlertDialog.Description>
          <Flex mt="4" justify="end">
            <AlertDialog.Cancel>
              <Button variant="soft" color="gray" data-testid={ElementIds.REPO_PATH_DROPDOWN_ALERT_OK}>
                OK
              </Button>
            </AlertDialog.Cancel>
          </Flex>
        </AlertDialog.Content>
      </AlertDialog.Root>
    </>
  );
};
