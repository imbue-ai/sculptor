import { readFileSync } from "node:fs";
import path from "node:path";

import { uploadsDir } from "~/config/sculptor_folder";
import type { PiImage } from "~/harness/pi/rpc";

// Prompt assembly for the pi harness (pi_agent/prompt_assembly.py).
// `ChatInputUserMessage.files` carries upload-path attachments. Pi delivers them
// two ways, split exclusively by type: images ride the `prompt` command's
// `images[]` field (base64 + mimeType), everything else is presented as file
// paths in the prompt text for pi to read with its own `read` tool. A missing
// source is skipped rather than failing the turn.

// The image formats the upload pipeline accepts, mapped to the pi ImageContent
// mimeType. Mirrors the frontend's ALLOWED_EXTENSIONS (FileUploadUtils.ts).
const IMAGE_EXTENSION_TO_MIME_TYPE: Readonly<Record<string, string>> = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".gif": "image/gif",
};

export interface AssembledAttachments {
  images: PiImage[];
  // Prepended to the prompt text (the non-image attachment paths), or "".
  instructions: string;
}

// An entry is an upload id under internal/uploads/ (web/app.py upload-file
// stores `<uuid><ext>` there). Resolve it strictly within the uploads dir so a
// crafted entry — an absolute path or a `../` traversal — can't read an
// arbitrary file off the host. Returns null for an entry that escapes (skipped
// like a missing source). Mirrors the containment check in git/discard.ts.
function resolveUploadPath(entry: string): string | null {
  const root = path.resolve(uploadsDir());
  const resolved = path.resolve(root, entry);
  if (resolved !== root && !resolved.startsWith(root + path.sep)) {
    return null;
  }
  return resolved;
}

function imageMimeType(filePath: string): string | undefined {
  return IMAGE_EXTENSION_TO_MIME_TYPE[path.extname(filePath).toLowerCase()];
}

function buildAttachmentInstructions(filePaths: readonly string[]): string {
  if (filePaths.length === 0) {
    return "";
  }
  const filePathsStr = filePaths.join("\n- ");
  return `<system-instructions>
The user has attached these files. Read them before proceeding.
${filePathsStr}
</system-instructions>

`;
}

export function assemblePiAttachments(
  files: readonly string[],
): AssembledAttachments {
  const images: PiImage[] = [];
  const pathAttachments: string[] = [];
  for (const entry of files) {
    const resolved = resolveUploadPath(entry);
    if (resolved === null) {
      // Entry escapes the uploads dir — skip rather than read off-host.
      continue;
    }
    const mimeType = imageMimeType(resolved);
    if (mimeType !== undefined) {
      try {
        const data = readFileSync(resolved).toString("base64");
        images.push({ type: "image", data, mimeType });
      } catch {
        // Skip a missing/unreadable image rather than failing the turn.
      }
    } else {
      pathAttachments.push(resolved);
    }
  }
  return {
    images,
    instructions: buildAttachmentInstructions(pathAttachments),
  };
}
