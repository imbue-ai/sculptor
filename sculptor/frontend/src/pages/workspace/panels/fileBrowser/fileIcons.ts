import type { LucideIcon } from "lucide-react";
import { File, FileCode, FileCog, FileImage, FileJson2, FileText, FileType } from "lucide-react";

/**
 * Maps file extensions to lucide-react icons.
 * Add new entries here to support additional file types.
 */
const EXTENSION_ICON_MAP: Readonly<Record<string, LucideIcon>> = {
  // Code
  ".ts": FileCode,
  ".tsx": FileCode,
  ".js": FileCode,
  ".jsx": FileCode,
  ".py": FileCode,
  ".go": FileCode,
  ".rs": FileCode,
  ".rb": FileCode,
  ".java": FileCode,
  ".kt": FileCode,
  ".c": FileCode,
  ".cpp": FileCode,
  ".h": FileCode,
  ".hpp": FileCode,
  ".cs": FileCode,
  ".swift": FileCode,
  ".sh": FileCode,
  ".bash": FileCode,
  ".zsh": FileCode,
  ".lua": FileCode,
  ".php": FileCode,
  ".r": FileCode,
  ".scala": FileCode,
  ".zig": FileCode,
  ".dart": FileCode,
  ".vue": FileCode,
  ".svelte": FileCode,
  ".html": FileCode,
  ".css": FileCode,
  ".scss": FileCode,
  ".less": FileCode,
  ".sql": FileCode,

  // Data / config (JSON-like)
  ".json": FileJson2,
  ".jsonl": FileJson2,
  ".jsonc": FileJson2,

  // Config
  ".yaml": FileCog,
  ".yml": FileCog,
  ".toml": FileCog,
  ".ini": FileCog,
  ".env": FileCog,
  ".cfg": FileCog,
  ".conf": FileCog,

  // Text / documentation
  ".md": FileText,
  ".mdx": FileText,
  ".txt": FileText,
  ".log": FileText,
  ".csv": FileText,
  ".rst": FileText,

  // Images
  ".png": FileImage,
  ".jpg": FileImage,
  ".jpeg": FileImage,
  ".gif": FileImage,
  ".svg": FileImage,
  ".webp": FileImage,
  ".ico": FileImage,
  ".bmp": FileImage,

  // Fonts
  ".woff": FileType,
  ".woff2": FileType,
  ".ttf": FileType,
  ".otf": FileType,
  ".eot": FileType,
};

export const getFileIcon = (filename: string): LucideIcon => {
  const lastDot = filename.lastIndexOf(".");
  if (lastDot <= 0) return File;

  const extension = filename.slice(lastDot).toLowerCase();
  return EXTENSION_ICON_MAP[extension] ?? File;
};
