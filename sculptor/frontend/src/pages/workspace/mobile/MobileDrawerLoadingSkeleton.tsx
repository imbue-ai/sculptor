import { Skeleton } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";

import styles from "./MobileDrawerLoadingSkeleton.module.scss";

// A couple of placeholder repo groups of uneven shape (varied header and row
// widths, different row counts) so the skeleton reads as content-in-progress
// rather than a uniform block. Purely decorative — the real list replaces it the
// instant the first snapshot lands.
const PLACEHOLDER_GROUPS: ReadonlyArray<{ headerWidth: string; rowWidths: ReadonlyArray<string> }> = [
  { headerWidth: "52%", rowWidths: ["74%", "60%", "68%"] },
  { headerWidth: "40%", rowWidths: ["66%", "54%"] },
];

/**
 * Placeholder skeleton for the mobile drawer's repo list, shown while the first
 * workspace snapshot is still in flight (see `isSidebarLoadingAtom`). Mirrors the
 * desktop `SidebarLoadingSkeleton`: without it, the drawer collapses the
 * not-yet-loaded state into "empty" and flashes the "No workspaces yet" empty
 * state on a cold load.
 *
 * Its bars mirror the real repo-header + workspace-row geometry so the list
 * doesn't reflow when the data arrives. The whole group fades in after a short
 * delay (see the stylesheet) so a fast reconnect never flashes a skeleton — only
 * a slow/cold backend surfaces it. `aria-hidden` keeps the decorative bars out of
 * the accessibility tree.
 */
export const MobileDrawerLoadingSkeleton = (): ReactElement => {
  return (
    <div className={styles.skeleton} aria-hidden="true" data-testid={ElementIds.MOBILE_DRAWER_LOADING_SKELETON}>
      {PLACEHOLDER_GROUPS.map((group, groupIndex) => (
        <div key={groupIndex} className={styles.group}>
          <div className={styles.header}>
            <Skeleton className={styles.chevron} />
            <Skeleton className={styles.bar} style={{ width: group.headerWidth }} />
          </div>
          {group.rowWidths.map((rowWidth, rowIndex) => (
            <div key={rowIndex} className={styles.row}>
              <Skeleton className={styles.dot} />
              <Skeleton className={styles.bar} style={{ width: rowWidth }} />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
};
