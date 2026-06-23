import { ContextMenu } from "@radix-ui/themes";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { copyImageToClipboard } from "~/common/copyImageToClipboard.ts";

type CopyImageContextMenuProps = {
  /** Full-size image URL (blob: or data:) to copy to the clipboard. */
  url: string;
  // A single image element. `@radix-ui/themes` strips `asChild` from its
  // Trigger, so it wraps this in a span rather than reusing the element
  // directly; requiring one ReactElement keeps the wrapped content well-formed.
  children: ReactElement;
};

export const CopyImageContextMenu = ({ url, children }: CopyImageContextMenuProps): ReactElement => {
  const handleCopy = (): void => {
    copyImageToClipboard(url).catch((error: unknown) => {
      console.error("Failed to copy image to clipboard:", error);
    });
  };

  return (
    <ContextMenu.Root>
      <ContextMenu.Trigger>{children}</ContextMenu.Trigger>
      <ContextMenu.Content size="1">
        <ContextMenu.Item onSelect={handleCopy} data-testid={ElementIds.FILE_PREVIEW_COPY_IMAGE}>
          Copy Image
        </ContextMenu.Item>
      </ContextMenu.Content>
    </ContextMenu.Root>
  );
};
