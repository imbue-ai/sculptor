import { useSortable } from "@dnd-kit/sortable";
import * as HoverCard from "@radix-ui/react-hover-card";
import { ContextMenu, IconButton } from "@radix-ui/themes";
import { X } from "lucide-react";
import type { MouseEvent, ReactElement } from "react";
import { useEffect, useRef, useState } from "react";

import { ElementIds } from "~/api";
import type { SortableTabProps } from "~/components/tabs/types";

import styles from "./SortableTab.module.scss";

const HOVER_PREVIEW_DELAY_MS = 600;
const COMPACT_CLOSE_ICON_SIZE = 12;
const DEFAULT_CLOSE_ICON_SIZE = 14;

export const SortableTab = ({
  tab,
  isActive,
  isCloseable,
  isDragActive,
  width,
  dropIndicator,
  onActivate,
  onClose,
  onDoubleClick,
  variant = "default",
  contextMenuContent,
  closeReplacesIcon = false,
}: SortableTabProps): ReactElement => {
  const [isHovered, setIsHovered] = useState<boolean>(false);
  const [isPreviewOpen, setIsPreviewOpen] = useState<boolean>(false);
  const wasDragActiveRef = useRef<boolean>(false);

  const isCompact = variant === "compact";

  const { attributes, listeners, setNodeRef, isDragging } = useSortable({ id: tab.id });

  useEffect((): void => {
    if (wasDragActiveRef.current && !isDragActive) {
      setIsHovered(false);
    }
    wasDragActiveRef.current = isDragActive;
  }, [isDragActive]);

  const handleClick = (): void => {
    onActivate(tab.id);
  };

  const handleDoubleClick = (): void => {
    onDoubleClick?.(tab.id);
  };

  const handleClose = (event: MouseEvent): void => {
    event.stopPropagation();
    onClose(tab.id);
  };

  const handleAuxClick = (event: MouseEvent): void => {
    if (event.button === 1 && isCloseable) {
      event.preventDefault();
      onClose(tab.id);
    }
  };

  const isEffectivelyHovered = isHovered && !isDragActive;
  const shouldShowCloseButton = isCloseable && (isEffectivelyHovered || isActive);

  const dropClass = dropIndicator === "left" ? styles.dropLeft : dropIndicator === "right" ? styles.dropRight : "";

  const customDataAttrs = tab.dataAttributes
    ? Object.fromEntries(Object.entries(tab.dataAttributes).map(([k, v]) => [`data-${k}`, v]))
    : {};

  const compactDropClass =
    dropIndicator === "left" ? styles.compactDropLeft : dropIndicator === "right" ? styles.compactDropRight : "";

  const tabClassName = isCompact
    ? `${styles.tabCompact} ${isActive ? styles.compactActive : ""} ${isEffectivelyHovered ? styles.compactHovered : ""} ${isDragging ? styles.compactDragging : ""} ${compactDropClass}`
    : `${styles.tab} ${isActive ? styles.active : ""} ${isEffectivelyHovered ? styles.hovered : ""} ${isDragging ? styles.dragging : ""} ${dropClass}`;

  const closeIconSize = isCompact ? COMPACT_CLOSE_ICON_SIZE : DEFAULT_CLOSE_ICON_SIZE;
  const closeButtonClass = isCompact ? styles.compactCloseButton : styles.closeButton;
  // Compact: always render close button so width stays stable (CSS handles visibility via opacity).
  // Default: conditionally render to avoid reserving space in fixed-width tabs.
  const shouldRenderCloseButton = isCompact ? isCloseable : shouldShowCloseButton;

  // When closeReplacesIcon is set, the leading icon turns into the close button
  // on hover rather than showing a separate trailing close button.
  const shouldShowCloseInIconSlot = closeReplacesIcon && isCloseable && isEffectivelyHovered;
  const closeButton = (
    <IconButton
      variant="ghost"
      size="1"
      color="gray"
      data-testid={ElementIds.TAB_CLOSE_BUTTON}
      className={closeButtonClass}
      onClick={handleClose}
      aria-label={`Close ${tab.label}`}
    >
      {tab.closeIcon ?? <X width={closeIconSize} height={closeIconSize} />}
    </IconButton>
  );
  // A close button sized to occupy the exact same footprint as the leading icon,
  // so swapping icon ↔ close on hover doesn't shift the label (closeReplacesIcon).
  const iconSlotCloseButton = (
    <button
      type="button"
      data-testid={ElementIds.TAB_CLOSE_BUTTON}
      className={`${styles.icon} ${styles.iconSlotClose}`}
      onClick={handleClose}
      aria-label={`Close ${tab.label}`}
    >
      {tab.closeIcon ?? <X width={closeIconSize} height={closeIconSize} />}
    </button>
  );

  const tabElement = (
    <div
      ref={setNodeRef}
      style={width !== undefined ? { width } : undefined}
      {...attributes}
      {...listeners}
      {...customDataAttrs}
      role="tab"
      aria-selected={isActive}
      data-tab-id={tab.id}
      data-testid={tab.dataTestId}
      className={tabClassName}
      onClick={handleClick}
      onDoubleClick={handleDoubleClick}
      onAuxClick={handleAuxClick}
      onMouseEnter={(): void => setIsHovered(true)}
      onMouseLeave={(): void => setIsHovered(false)}
    >
      {closeReplacesIcon && shouldShowCloseInIconSlot
        ? iconSlotCloseButton
        : tab.icon && <span className={styles.icon}>{tab.icon}</span>}
      <span className={isCompact ? styles.compactLabel : styles.label}>{tab.labelContent ?? tab.label}</span>
      {!closeReplacesIcon && shouldRenderCloseButton && closeButton}
    </div>
  );

  const menuContent = contextMenuContent?.(tab.id);

  const wrapWithPreview = (element: ReactElement): ReactElement => {
    if (!tab.preview || isDragActive || isCompact) return element;
    return (
      <HoverCard.Root
        openDelay={tab.previewOpenDelay ?? HOVER_PREVIEW_DELAY_MS}
        closeDelay={0}
        open={isPreviewOpen && isHovered && !isDragActive}
        onOpenChange={setIsPreviewOpen}
      >
        <HoverCard.Trigger asChild>{element}</HoverCard.Trigger>
        <HoverCard.Content side="bottom" align="start" sideOffset={4} className={styles.previewContent}>
          {tab.preview}
        </HoverCard.Content>
      </HoverCard.Root>
    );
  };

  if (menuContent) {
    return (
      <ContextMenu.Root>
        <ContextMenu.Trigger>{wrapWithPreview(tabElement)}</ContextMenu.Trigger>
        {menuContent}
      </ContextMenu.Root>
    );
  }

  if (tab.contextMenu) {
    return tab.contextMenu(wrapWithPreview(tabElement));
  }

  return wrapWithPreview(tabElement);
};
