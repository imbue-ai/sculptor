// The section body's loading placeholder: a few skeleton lines shown while a
// placed panel is still resolving because the agent/task snapshot hasn't arrived
// yet (see isSubSectionPanelLoadingAtom). Deliberately panel-agnostic — a chat,
// terminal, and diff panel all read as "content on its way" behind these lines —
// rather than mimicking one panel's chrome.

import { Skeleton } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./SectionLoadingState.module.scss";

// Uneven widths so the block reads as loading content, not a filled rectangle.
const LINE_WIDTHS: ReadonlyArray<string> = ["58%", "82%", "70%", "46%", "76%", "62%"];

export const SectionLoadingState = (): ReactElement => {
  return (
    <div className={styles.loading} aria-hidden="true" data-testid={ElementIds.SECTION_LOADING_STATE}>
      {LINE_WIDTHS.map((width, index) => (
        <Skeleton key={index} className={styles.line} style={{ width }} />
      ))}
    </div>
  );
};
