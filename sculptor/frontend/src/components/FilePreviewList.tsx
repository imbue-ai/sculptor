import { Flex } from "@radix-ui/themes";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds } from "~/api";
import { baseUrl } from "~/apiClient.ts";
import { setupAuthHeaders } from "~/common/Auth.ts";

import { useAgentLightbox } from "./AgentLightboxContext.tsx";
import { FilePreview } from "./FilePreview.tsx";
import { ImageLightbox } from "./ImageLightbox.tsx";

type FilePreviewListProps = {
  files: Array<string>;
  onRemoveFile?: (filePath: string) => void;
  displayMode?: "compact" | "inline" | "full";
  /** Stable ID for this list in the agent lightbox registry. When provided along with an AgentLightboxProvider, enables cross-message navigation. */
  listId?: string;
  /** Numeric order used to sort this list's images in the shared lightbox. Lower values appear first. */
  listOrder?: number;
  /** When true, image previews get a right-click "Copy Image" context menu. */
  allowCopyImage?: boolean;
};

const isPdfFile = (filePath: string): boolean => {
  return filePath.toLowerCase().endsWith(".pdf");
};

const VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov"];

const isVideoFile = (filePath: string): boolean => {
  const lower = filePath.toLowerCase();
  return VIDEO_EXTENSIONS.some((ext) => lower.endsWith(ext));
};

const getFileName = (filePath: string): string => {
  const parts = filePath.split(/[/\\]/);
  return parts[parts.length - 1] || filePath;
};

// New uploads are referenced by a bare upload id (served over HTTP). Legacy
// desktop attachments were saved by the (now-removed) Electron `saveFile` IPC
// handler and are referenced by an absolute path — Unix (`/…`) or Windows
// (`C:\…`). Those are read via the retained `getFileData` IPC handler.
const isLegacyAbsolutePath = (filePath: string): boolean =>
  filePath.startsWith("/") || /^[a-zA-Z]:[\\/]/.test(filePath);

export const FilePreviewList = ({
  files,
  onRemoveFile,
  displayMode = "compact",
  listId,
  listOrder = 0,
  allowCopyImage = false,
}: FilePreviewListProps): ReactElement | undefined => {
  const agentLightbox = useAgentLightbox();
  const [filesUrls, setFilesUrls] = useState<Record<string, string>>({});
  const [failedFiles, setFailedFiles] = useState<Set<string>>(new Set());
  const [localLightboxIndex, setLocalLightboxIndex] = useState<number | null>(null);
  const prevFilesRef = useRef<Array<string>>([]);
  const handleCloseLocalLightbox = useCallback((): void => setLocalLightboxIndex(null), []);

  const validFiles = useMemo(() => files.filter((f): f is string => f != null), [files]);

  const lightboxMedia = useMemo(
    () =>
      validFiles
        .filter((f) => !isPdfFile(f) && !failedFiles.has(f) && filesUrls[f] != null)
        .map((f) => ({ url: filesUrls[f], name: getFileName(f), path: f, isVideo: isVideoFile(f) })),
    [validFiles, failedFiles, filesUrls],
  );

  // Register media with the agent-level lightbox context when a stable listId is provided.
  // We intentionally do NOT unregister on unmount so that images remain accessible
  // even when this list is virtualized off-screen.
  useEffect(() => {
    if (!agentLightbox || !listId || lightboxMedia.length === 0) return;
    agentLightbox.registerMedia(listId, listOrder, lightboxMedia);
  }, [agentLightbox, listId, listOrder, lightboxMedia]);

  // Load new files and clean up removed files incrementally
  useEffect(() => {
    const prevFiles = new Set(prevFilesRef.current);
    const currentFiles = new Set(validFiles);
    prevFilesRef.current = validFiles;

    // Clean up state for removed files
    const removedFiles = [...prevFiles].filter((f) => !currentFiles.has(f));
    if (removedFiles.length > 0) {
      setFilesUrls((prev) => {
        const next = { ...prev };
        for (const f of removedFiles) {
          delete next[f];
        }
        return next;
      });
      setFailedFiles((prev) => {
        const next = new Set(prev);
        for (const f of removedFiles) {
          next.delete(f);
        }
        return next;
      });
    }

    // Load only new files
    const newFiles = validFiles.filter((f) => !prevFiles.has(f));
    if (newFiles.length === 0) return;

    let isCancelled = false;

    const loadNewFiles = async (): Promise<void> => {
      const urlPromises = newFiles.map(async (filePath): Promise<{ url: string; filePath: string } | undefined> => {
        try {
          if (isLegacyAbsolutePath(filePath)) {
            // Legacy desktop attachment saved to disk; read it back over IPC.
            if (!window.sculptor?.getFileData) return undefined;
            const base64Data = await window.sculptor.getFileData(filePath);
            return { url: base64Data, filePath };
          }
          // Uploaded to the backend: fetch via the API download endpoint by id.
          const headers = new Headers();
          setupAuthHeaders(headers);
          const resp = await fetch(`${baseUrl}/api/v1/uploaded-file/${encodeURIComponent(filePath)}`, { headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          const blob = await resp.blob();
          return { url: URL.createObjectURL(blob), filePath };
        } catch (error) {
          console.error("Failed to load file:", filePath, error);
          if (!isCancelled) {
            setFailedFiles((prev) => new Set(prev).add(filePath));
          }
          return undefined;
        }
      });

      const urls = await Promise.all(urlPromises);
      const validUrls = urls.filter((item): item is { url: string; filePath: string } => item != null);

      if (validUrls.length > 0) {
        setFilesUrls((prev) => {
          const next = { ...prev };
          for (const { filePath, url } of validUrls) {
            next[filePath] = url;
          }
          return next;
        });
      }
    };

    loadNewFiles();
    return (): void => {
      isCancelled = true;
    };
  }, [validFiles]);

  if (validFiles.length === 0) {
    return undefined;
  }

  const isInline = displayMode === "inline";
  const isFull = displayMode === "full";
  const isSharedLightbox = agentLightbox != null && listId != null;

  return (
    <>
      <Flex
        direction={isFull ? "column" : "row"}
        gap={isFull ? "3" : "1"}
        wrap="nowrap"
        style={{ overflowX: isFull ? undefined : "auto", padding: isFull ? 0 : isInline ? "4px 0" : "8px 8px 4px" }}
        data-testid={ElementIds.FILE_PREVIEW_LIST}
      >
        {validFiles.map((filePath) => {
          const fileUrl = filesUrls[filePath];
          const isFailed = failedFiles.has(filePath);
          const isPdf = isPdfFile(filePath);
          const isVideo = isVideoFile(filePath);
          const fileName = getFileName(filePath);

          return (
            <FilePreview
              key={filePath}
              filePath={filePath}
              fileUrl={fileUrl}
              isFailed={isFailed}
              isPdf={isPdf}
              isVideo={isVideo}
              fileName={fileName}
              displayMode={displayMode}
              allowCopyImage={allowCopyImage}
              onRemove={onRemoveFile ? (): void => onRemoveFile(filePath) : undefined}
              onError={(): void => {
                setFailedFiles((prev) => new Set(prev).add(filePath));
              }}
              onClick={
                fileUrl && !isFailed && !isPdfFile(filePath)
                  ? (): void => {
                      if (isSharedLightbox) {
                        agentLightbox.openLightbox(filePath);
                      } else {
                        const index = lightboxMedia.findIndex((item) => item.path === filePath);
                        if (index >= 0) setLocalLightboxIndex(index);
                      }
                    }
                  : undefined
              }
            />
          );
        })}
      </Flex>
      {!isSharedLightbox && localLightboxIndex != null && lightboxMedia.length > 0 && (
        <ImageLightbox media={lightboxMedia} initialIndex={localLightboxIndex} onClose={handleCloseLocalLightbox} />
      )}
    </>
  );
};
