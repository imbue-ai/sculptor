import type { ReactElement, ReactNode } from "react";

export type TabVariant = "default" | "compact";

export type TabDefinition = {
  id: string;
  label: string;
  icon?: ReactNode;
  content?: ReactNode;
  preview?: ReactNode;
  /** Delay in ms before the preview hover card opens. Defaults to 600ms. */
  previewOpenDelay?: number;
  /** Custom content to render instead of the label text (e.g. an inline rename input). */
  labelContent?: ReactNode;
  /** Custom data-testid applied to the tab element. */
  dataTestId?: string;
  /** Custom data-* attributes applied to the tab element (keys without the "data-" prefix). */
  dataAttributes?: Record<string, string>;
  /** Wrapper that adds a right-click context menu around the tab element. */
  contextMenu?: (children: ReactNode) => ReactElement;
  /** Icon to render in the close button. Defaults to X. */
  closeIcon?: ReactNode;
};

export type TabBarProps = {
  tabs: Array<TabDefinition>;
  openTabIds: Array<string>;
  activeTabId: string;
  onActivate: (tabId: string) => void;
  onClose: (tabId: string) => void;
  onReorder: (newOrder: Array<string>) => void;
  maxTabWidth?: number;
  children?: ReactNode;
  /** Content rendered at the far right of the tab bar, outside the scroll area. */
  rightContent?: ReactNode;
  /** CSS class for the outermost wrapper (only rendered when tabs have content). */
  className?: string;
  /** CSS class for the tab bar row element. */
  tabBarClassName?: string;
  /** Called when a tab is double-clicked. */
  onDoubleClick?: (tabId: string) => void;
  /** When true, every tab shows a close button even if it's the only one open. */
  alwaysCloseable?: boolean;
  /** Visual variant. "compact" uses rounded tabs with horizontal scroll. */
  variant?: TabVariant;
  /** If provided, each tab is wrapped in a Radix ContextMenu rendering this content. */
  contextMenuContent?: (tabId: string) => ReactNode;
  /** Changing this value forces the active tab to be scrolled into view. */
  scrollTrigger?: number;
};

export type DropIndicator = "left" | "right";

export type SortableTabProps = {
  tab: TabDefinition;
  isActive: boolean;
  isCloseable: boolean;
  isDragActive: boolean;
  width?: number;
  dropIndicator?: DropIndicator;
  onActivate: (tabId: string) => void;
  onClose: (tabId: string) => void;
  onDoubleClick?: (tabId: string) => void;
  /** Visual variant. "compact" uses rounded corners, compact padding. */
  variant?: TabVariant;
  contextMenuContent?: (tabId: string) => ReactNode;
};
