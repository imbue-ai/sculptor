import type { ReactElement, Ref } from "react";
import { forwardRef, useImperativeHandle, useRef, useState } from "react";

import { ElementIds } from "~/api";

import { ALLOWED_EXTENSIONS, processAndValidateFiles, saveFiles } from "./FileUploadUtils";
import type { ToastContent } from "./Toast";
import { ToastType } from "./Toast";

type FileUploadProps = {
  files: Array<string>;
  onFilesChange: (files: Array<string>) => void;
  onError: (toast: ToastContent) => void;
  disabled?: boolean;
};

/**
 * Imperative handle exposed via `forwardRef` so callers (the plus-prefilter
 * picker's "Images" category) can open the native file dialog without
 * needing their own `<input type="file">` and validation pipeline.
 */
export type FileUploadHandle = {
  triggerUpload: () => void;
};

/**
 * Headless image-attachment harness. Renders a hidden `<input type="file">`
 * and exposes `triggerUpload()` via ref so consumers can fire the native
 * picker dialog from elsewhere in the UI. There's no visible affordance —
 * the in-editor `+` menu surfaces the "Images" entry point now.
 */
export const FileUpload = forwardRef<FileUploadHandle, FileUploadProps>(function FileUpload(
  { files, onFilesChange, onError, disabled = false }: FileUploadProps,
  ref: Ref<FileUploadHandle>,
): ReactElement {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);

  useImperativeHandle(
    ref,
    (): FileUploadHandle => ({
      triggerUpload: (): void => {
        // Ignore programmatic triggers while a previous upload is still
        // resolving so we don't reset the input mid-flight.
        if (disabled || isUploading) return;
        fileInputRef.current?.click();
      },
    }),
    [disabled, isUploading],
  );

  const handleFileUpload = async (event: React.ChangeEvent<HTMLInputElement>): Promise<void> => {
    const filesToUpload = event.target.files;
    if (!filesToUpload || filesToUpload.length === 0) return;

    setIsUploading(true);

    const { validFiles, errors } = await processAndValidateFiles(filesToUpload);

    if (errors.length > 0) {
      const errorMessage = errors.join("\n");
      onError({
        title: "Upload Error",
        description: errorMessage,
        type: ToastType.ERROR,
      });
    }

    if (validFiles.length === 0) {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
      return;
    }

    const savedFilePaths = await saveFiles(validFiles);

    if (savedFilePaths.length > 0) {
      onFilesChange([...files, ...savedFilePaths]);
    } else {
      onError({ title: "Failed to upload files", type: ToastType.ERROR });
    }

    setIsUploading(false);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  return (
    <input
      ref={fileInputRef}
      type="file"
      accept={ALLOWED_EXTENSIONS.join(",")}
      multiple
      onChange={handleFileUpload}
      style={{ display: "none" }}
      data-testid={ElementIds.FILE_UPLOAD}
    />
  );
});
