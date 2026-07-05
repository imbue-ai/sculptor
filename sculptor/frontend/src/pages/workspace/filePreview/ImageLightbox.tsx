import { ChevronLeftIcon, ChevronRightIcon } from "@radix-ui/react-icons";
import { VisuallyHidden } from "@radix-ui/react-visually-hidden";
import { Dialog, Flex, IconButton } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useEffect, useState } from "react";

import { ElementIds } from "~/api";

import { CopyImageContextMenu } from "./CopyImageContextMenu.tsx";
import styles from "./ImageLightbox.module.scss";

type MediaFile = {
  url: string;
  name: string;
  isVideo: boolean;
};

type ImageLightboxProps = {
  media: Array<MediaFile>;
  initialIndex: number;
  onClose: () => void;
  /** When true, the full-size image gets a right-click "Copy Image" context menu. */
  allowCopyImage?: boolean;
};

export const ImageLightbox = ({
  media,
  initialIndex,
  onClose,
  allowCopyImage = false,
}: ImageLightboxProps): ReactElement => {
  const [currentIndex, setCurrentIndex] = useState<number>(initialIndex);
  const currentItem = media[currentIndex];
  const hasMultiple = media.length > 1;
  const isAtStart = currentIndex === 0;
  const isAtEnd = currentIndex === media.length - 1;

  const goToPrevious = useCallback((): void => {
    setCurrentIndex((i) => Math.max(0, i - 1));
  }, []);

  const goToNext = useCallback((): void => {
    setCurrentIndex((i) => Math.min(media.length - 1, i + 1));
  }, [media.length]);

  useEffect(() => {
    if (!hasMultiple) return;

    const handleKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        goToPrevious();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        goToNext();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return (): void => window.removeEventListener("keydown", handleKeyDown);
  }, [hasMultiple, goToPrevious, goToNext]);

  const ariaLabel = currentItem.isVideo ? "Video preview" : "Image preview";

  return (
    <Dialog.Root open onOpenChange={(open) => !open && onClose()}>
      <Dialog.Content className={styles.dialogContent} aria-label={`${ariaLabel}: ${currentItem.name}`}>
        <VisuallyHidden>
          <Dialog.Title>{ariaLabel}</Dialog.Title>
          <Dialog.Description>
            {hasMultiple
              ? "Use the left and right arrow keys to navigate between media. Press Escape to close."
              : "Press Escape to close."}
          </Dialog.Description>
        </VisuallyHidden>
        {hasMultiple && !isAtStart && (
          <IconButton
            variant="ghost"
            size="3"
            radius="full"
            color="gray"
            className={`${styles.navButton} ${styles.navPrevious}`}
            onClick={goToPrevious}
            aria-label="Previous image"
            data-testid={ElementIds.LIGHTBOX_NAV_PREVIOUS}
          >
            <ChevronLeftIcon width="24" height="24" />
          </IconButton>
        )}
        <Flex direction="column" align="center" gap="3">
          {currentItem.isVideo ? (
            <video src={currentItem.url} className={styles.image} controls autoPlay muted />
          ) : allowCopyImage ? (
            <CopyImageContextMenu url={currentItem.url}>
              <img src={currentItem.url} alt={`Full size: ${currentItem.name}`} className={styles.image} />
            </CopyImageContextMenu>
          ) : (
            <img src={currentItem.url} alt={`Full size: ${currentItem.name}`} className={styles.image} />
          )}
          <span className={styles.fileName}>
            {currentItem.name}
            {hasMultiple && (
              <span data-testid={ElementIds.LIGHTBOX_COUNTER}>{` (${currentIndex + 1}/${media.length})`}</span>
            )}
          </span>
        </Flex>
        {hasMultiple && !isAtEnd && (
          <IconButton
            variant="ghost"
            size="3"
            radius="full"
            color="gray"
            className={`${styles.navButton} ${styles.navNext}`}
            onClick={goToNext}
            aria-label="Next image"
            data-testid={ElementIds.LIGHTBOX_NAV_NEXT}
          >
            <ChevronRightIcon width="24" height="24" />
          </IconButton>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};
