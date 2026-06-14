import { ChevronDown, GitCompare, Layers } from "lucide-react";
import type { ReactElement } from "react";
import { useState } from "react";

import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";

import styles from "./ChangesPill.module.scss";
import { useMobileChangeSummary } from "./useMobileChangeSummary.ts";

type ChangesPillProps = {
  onReviewAll: () => void;
};

/**
 * ChangesPill (C1-C3) — a compact pill under the header summarising
 * `+X −Y · N files`, shown only when there are changes (C1). Tapping it expands
 * a floating file list that overlays the chat (the chat + input stay put, C2);
 * "Review all changes" opens the review-all overlay (C3).
 */
export const ChangesPill = ({ onReviewAll }: ChangesPillProps): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const summary = useMobileChangeSummary(workspaceID);
  const [isOpen, setIsOpen] = useState(false);

  if (!summary.hasChanges) return null;

  return (
    <div className={`${styles.pill} ${isOpen ? styles.open : ""}`}>
      <button type="button" className={styles.top} onClick={() => setIsOpen((v) => !v)} aria-expanded={isOpen}>
        <span className={styles.gitIcon}>
          <GitCompare size={18} />
        </span>
        <span className={styles.label}>Changes</span>
        <span className={styles.stat}>
          <span className={styles.add}>+{summary.added}</span> <span className={styles.del}>−{summary.removed}</span> ·{" "}
          {summary.filesChanged} {summary.filesChanged === 1 ? "file" : "files"}
        </span>
        <span className={styles.chevron}>
          <ChevronDown size={18} />
        </span>
      </button>

      <div className={styles.body}>
        {summary.files.map((file, i) => (
          <button
            type="button"
            key={`${file.dirPath}${file.fileName}-${i}`}
            className={styles.fileRow}
            onClick={onReviewAll}
          >
            <span className={`${styles.status} ${styles[`status${file.status}`]}`}>{file.status}</span>
            <span className={styles.fileInfo}>
              <span className={styles.fileName}>{file.fileName}</span>
              {file.dirPath ? <span className={styles.filePath}>{file.dirPath}</span> : null}
            </span>
            <span className={styles.fileStat}>
              {file.added > 0 ? <span className={styles.add}>+{file.added}</span> : null}
              {file.removed > 0 ? <span className={styles.del}>−{file.removed}</span> : null}
            </span>
          </button>
        ))}
        <div className={styles.reviewRow}>
          <button type="button" className={styles.reviewButton} onClick={onReviewAll}>
            <Layers size={18} /> Review all changes
          </button>
        </div>
      </div>
    </div>
  );
};
