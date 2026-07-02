import type { ReactElement, ReactNode } from "react";

import type { ToolResultBlock, ToolUseBlock } from "~/api";

import styles from "./AlphaToolPopover.module.scss";
import { PopoverHeader } from "./PopoverHeader.tsx";

export type ToolEntryShellArgs = {
  title: ReactNode;
  meta?: ReactNode;
  actions?: ReactNode;
  /** Body text. The popover shell renders this as <pre>; the row shell ignores it. */
  bodyText: string;
  /** Extra className for the body — e.g. terminal background or error tint. */
  bodyClassName?: string;
  /** Custom body node. Preferred over bodyText in the popover shell; the row shell ignores it. */
  body?: ReactNode;
};

/**
 * Render-prop callback that decides how a per-tool entry is laid out.
 * Used by the popover (default) to render header + body, and by the
 * expanded row mode to inline header content next to the tool icon.
 */
export type ToolEntryShell = (args: ToolEntryShellArgs) => ReactElement;

export type ToolEntryProps = {
  block: ToolUseBlock | null;
  result: ToolResultBlock | null;
  workspaceCodePath: string | null;
  /** Defaults to the popover-entry layout (header + body). */
  renderShell?: ToolEntryShell;
};

export const defaultPopoverShell: ToolEntryShell = ({ title, meta, actions, bodyText, bodyClassName, body }) => (
  <div className={styles.entry}>
    <PopoverHeader title={title} meta={meta} actions={actions} />
    {body ?? (bodyText && <pre className={bodyClassName ?? styles.entryBody}>{bodyText}</pre>)}
  </div>
);
