import type { ReactElement, ReactNode } from "react";

export type TabVariant = "default" | "compact";

// Where the drag-and-drop context lives. "owned" (default): the TabBar renders
// its own DndContext and handles within-strip reorder itself. "shared": the
// TabBar renders only the SortableContext and assumes an ancestor DndContext
// (e.g. the compact layout's PanelDndProvider) drives reorder and cross-section
// moves — so a tab can be dragged out of this strip into another section.
export type TabDndMode = "owned" | "shared";

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
  /** Display string for this panel's focus shortcut (e.g. "⌘P"), shown as a
   *  small badge on the active tab so the keybinding is discoverable. */
  shortcut?: string;
  /** Custom data-testid applied to the tab element. */
  dataTestId?: string;
  /** Custom data-* attributes applied to the tab element (keys without the "data-" prefix). */
  dataAttributes?: Record<string, string>;
  /** Wrapper that adds a right-click context menu around the tab element. */
  contextMenu?: (children: ReactNode) => ReactElement;
  /** Icon to render in the close button. Defaults to X. */
  closeIcon?: ReactNode;
  /** Per-tab override for whether the close affordance is shown. Defaults to the
   *  TabBar-level closeable state. Set false to hide the close button on a tab
   *  that cannot be closed (e.g. the only/active agent). */
  closeable?: boolean;
};

export type TabBarProps = {
  tabs: Array<TabDefinition>;
  openTabIds: Array<string>;
  activeTabId: string;
  onActivate: (tabId: string) => void;
  onClose: (tabId: string) => void;
  /** Called on within-strip reorder. Optional: in "shared" dndMode an ancestor
   *  DndContext drives reordering instead, so this is never called. */
  onReorder?: (newOrder: Array<string>) => void;
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
  /** On hover, replace the tab's leading icon with the close (X) button instead
   *  of showing a separate trailing close button. */
  closeReplacesIcon?: boolean;
  /** Drag-and-drop ownership. Defaults to "owned" (self-contained DndContext). */
  dndMode?: TabDndMode;
  /** In "shared" dndMode, signals that a drag is in flight in the ancestor
   *  context so hover affordances are suppressed (the local drag state, which
   *  drives this in "owned" mode, is never set in "shared" mode). */
  externalDragActive?: boolean;
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
  /** On hover, replace the leading icon with the close button. */
  closeReplacesIcon?: boolean;
  /** When dragging this tab, render it as a ghosted full-size placeholder in the
   *  gap (the floating copy is shown via the ancestor's DragOverlay). Used in
   *  "shared" dndMode so the tab previews where it will land across sections. */
  ghostWhenDragging?: boolean;
};
