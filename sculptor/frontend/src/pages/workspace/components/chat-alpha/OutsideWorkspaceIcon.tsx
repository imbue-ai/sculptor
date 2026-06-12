import { Tooltip } from "@radix-ui/themes";
import { FolderOutput } from "lucide-react";
import type { ReactElement } from "react";

import styles from "./OutsideWorkspaceIcon.module.scss";

const LABEL = "Path outside of the workspace";

/** Indicator icon shown next to a tool-call path that lives outside the workspace. */
export const OutsideWorkspaceIcon = (): ReactElement => (
  <Tooltip content={LABEL}>
    <span className={styles.icon}>
      <FolderOutput size={12} aria-label={LABEL} />
    </span>
  </Tooltip>
);
