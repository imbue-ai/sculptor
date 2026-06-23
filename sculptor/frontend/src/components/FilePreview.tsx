import { Flex, IconButton, Skeleton, Text, Tooltip } from "@radix-ui/themes";
import { FileIcon, FileWarningIcon, XIcon } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useThemeDangerColor } from "~/common/state/hooks/useThemeBuilder.ts";
import { mergeClasses, optional } from "~/common/Utils.ts";

import { CopyImageContextMenu } from "./CopyImageContextMenu.tsx";
import styles from "./FilePreview.module.scss";

type FilePreviewProps = {
  filePath: string;
  fileUrl?: string;
  isFailed: boolean;
  isPdf: boolean;
  isVideo: boolean;
  fileName: string;
  onRemove?: () => void;
  onError: () => void;
  onClick?: () => void;
  displayMode?: "compact" | "inline" | "full";
  /** When true, image content gets a right-click "Copy Image" context menu. */
  allowCopyImage?: boolean;
};

export const FilePreview = ({
  filePath,
  fileUrl,
  isFailed,
  isPdf,
  isVideo,
  fileName,
  onRemove,
  onError,
  onClick,
  displayMode = "compact",
  allowCopyImage = false,
}: FilePreviewProps): ReactElement => {
  const dangerColor = useThemeDangerColor();
  const isInline = displayMode === "inline";
  const isFull = displayMode === "full";

  // Wrap a loaded image element in the Copy Image context menu when enabled.
  const withCopyImageMenu = (element: ReactElement): ReactElement =>
    allowCopyImage && fileUrl ? <CopyImageContextMenu url={fileUrl}>{element}</CopyImageContextMenu> : element;

  const renderFullContent = (): ReactElement => {
    if (isFailed) {
      return (
        <Tooltip content="Failed to load file. The file may be corrupted or inaccessible.">
          <Flex align="center" justify="center" direction="column" gap="1" className={styles.fullError}>
            <FileWarningIcon size={20} />
            <Text size="1" color={dangerColor} truncate>
              {fileName}
            </Text>
          </Flex>
        </Tooltip>
      );
    }

    if (!fileUrl) {
      return <Skeleton className={styles.fullSkeleton} />;
    }

    if (isPdf) {
      return (
        <Tooltip content={fileName}>
          <Flex align="center" justify="center" direction="column" className={styles.preview} mt="1">
            <FileIcon size={12} />
          </Flex>
        </Tooltip>
      );
    }

    if (isVideo) {
      return (
        <video
          src={fileUrl}
          className={styles.fullMedia}
          onError={onError}
          data-testid={ElementIds.FILE_PREVIEW}
          data-path={filePath}
          controls
          muted
          onClick={onClick}
        />
      );
    }

    return withCopyImageMenu(
      <img
        src={fileUrl}
        alt={`Attachment: ${fileName}`}
        className={styles.fullMedia}
        onError={onError}
        data-testid={ElementIds.FILE_PREVIEW}
        data-path={filePath}
        onClick={onClick}
      />,
    );
  };

  const renderInlineContent = (): ReactElement => {
    if (isFailed) {
      return (
        <Tooltip content="Failed to load file. The file may be corrupted or inaccessible.">
          <Flex align="center" justify="center" direction="column" gap="1" className={styles.inlineError}>
            <FileWarningIcon size={20} />
            <Text size="1" color={dangerColor} truncate>
              {fileName}
            </Text>
          </Flex>
        </Tooltip>
      );
    }

    if (!fileUrl) {
      return <Skeleton className={styles.inlineSkeleton} />;
    }

    if (isPdf) {
      // PDFs have no meaningful inline representation; fall back to compact icon
      return (
        <Tooltip content={fileName}>
          <Flex align="center" justify="center" direction="column" className={styles.preview} mt="1">
            <FileIcon size={12} />
          </Flex>
        </Tooltip>
      );
    }

    if (isVideo) {
      return (
        <video
          src={fileUrl}
          className={mergeClasses(styles.inlineMedia, optional(!!onClick, styles.clickable))}
          onError={onError}
          data-testid={ElementIds.FILE_PREVIEW}
          data-path={filePath}
          controls
          muted
          onClick={onClick}
        />
      );
    }

    return withCopyImageMenu(
      <img
        src={fileUrl}
        alt={`Attachment: ${fileName}`}
        className={mergeClasses(styles.inlineMedia, optional(!!onClick, styles.clickable))}
        onError={onError}
        data-testid={ElementIds.FILE_PREVIEW}
        data-path={filePath}
        onClick={onClick}
      />,
    );
  };

  const renderCompactContent = (): ReactElement => {
    if (isFailed) {
      return (
        <Tooltip content="Failed to load file. The file may be corrupted or inaccessible.">
          <Flex align="center" justify="center" className={styles.previewError}>
            <Text size="1" color={dangerColor} className={styles.previewErrorIcon}>
              <FileWarningIcon />
            </Text>
          </Flex>
        </Tooltip>
      );
    }

    if (!fileUrl) {
      return <Skeleton className={styles.previewSkeleton} />;
    }

    if (isPdf) {
      return (
        <Tooltip content={fileName}>
          <Flex align="center" justify="center" direction="column" className={styles.preview} mt="1">
            <FileIcon size={12} />
          </Flex>
        </Tooltip>
      );
    }

    if (isVideo) {
      return (
        <video
          src={fileUrl}
          className={styles.preview}
          onError={onError}
          data-testid={ElementIds.FILE_PREVIEW}
          data-path={filePath}
          muted
        />
      );
    }

    return (
      <img
        src={fileUrl}
        alt={`Attachment: ${fileName}`}
        className={styles.preview}
        onError={onError}
        data-testid={ElementIds.FILE_PREVIEW}
        data-path={filePath}
      />
    );
  };

  if (isFull) {
    return <div data-testid={ElementIds.FILE_PREVIEW_CONTAINER}>{renderFullContent()}</div>;
  }

  if (isInline) {
    return (
      <div className={styles.inlineWrapper} data-testid={ElementIds.FILE_PREVIEW_CONTAINER}>
        {renderInlineContent()}
      </div>
    );
  }

  return (
    <div className={styles.previewWrapper} data-testid={ElementIds.FILE_PREVIEW_CONTAINER}>
      <div
        className={mergeClasses(
          isFailed ? styles.previewContainerFailed : styles.previewContainer,
          optional(!!onClick && !isFailed && !isPdf, styles.clickable),
        )}
        onClick={onClick && !isFailed && !isPdf ? onClick : undefined}
      >
        {renderCompactContent()}
      </div>
      {onRemove && (
        <Tooltip content="Delete image">
          <IconButton
            size="1"
            variant="solid"
            onClick={(event) => {
              event.stopPropagation();
              onRemove();
            }}
            className={styles.removeButton}
            data-testid={ElementIds.FILE_PREVIEW_REMOVE}
          >
            <XIcon size={10} />
          </IconButton>
        </Tooltip>
      )}
    </div>
  );
};
