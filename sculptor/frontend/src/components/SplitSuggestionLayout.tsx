import type { SuggestionProps } from "@tiptap/suggestion";
import type { ReactElement, ReactNode } from "react";
import { forwardRef } from "react";

import type { SuggestionListRef } from "./SuggestionListContainer";
import { SuggestionListContainer } from "./SuggestionListContainer";

type SuggestionItemShape = {
  id: string;
  label: string;
  isSectionHeader?: boolean;
  isFirstInList?: boolean;
  [key: string]: unknown;
};

export type SplitSuggestionLayoutProps = {
  props: SuggestionProps;
  rowHeight: number;
  sectionHeaderHeight?: number;
  firstSectionHeaderHeight?: number;
  className?: string;
  emptyState: ReactNode;
  renderItem: (item: { id: string; label: string; [key: string]: unknown }) => ReactNode;
  itemTestId?: string;
  beforeList?: ReactNode;
  footer?: ReactNode;
  onStepBack?: () => boolean;
  // Right-hand pane render prop. Required — the whole point of this
  // component is to host a detail view beside the list.
  sideContent: (activeItem: SuggestionItemShape | undefined) => ReactNode;
  // Mouse-driven selection updates are the norm when a side pane is shown;
  // default to true so hover and keyboard drive the same "active" state.
  followHover?: boolean;
};

/**
 * Split-pane variant of the suggestion popover: scrollable item list on the
 * left, caller-supplied detail view on the right, keyed on the active row.
 *
 * Used by any suggestion picker that wants to surface rich per-item detail
 * beyond what fits on a single row — currently the `/`-skill picker and the
 * `+`-entity picker. The simpler list-plus-footer shape (file picker) keeps
 * using `SuggestionListContainer` directly.
 */
export const SplitSuggestionLayout = forwardRef<SuggestionListRef, SplitSuggestionLayoutProps>(
  ({ followHover = true, ...rest }, ref): ReactElement => (
    <SuggestionListContainer ref={ref} followHover={followHover} {...rest} />
  ),
);
