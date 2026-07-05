import type { FileDiffOptions } from "@pierre/diffs";
import { PatchDiff } from "@pierre/diffs/react";
import { IconButton, Tooltip } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { Check, CopyIcon, ExternalLink } from "lucide-react";
import type { KeyboardEvent, MutableRefObject, ReactElement } from "react";
import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { themeCodeThemeAtom } from "~/common/state/atoms/themeBuilder.ts";
import { appThemeAtom } from "~/common/state/atoms/userConfig.ts";
import { getShikiThemes } from "~/common/theme/shikiThemes.ts";
import { openDiffTabAtom, openFileViewTabAtom } from "~/pages/workspace/diffPanel/atoms.ts";
import { adoptPierreOverrideSheet, createPierreOverrideSheet } from "~/pages/workspace/diffPanel/pierreShadowStyles.ts";
import { usePierreHighlighterReady } from "~/pages/workspace/diffPanel/usePierreHighlighterReady.ts";
import { useWorkspaceCodePath } from "~/pages/workspace/hooks/useWorkspaceCodePath.ts";
import { isDiffToolContent } from "~/pages/workspace/utils/blockGuards.ts";

import styles from "./AlphaChipDiffPopover.module.scss";
import { useChatTask } from "./ChatTaskContext.tsx";
import type { ChipData } from "./chipRow.types.ts";
import { makeRelative } from "./toolPillUtils.ts";

export type ChipDiffPopoverActions = {
  openDiffPanel: () => void;
};

type AlphaChipDiffPopoverProps = {
  chipData: ChipData;
  onClose: () => void;
  onNavigate: (direction: "prev" | "next") => void;
  actionRef?: MutableRefObject<ChipDiffPopoverActions | null>;
};

/** How long the copy buttons show their "copied" check before reverting. */
const COPIED_INDICATOR_DURATION_MS = 1500;

/** Pixel size for the header action icons. */
const HEADER_ICON_SIZE = 14;

const splitFilePath = (filePath: string): { dir: string; base: string } => {
  const lastSlash = filePath.lastIndexOf("/");

  if (lastSlash < 0) return { dir: "", base: filePath };

  return { dir: filePath.slice(0, lastSlash), base: filePath.slice(lastSlash + 1) };
};

// The shared Pierre background override so the diff blends with the popover.
const bgOverrideSheet = createPierreOverrideSheet();

export const AlphaChipDiffPopover = ({
  chipData,
  onClose,
  onNavigate,
  actionRef,
}: AlphaChipDiffPopoverProps): ReactElement => {
  const { workspaceId: workspaceID } = useChatTask();
  const workspaceCodePath = useWorkspaceCodePath(workspaceID);
  const setOpenDiffTab = useSetAtom(openDiffTabAtom);
  const setOpenFileViewTab = useSetAtom(openFileViewTabAtom);
  const pierreRef = useRef<HTMLDivElement>(null);

  const appTheme = useAtomValue(appThemeAtom);
  const codeTheme = useAtomValue(themeCodeThemeAtom);
  const shikiThemes = getShikiThemes(codeTheme);
  // Pierre must not MOUNT before its shared highlighter has these themes
  // attached — a cold-themes first mount paints nothing and does not survive
  // React StrictMode's remount (see usePierreHighlighterReady), leaving the
  // first chip popover of a session permanently blank.
  const isHighlighterReady = usePierreHighlighterReady(shikiThemes);

  const pierreOptions = useMemo(
    (): FileDiffOptions<undefined> => ({
      diffStyle: "unified",
      overflow: "scroll",
      themeType: appTheme,
      theme: shikiThemes,
      diffIndicators: "bars",
      lineDiffType: "word-alt",
      expandUnchanged: false,
      disableFileHeader: true,
    }),
    [appTheme, shikiThemes],
  );

  const { dir, base } = splitFilePath(chipData.filePath);

  const diffPatches = useMemo(() => {
    return chipData.results
      .filter((r) => isDiffToolContent(r.content))
      .map((r) => (isDiffToolContent(r.content) ? r.content.diff : ""))
      .filter((d) => d.length > 0);
  }, [chipData.results]);

  // Inject the bg-override stylesheet into Pierre's shadow DOM (see
  // adoptPierreOverrideSheet for why this is a layout effect). Deps are
  // `diffPatches` because Pierre re-creates its shadow DOM whenever the patch
  // content changes, and the highlighter gate, which is when the container
  // first mounts.
  useLayoutEffect(() => {
    adoptPierreOverrideSheet(pierreRef.current, bgOverrideSheet);
  }, [diffPatches, isHighlighterReady]);

  const handleOpenDiffPanel = useCallback((): void => {
    // Files inside the workspace clone get a diff tab so the user can review
    // the change against HEAD. Files outside the clone — and plan files at
    // `.claude/plans/`, which are documents, not code changes — have no
    // useful diff context, so route them to a file-view tab that renders the
    // contents directly.
    const { display: pathRel, isOutsideWorkspace } = makeRelative(chipData.filePath, workspaceCodePath);
    // `.claude/plans/` always sits at the workspace root, so check the
    // relative path with `startsWith` rather than `includes` on the absolute
    // path — avoids misrouting an unrelated file whose name happens to
    // contain the substring.
    const isPlanFile = pathRel.startsWith(".claude/plans/");
    if (isOutsideWorkspace || isPlanFile) {
      setOpenFileViewTab({ workspaceId: workspaceID, filePath: chipData.filePath });
    } else {
      setOpenDiffTab({
        workspaceId: workspaceID,
        filePath: chipData.filePath,
        status: chipData.isNewFile ? "A" : "M",
      });
    }
    onClose();
  }, [
    workspaceID,
    workspaceCodePath,
    chipData.filePath,
    chipData.isNewFile,
    setOpenDiffTab,
    setOpenFileViewTab,
    onClose,
  ]);

  // Expose actions to the parent via ref so it can trigger them from its own key handler.
  useEffect(() => {
    if (!actionRef) return;
    actionRef.current = { openDiffPanel: handleOpenDiffPanel };
    return (): void => {
      actionRef.current = null;
    };
  }, [actionRef, handleOpenDiffPanel]);

  // Only one of the path/error buttons is visible at a time, so a single
  // discriminator captures which (if any) is in its post-copy "Check" state.
  const [copiedKey, setCopiedKey] = useState<"path" | "error" | null>(null);
  const copyTimerRef = useRef<ReturnType<typeof setTimeout>>(undefined);
  useEffect(() => (): void => clearTimeout(copyTimerRef.current), []);

  const flashCopied = useCallback((key: "path" | "error"): void => {
    setCopiedKey(key);
    clearTimeout(copyTimerRef.current);
    copyTimerRef.current = setTimeout(() => setCopiedKey(null), COPIED_INDICATOR_DURATION_MS);
  }, []);

  const handleCopyPath = useCallback((): void => {
    if (!chipData.filePath) return;
    navigator.clipboard.writeText(chipData.filePath).catch(() => {});
    flashCopied("path");
  }, [chipData.filePath, flashCopied]);

  const handleCopyError = useCallback((): void => {
    navigator.clipboard.writeText(chipData.errorDetail ?? "").catch(() => {});
    flashCopied("error");
  }, [chipData.errorDetail, flashCopied]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        onNavigate("prev");
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        onNavigate("next");
      } else if (e.key === "Enter" && e.shiftKey) {
        e.preventDefault();
        handleOpenDiffPanel();
      }
    },
    [onNavigate, handleOpenDiffPanel],
  );

  const headerClass = [styles.header];

  if (chipData.state === "error") headerClass.push(styles.headerError);

  return (
    <div className={styles.popover} data-testid={ElementIds.ALPHA_CHAT_CHIP_POPOVER} onKeyDown={handleKeyDown}>
      <div className={headerClass.join(" ")}>
        <div className={styles.headerLeft}>
          {chipData.state === "completed" && chipData.isNewFile && (
            <span className={styles.newFileBadge}>new file</span>
          )}
          {chipData.state === "error" && <span className={styles.failedLabel}>Failed</span>}
          <span className={styles.filePath}>
            {dir && <span className={styles.filePathDir}>{dir}</span>}
            {dir && <span className={styles.filePathSep}>/</span>}
            <span className={styles.filePathBase}>{base}</span>
          </span>
        </div>
        <div className={styles.headerRight}>
          {chipData.state === "completed" && (
            <div className={styles.headerActions}>
              <Tooltip content="Copy file path">
                <IconButton
                  variant="ghost"
                  size="1"
                  className={styles.headerActionButton}
                  onClick={handleCopyPath}
                  aria-label="Copy file path"
                >
                  {copiedKey === "path" ? <Check size={HEADER_ICON_SIZE} /> : <CopyIcon size={HEADER_ICON_SIZE} />}
                </IconButton>
              </Tooltip>
              <Tooltip content="View full diff">
                <IconButton
                  variant="ghost"
                  size="1"
                  className={styles.headerActionButton}
                  onClick={handleOpenDiffPanel}
                  aria-label="View full diff"
                  data-testid={ElementIds.ALPHA_CHAT_CHIP_VIEW_FULL_DIFF_BTN}
                >
                  <ExternalLink size={HEADER_ICON_SIZE} />
                </IconButton>
              </Tooltip>
            </div>
          )}
          {chipData.state === "error" && (
            <div className={styles.headerActions}>
              <Tooltip content="Copy error">
                <IconButton
                  variant="ghost"
                  size="1"
                  className={styles.headerActionButton}
                  onClick={handleCopyError}
                  aria-label="Copy error"
                >
                  {copiedKey === "error" ? <Check size={HEADER_ICON_SIZE} /> : <CopyIcon size={HEADER_ICON_SIZE} />}
                </IconButton>
              </Tooltip>
            </div>
          )}
        </div>
      </div>

      <div className={styles.body}>
        {chipData.state === "completed" && diffPatches.length > 0 && (
          <div ref={pierreRef}>
            {isHighlighterReady &&
              diffPatches.map((patch, i) => <PatchDiff key={i} patch={patch} options={pierreOptions} />)}
          </div>
        )}
        {chipData.state === "error" && (
          <div className={chipData.errorContentType === "diff" ? styles.body : styles.bodyError}>
            {chipData.errorContentType === "diff" && chipData.errorDetail ? (
              <div ref={pierreRef}>
                {isHighlighterReady && <PatchDiff patch={chipData.errorDetail} options={pierreOptions} />}
              </div>
            ) : chipData.errorDetail ? (
              <pre className={styles.errorDetail}>{chipData.errorDetail}</pre>
            ) : (
              <div className={styles.errorFallback}>No error details available</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
