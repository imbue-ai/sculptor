import { useAtom, useAtomValue } from "jotai";
import { ChevronDown, GitMerge, Layers, Plus } from "lucide-react";
import type { ReactElement } from "react";
import { useEffect, useMemo, useRef, useState } from "react";

import type { PrStatusInfo } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useGitAndOpenInRuntime } from "~/components/CommandPalette/contextActions/useGitAndOpenInRuntime.ts";
import { DiffScopePicker } from "~/pages/workspace/components/diffPanel/DiffScopePicker.tsx";
import type { DiffScope } from "~/pages/workspace/components/diffPanel/types.ts";
import { changesScopeAtomFamily } from "~/pages/workspace/panels/fileBrowser/atoms.ts";
import { FlatListRow } from "~/pages/workspace/panels/fileBrowser/FlatListRow.tsx";
import { useFileStatusMap, useFileTree, usePerFileDiffMap } from "~/pages/workspace/panels/fileBrowser/hooks.ts";
import { getChangedFiles } from "~/pages/workspace/panels/fileBrowser/utils.ts";

import styles from "./ChangesPill.module.scss";

type ChangesPillProps = {
  onReviewAll: () => void;
};

// Slack (px) the bar must regain before "· N files" comes back, so the label
// doesn't flicker on/off around the exact overlap point.
const RESTORE_MARGIN = 12;

const pipelineDotClass = (status: PrStatusInfo["pipelineStatus"]): string => {
  if (status === "running") return styles.dotRunning;
  if (status === "passed") return styles.dotPassed;
  if (status === "failed") return styles.dotFailed;
  return styles.dotMuted;
};

const reviewDotClass = (prStatus: PrStatusInfo): string => {
  const approvals = prStatus.approvals;
  if (!approvals || approvals.length === 0) return styles.dotMuted;
  return approvals.every((a) => a.approved) ? styles.dotApproved : styles.dotPending;
};

/**
 * ChangesPill (C1-C3) — the right-hand pill of the header status row (the agent
 * switcher sits on its left). Styled to match the chat's StatusPill /
 * JumpToBottom indicators (gray-1 surface, gray-4 hairline, radius-2, shadow-sm).
 * The left segment is the PR control (create / open / merged, mirroring the
 * desktop PrButton but without its split-button popover); the right segment is
 * the `+X −Y · N files` summary. When the two pills would overlap, the "· N
 * files" suffix is dropped first (the agent name truncates independently).
 * Tapping the summary floats a flat file list over the chat — the real
 * `FlatListRow` plus an All / Uncommitted toggle (`DiffScopePicker`) — and a
 * subtle "Review all changes" affordance opens the review-all overlay (C3).
 *
 * The expanded panel is positioned against the shell's `.statusRow` (its
 * positioned ancestor) so it spans the row width rather than the narrow bar.
 */
export const ChangesPill = ({ onReviewAll }: ChangesPillProps): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();
  const workspace = useWorkspace(workspaceID);
  const git = useGitAndOpenInRuntime();
  const prStatus = useAtomValue(prStatusAtomFamily(workspaceID));
  const [isOpen, setIsOpen] = useState(false);
  const [scope, setScope] = useAtom(changesScopeAtomFamily(workspaceID));

  const wrapRef = useRef<HTMLDivElement>(null);
  const filesWidthRef = useRef(0);
  const [shouldDropFiles, setShouldDropFiles] = useState(false);

  const hasTargetBranch = workspace?.targetBranch != null;
  const uncommittedMap = useFileStatusMap(workspaceID, "uncommitted");
  const allMap = useFileStatusMap(workspaceID, "vs-target-branch");
  // Mirror DiffScopePicker: fall back to uncommitted when there's no target
  // branch, so the bar's summary and list agree with the (forced) toggle.
  const effectiveScope: DiffScope = !hasTargetBranch && scope === "vs-target-branch" ? "uncommitted" : scope;

  const { tree } = useFileTree(workspaceID, effectiveScope);
  const perFileDiffMap = usePerFileDiffMap(workspaceID, effectiveScope);
  const files = useMemo(() => getChangedFiles(tree), [tree]);

  const summary = useMemo(() => {
    let added = 0;
    let removed = 0;
    for (const fileDiff of perFileDiffMap.values()) {
      added += fileDiff.addedLines;
      removed += fileDiff.removedLines;
    }
    return { added, removed, filesChanged: perFileDiffMap.size };
  }, [perFileDiffMap]);

  // Show the bar whenever either scope has changes (so the toggle is reachable
  // even if the selected scope is empty), or there's an open PR to surface.
  const isVisible = uncommittedMap.size > 0 || allMap.size > 0 || prStatus?.prState === "open";

  // Drop the "· N files" suffix when the bar would otherwise overlap the agent
  // switcher. The decision uses widths that don't depend on `shouldDropFiles` (the row
  // and agent are sized independently of this bar), so it converges without
  // oscillating; `RESTORE_MARGIN` adds hysteresis around the threshold.
  useEffect(() => {
    if (!isVisible || typeof ResizeObserver === "undefined") return;
    const wrap = wrapRef.current;
    const row = wrap?.parentElement ?? null;
    if (!wrap || !row) return;

    const measure = (): void => {
      const agent = wrap.previousElementSibling as HTMLElement | null;
      const rowStyle = getComputedStyle(row);
      const padX = (parseFloat(rowStyle.paddingLeft) || 0) + (parseFloat(rowStyle.paddingRight) || 0);
      const gap = parseFloat(rowStyle.columnGap || rowStyle.gap || "0") || 0;
      const available = row.clientWidth - padX - (agent?.offsetWidth ?? 0) - gap;
      const filesEl = wrap.querySelector<HTMLElement>("[data-files]");
      // Cache the suffix width whenever it's on screen; reuse it while hidden so
      // the bar's "full" width (with files) stays a stable reference.
      if (filesEl) filesWidthRef.current = filesEl.getBoundingClientRect().width;
      const fullWidth = wrap.offsetWidth + (filesEl ? 0 : filesWidthRef.current);
      setShouldDropFiles((prev) => {
        if (fullWidth > available) return true;
        if (fullWidth + RESTORE_MARGIN <= available) return false;
        return prev;
      });
    };

    const observer = new ResizeObserver(measure);
    observer.observe(row);
    const agent = wrap.previousElementSibling;
    if (agent) observer.observe(agent);
    measure();
    return (): void => observer.disconnect();
  }, [isVisible, summary.added, summary.removed, summary.filesChanged]);

  if (!isVisible) return null;

  // GitHub is the only supported provider now (GitProvider is "github" | null),
  // matching the GitHub-only desktop PR button, so the labels are fixed.
  const prTerm = "PR";
  const prPrefix = "#";

  const openPrUrl = (): void => {
    if (prStatus?.prWebUrl) window.open(prStatus.prWebUrl, "_blank", "noopener,noreferrer");
  };

  const renderPrControl = (): ReactElement | null => {
    if (prStatus?.prState === "open") {
      return (
        <button
          type="button"
          className={`${styles.pr} ${styles.prRef}`}
          onClick={openPrUrl}
          title={`Open ${prTerm} ${prPrefix}${prStatus.prIid}`}
        >
          {prTerm} {prPrefix}
          {prStatus.prIid}
          <span className={`${styles.dot} ${pipelineDotClass(prStatus.pipelineStatus)}`} />
          <span className={`${styles.dot} ${reviewDotClass(prStatus)}`} />
        </button>
      );
    }

    if (prStatus?.prState === "merged" || prStatus?.prState === "closed") {
      const isMerged = prStatus.prState === "merged";
      return (
        <button
          type="button"
          className={`${styles.pr} ${styles.prRef} ${styles.prMerged}`}
          onClick={openPrUrl}
          title={`Open ${prTerm} ${prPrefix}${prStatus.prIid}`}
        >
          <GitMerge size={13} className={isMerged ? styles.mergeIcon : undefined} />
          {prTerm} {prPrefix}
          {prStatus.prIid}
          <span className={isMerged ? styles.mergedLabel : styles.closedLabel}>{prStatus.prState}</span>
        </button>
      );
    }
    if (!workspace) return null;
    return (
      <button type="button" className={styles.pr} onClick={() => git.createMergeRequest(workspace)}>
        <Plus size={14} /> {prTerm}
      </button>
    );
  };

  return (
    <div ref={wrapRef} className={`${styles.wrap} ${isOpen ? styles.open : ""}`}>
      <div className={styles.bar}>
        {renderPrControl()}
        <button type="button" className={styles.changes} onClick={() => setIsOpen((v) => !v)} aria-expanded={isOpen}>
          <span className={styles.stat}>
            <span className={styles.add}>+{summary.added}</span> <span className={styles.del}>−{summary.removed}</span>
            {shouldDropFiles ? null : (
              <span className={styles.files} data-files>
                {" "}
                · {summary.filesChanged} {summary.filesChanged === 1 ? "file" : "files"}
              </span>
            )}
          </span>
          <span className={styles.chevron}>
            <ChevronDown size={14} />
          </span>
        </button>
      </div>

      <div className={styles.panel}>
        <div className={styles.scopeRow}>
          <DiffScopePicker
            scope={scope}
            onScopeChange={setScope}
            hasTargetBranch={hasTargetBranch}
            uncommittedCount={uncommittedMap.size}
            allCount={allMap.size}
          />
        </div>
        <div className={styles.list}>
          {files.map((entry) => {
            const fileDiff = perFileDiffMap.get(entry.path);
            return (
              <FlatListRow
                key={entry.path}
                entry={entry}
                isFocused={false}
                addedLines={fileDiff?.addedLines}
                removedLines={fileDiff?.removedLines}
                onFileClick={onReviewAll}
              />
            );
          })}
        </div>
        <div className={styles.reviewFoot}>
          <button type="button" className={styles.reviewButton} onClick={onReviewAll}>
            <Layers size={15} /> Review all changes
          </button>
        </div>
      </div>
    </div>
  );
};
