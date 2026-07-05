import { Button, Flex, Text } from "@radix-ui/themes";
import { ExternalLink, File as FileIcon, FolderOpen } from "lucide-react";
import type { ReactElement } from "react";
import { useCallback, useMemo, useRef, useState } from "react";

import { getBackendCapabilities } from "~/common/state/atoms/backendCapabilities.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import type { WorkspaceFilePayload } from "~/common/state/hooks/useWorkspaceFileContent.ts";
import { useWorkspaceFilePayload } from "~/common/state/hooks/useWorkspaceFileContent.ts";
import { isSupportedImageFormat } from "~/pages/workspace/panels/fileBrowser/utils/fileType.ts";

import { openInOs } from "../panels/fileBrowser/openInOs.ts";
import styles from "./BinaryPreview.module.scss";

const IMAGE_MIME_TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  gif: "image/gif",
  webp: "image/webp",
  svg: "image/svg+xml",
};

const MIN_ZOOM = 0.1;
const MAX_ZOOM = 10;
const ZOOM_STEP = 0.1;

const getExtension = (filePath: string): string => {
  const lastDot = filePath.lastIndexOf(".");
  if (lastDot === -1) return "";
  return filePath.slice(lastDot + 1).toLowerCase();
};

const getMimeType = (filePath: string): string => {
  const ext = getExtension(filePath);
  return IMAGE_MIME_TYPES[ext] ?? "application/octet-stream";
};

const formatFileSize = (bytes: number): string => {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
};

type ImageData = {
  dataUrl: string;
  sizeBytes: number;
};

type ImageDimensions = {
  width: number;
  height: number;
};

const payloadToImageData = (payload: WorkspaceFilePayload, filePath: string): ImageData => {
  const { content } = payload;
  const mimeType = getMimeType(filePath);
  const isBase64 = payload.encoding === "base64";
  const dataUrl = isBase64 ? `data:${mimeType};base64,${content}` : `data:${mimeType};base64,${btoa(content)}`;
  const sizeBytes = isBase64 ? Math.round((content.length * 3) / 4) : content.length;
  return { dataUrl, sizeBytes };
};

const useImageData = (workspaceId: string, filePath: string): ImageData | null => {
  const { data: payload } = useWorkspaceFilePayload(workspaceId, filePath, null);
  return useMemo(() => (payload ? payloadToImageData(payload, filePath) : null), [payload, filePath]);
};

const useImageDataAtRef = (workspaceId: string, filePath: string, gitRef: string | null): ImageData | null => {
  // File may not exist at base ref (new file) — the query errors and `data`
  // stays undefined, which resolves to `null` here.
  const { data: payload } = useWorkspaceFilePayload(gitRef ? workspaceId : null, gitRef ? filePath : null, gitRef);
  return useMemo(() => (payload ? payloadToImageData(payload, filePath) : null), [payload, filePath]);
};

type ImageViewerProps = {
  dataUrl: string;
  label?: string;
};

const ImageViewer = ({ dataUrl, label }: ImageViewerProps): ReactElement => {
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [isPanning, setIsPanning] = useState(false);
  const panStartRef = useRef({ x: 0, y: 0 });
  const translateStartRef = useRef({ x: 0, y: 0 });
  const [dimensions, setDimensions] = useState<ImageDimensions | null>(null);

  const handleWheel = useCallback((e: React.WheelEvent): void => {
    e.preventDefault();
    setScale((prev) => {
      const delta = e.deltaY > 0 ? -ZOOM_STEP : ZOOM_STEP;
      return Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, prev + delta));
    });
  }, []);

  const handlePointerDown = useCallback(
    (e: React.PointerEvent): void => {
      e.preventDefault();
      setIsPanning(true);
      panStartRef.current = { x: e.clientX, y: e.clientY };
      translateStartRef.current = { ...translate };
      (e.target as HTMLElement).setPointerCapture(e.pointerId);
    },
    [translate],
  );

  const handlePointerMove = useCallback(
    (e: React.PointerEvent): void => {
      if (!isPanning) return;
      const dx = e.clientX - panStartRef.current.x;
      const dy = e.clientY - panStartRef.current.y;
      setTranslate({
        x: translateStartRef.current.x + dx,
        y: translateStartRef.current.y + dy,
      });
    },
    [isPanning],
  );

  const handlePointerUp = useCallback((): void => {
    setIsPanning(false);
  }, []);

  const handleImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>): void => {
    const img = e.currentTarget;
    setDimensions({ width: img.naturalWidth, height: img.naturalHeight });
  }, []);

  return (
    <Flex direction="column" gap="2" flexGrow="1" align="center">
      {label && (
        <Text size="1" color="gray" weight="medium">
          {label}
        </Text>
      )}
      <div
        className={styles.imageContainer}
        onWheel={handleWheel}
        onPointerDown={handlePointerDown}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        style={{ cursor: isPanning ? "grabbing" : "grab" }}
      >
        <img
          src={dataUrl}
          alt=""
          className={styles.image}
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
          }}
          onLoad={handleImageLoad}
          draggable={false}
        />
      </div>
      {dimensions && (
        <Text size="1" color="gray">
          {dimensions.width} x {dimensions.height}
        </Text>
      )}
    </Flex>
  );
};

type ActionButtonsProps = {
  workspaceId: string;
  filePath: string;
};

const ActionButtons = ({ workspaceId, filePath }: ActionButtonsProps): ReactElement => {
  const handleOpenFile = useCallback((): void => {
    openInOs({ workspaceId, path: filePath, action: "open_file" });
  }, [workspaceId, filePath]);

  const handleOpenFolder = useCallback((): void => {
    openInOs({ workspaceId, path: filePath, action: "open_containing_folder" });
  }, [workspaceId, filePath]);

  return (
    <Flex gap="2" justify="center">
      <Button variant="soft" size="1" onClick={handleOpenFile}>
        <ExternalLink size={14} />
        Open in default app
      </Button>
      <Button variant="soft" size="1" onClick={handleOpenFolder}>
        <FolderOpen size={14} />
        Open containing folder
      </Button>
    </Flex>
  );
};

type ImageMetadataProps = {
  filePath: string;
  imageData: ImageData;
  dimensions: ImageDimensions | null;
};

const ImageMetadata = ({ filePath, imageData, dimensions }: ImageMetadataProps): ReactElement => {
  return (
    <table className={styles.metadataTable}>
      <tbody>
        <tr>
          <td className={styles.metadataLabel}>Type</td>
          <td className={styles.metadataValue}>{getMimeType(filePath)}</td>
        </tr>
        {dimensions && (
          <tr>
            <td className={styles.metadataLabel}>Dimensions</td>
            <td className={styles.metadataValue}>
              {dimensions.width} x {dimensions.height}
            </td>
          </tr>
        )}
        <tr>
          <td className={styles.metadataLabel}>Size</td>
          <td className={styles.metadataValue}>{formatFileSize(imageData.sizeBytes)}</td>
        </tr>
      </tbody>
    </table>
  );
};

type SingleImagePreviewProps = {
  workspaceId: string;
  filePath: string;
  imageData: ImageData;
};

const SingleImagePreview = ({ workspaceId, filePath, imageData }: SingleImagePreviewProps): ReactElement => {
  const [dimensions, setDimensions] = useState<ImageDimensions | null>(null);

  const handleImageLoad = useCallback((e: React.SyntheticEvent<HTMLImageElement>): void => {
    const img = e.currentTarget;
    setDimensions({ width: img.naturalWidth, height: img.naturalHeight });
  }, []);

  return (
    <Flex
      direction="column"
      gap="3"
      flexGrow="1"
      p="3"
      className={styles.scrollArea}
      data-testid="binary-image-preview"
    >
      <div className={styles.imageContainer} style={{ cursor: "default" }}>
        <img src={imageData.dataUrl} alt="" className={styles.image} onLoad={handleImageLoad} draggable={false} />
      </div>
      <ImageMetadata filePath={filePath} imageData={imageData} dimensions={dimensions} />
      {getBackendCapabilities().canOpenInOS && <ActionButtons workspaceId={workspaceId} filePath={filePath} />}
    </Flex>
  );
};

type BinaryPreviewProps = {
  workspaceId: string;
  filePath: string;
  fileStatus: string | null;
  previousFilePath: string | null;
};

export const BinaryPreview = ({
  workspaceId,
  filePath,
  fileStatus,
  previousFilePath,
}: BinaryPreviewProps): ReactElement => {
  const isImage = useMemo(() => isSupportedImageFormat(filePath), [filePath]);
  const workspace = useWorkspace(workspaceId);
  const baseRef = workspace?.targetBranch ?? "main";

  const imageData = useImageData(workspaceId, filePath);
  const isModifiedImage = isImage && fileStatus === "M";
  const oldFilePath = previousFilePath ?? filePath;
  const oldImageData = useImageDataAtRef(workspaceId, oldFilePath, isModifiedImage ? baseRef : null);

  if (!isImage) {
    const fileName = filePath.split("/").pop() ?? filePath;
    return (
      <Flex
        direction="column"
        align="center"
        justify="center"
        gap="3"
        flexGrow="1"
        p="4"
        data-testid="binary-unsupported"
      >
        <FileIcon size={48} className={styles.fileIcon} />
        <Text size="2" color="gray">
          Binary file — cannot preview
        </Text>
        <Text size="1" color="gray">
          {fileName}
          {imageData ? ` (${formatFileSize(imageData.sizeBytes)})` : ""}
        </Text>
        {getBackendCapabilities().canOpenInOS && <ActionButtons workspaceId={workspaceId} filePath={filePath} />}
      </Flex>
    );
  }

  if (!imageData) {
    return (
      <Flex align="center" justify="center" flexGrow="1">
        <Text size="2" color="gray">
          Loading image...
        </Text>
      </Flex>
    );
  }

  if (isModifiedImage && oldImageData) {
    return (
      <Flex
        direction="column"
        gap="3"
        flexGrow="1"
        p="3"
        className={styles.scrollArea}
        data-testid="binary-image-comparison"
      >
        <Flex gap="3" flexGrow="1">
          <ImageViewer dataUrl={oldImageData.dataUrl} label="Before" />
          <ImageViewer dataUrl={imageData.dataUrl} label="After" />
        </Flex>
        {getBackendCapabilities().canOpenInOS && <ActionButtons workspaceId={workspaceId} filePath={filePath} />}
      </Flex>
    );
  }

  // Keyed by filePath so dimensions state resets to null on file change,
  // avoiding a flash of the previous image's dimensions before onLoad fires.
  return <SingleImagePreview key={filePath} workspaceId={workspaceId} filePath={filePath} imageData={imageData} />;
};
