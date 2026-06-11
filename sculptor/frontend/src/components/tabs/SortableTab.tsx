import { useSortable } from "@dnd-kit/sortable";
import type { ReactElement } from "react";

import { SortableTabContent } from "~/components/tabs/SortableTabContent";
import type { SortableTabProps } from "~/components/tabs/types";

/**
 * Thin wrapper owning only the `useSortable` hook. dnd-kit re-renders every
 * hook consumer on drag-context changes — the dragged tab on every pointer
 * move, all tabs on every `over` change — so this component must do no work
 * itself: it re-runs the hook and re-renders the memoized SortableTabContent,
 * which bails out unless its (identity-stable for idle tabs) props changed.
 */
export const SortableTab = (props: SortableTabProps): ReactElement => {
  const { attributes, listeners, setNodeRef, isDragging } = useSortable({ id: props.tab.id });

  return (
    <SortableTabContent
      {...props}
      attributes={attributes}
      listeners={listeners}
      setNodeRef={setNodeRef}
      isDragging={isDragging}
    />
  );
};
