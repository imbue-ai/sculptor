import type { CSSProperties } from "react";

import type { DiffData } from "~/components/DiffUtils.ts";

import type { FileStatus, FlatFileEntry, TreeNode } from "./types.ts";

/** Row height (px) used by virtualizer across all file browser views. */
export const FILE_TREE_ROW_HEIGHT = 28;

/** Top padding (px) inside the virtualised scroll area. */
export const FILE_TREE_PADDING_TOP = 8;

/** Determine a file's change status from parsed diff metadata. */
export const determineFileStatus = (fileChange: DiffData["fileChanges"][number]): FileStatus => {
  const { previousFileName, newFileName } = fileChange.fileNames;
  if (previousFileName && newFileName && previousFileName !== newFileName) {
    return "R";
  }

  if (newFileName === null) {
    return "D";
  }

  if (previousFileName === null) {
    return "A";
  }
  return "M";
};

/** Number of extra rows to render outside the viewport for smoother scrolling. */
export const FILE_TREE_OVERSCAN = 10;

/** Maps file status to its design-system color token (text level). */
const STATUS_COLORS: Record<FileStatus, string> = {
  M: "var(--amber-11)",
  A: "var(--green-11)",
  D: "var(--red-11)",
  R: "var(--purple-11)",
};

/** Pre-computed style objects for status colors, avoiding inline object creation on each render. */
export const STATUS_COLOR_STYLES: Record<FileStatus, CSSProperties> = {
  M: { color: STATUS_COLORS.M },
  A: { color: STATUS_COLORS.A },
  D: { color: STATUS_COLORS.D },
  R: { color: STATUS_COLORS.R },
};

/** Recursively collects all descendant folder paths from a tree node. */
export const collectDescendantFolderPaths = (node: TreeNode): Array<string> => {
  const paths: Array<string> = [];
  for (const child of node.children) {
    if (child.type === "directory") {
      paths.push(child.path);
      paths.push(...collectDescendantFolderPaths(child));
    }
  }
  return paths;
};

const BINARY_EXTENSIONS = new Set([
  // Images
  "png",
  "jpg",
  "jpeg",
  "gif",
  "webp",
  "svg",
  "ico",
  "bmp",
  "tiff",
  // Fonts
  "woff",
  "woff2",
  "ttf",
  "otf",
  "eot",
  // Documents
  "pdf",
  // Archives
  "zip",
  "tar",
  "gz",
  // Compiled
  "wasm",
  "pyc",
  "class",
  // Media
  "mp3",
  "mp4",
  "avi",
  "mov",
]);

const SUPPORTED_IMAGE_EXTENSIONS = new Set(["png", "jpg", "jpeg", "gif", "webp", "svg"]);

export const buildFileTree = ({
  files,
  fileStatusMap,
  fileErrors,
}: {
  files: ReadonlyArray<{ path: string; type: "file" | "directory" }>;
  fileStatusMap: Map<string, FileStatus>;
  fileErrors: Record<string, string>;
}): Array<TreeNode> => {
  const nodeMap = new Map<string, TreeNode>();

  const getOrCreateFolder = (folderPath: string): TreeNode => {
    const existing = nodeMap.get(folderPath);
    if (existing) {
      return existing;
    }
    const segments = folderPath.split("/");
    const node: TreeNode = {
      name: segments[segments.length - 1],
      path: folderPath,
      type: "directory",
      children: [],
    };
    nodeMap.set(folderPath, node);
    return node;
  };

  for (const file of files) {
    const segments = file.path.split("/");

    // Create intermediate folder nodes
    for (let i = 1; i < segments.length; i++) {
      const folderPath = segments.slice(0, i).join("/");
      getOrCreateFolder(folderPath);
    }

    if (file.type === "file") {
      const node: TreeNode = {
        name: segments[segments.length - 1],
        path: file.path,
        type: "file",
        children: [],
        status: fileStatusMap.get(file.path),
        errorMessage: fileErrors[file.path],
      };
      nodeMap.set(file.path, node);
    } else {
      getOrCreateFolder(file.path);
    }
  }

  // Build parent-child relationships
  for (const [path, node] of nodeMap) {
    const lastSlash = path.lastIndexOf("/");
    if (lastSlash > 0) {
      const parentPath = path.slice(0, lastSlash);
      const parent = nodeMap.get(parentPath);
      if (parent) {
        parent.children.push(node);
      }
    }
  }

  // Collect root nodes (no parent path in the map)
  const roots: Array<TreeNode> = [];
  for (const [path, node] of nodeMap) {
    const lastSlash = path.lastIndexOf("/");
    if (lastSlash < 0 || !nodeMap.has(path.slice(0, lastSlash))) {
      roots.push(node);
    }
  }

  // Filter out .git directory at root level
  const filtered = roots.filter((node) => !(node.type === "directory" && node.name === ".git"));

  return sortTreeNodes(filtered);
};

export const sortTreeNodes = (nodes: Array<TreeNode>): Array<TreeNode> => {
  const sorted = [...nodes].sort((a, b) => {
    // Directories before files
    if (a.type !== b.type) {
      return a.type === "directory" ? -1 : 1;
    }
    // Alphabetical within each group (case-insensitive)
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });

  // Recursively sort children — create new node objects to avoid mutating originals
  return sorted.map((node) => {
    if (node.children.length > 0) {
      return { ...node, children: sortTreeNodes(node.children) };
    }
    return node;
  });
};

export const getAncestorPaths = (filePath: string): Array<string> => {
  const segments = filePath.split("/");
  const ancestors: Array<string> = [];
  for (let i = 1; i < segments.length; i++) {
    ancestors.push(segments.slice(0, i).join("/"));
  }
  return ancestors;
};

export const computeFolderChangeCounts = (roots: Array<TreeNode>): Map<string, number> => {
  const counts = new Map<string, number>();

  const countChanges = (node: TreeNode): number => {
    if (node.type === "file") {
      return node.status != null ? 1 : 0;
    }
    let total = 0;
    for (const child of node.children) {
      total += countChanges(child);
    }
    counts.set(node.path, total);
    return total;
  };

  for (const root of roots) {
    countChanges(root);
  }

  return counts;
};

/**
 * Prune a full file tree down to only changed files and their ancestor directories.
 * Empty directories with no changed descendants are removed.
 */
export const buildChangesTree = (roots: Array<TreeNode>): Array<TreeNode> => {
  const prune = (nodes: Array<TreeNode>): Array<TreeNode> => {
    const kept: Array<TreeNode> = [];
    for (const node of nodes) {
      if (node.type === "file") {
        if (node.status != null) {
          kept.push(node);
        }
      } else {
        const prunedChildren = prune(node.children);
        if (prunedChildren.length > 0) {
          kept.push({ ...node, children: prunedChildren });
        }
      }
    }
    return kept;
  };
  return prune(roots);
};

/**
 * Prune a file tree to only files in the given path set and their ancestor directories.
 * Empty directories with no matching descendants are removed.
 */
export const filterTreeByPaths = (roots: Array<TreeNode>, matchingPaths: Set<string>): Array<TreeNode> => {
  const prune = (nodes: Array<TreeNode>): Array<TreeNode> => {
    const kept: Array<TreeNode> = [];
    for (const node of nodes) {
      if (node.type === "file") {
        if (matchingPaths.has(node.path)) {
          kept.push(node);
        }
      } else {
        const prunedChildren = prune(node.children);
        if (prunedChildren.length > 0) {
          kept.push({ ...node, children: prunedChildren });
        }
      }
    }
    return kept;
  };
  return prune(roots);
};

/** Collect all directory paths in a tree (for auto-expanding). */
export const collectAllFolderPaths = (nodes: Array<TreeNode>): Array<string> => {
  const paths: Array<string> = [];
  for (const node of nodes) {
    if (node.type === "directory") {
      paths.push(node.path);
      paths.push(...collectAllFolderPaths(node.children));
    }
  }
  return paths;
};

/**
 * Merge chains of single-child directories into one node.
 * e.g., src > components > utils (each with one child) becomes a single "src/components/utils" node.
 */
export const compactSingleChildFolders = (roots: Array<TreeNode>): Array<TreeNode> => {
  return roots.map(compactNode);
};

const compactNode = (node: TreeNode): TreeNode => {
  if (node.type === "file") return node;

  let compacted = { ...node, children: node.children.map(compactNode) };

  while (compacted.children.length === 1 && compacted.children[0].type === "directory") {
    const child = compacted.children[0];
    compacted = { ...child, name: `${compacted.name}/${child.name}` };
  }

  return compacted;
};

export type FlatRowEntry = {
  node: TreeNode;
  depth: number;
};

/**
 * Flatten the tree into a list of rows with explicit depth.
 * Unlike `getDepth(path)`, this correctly handles compact folder nodes
 * where the path depth doesn't match the visual nesting level.
 */
export const flattenVisibleTreeWithDepth = ({
  roots,
  expandedFolders,
}: {
  roots: Array<TreeNode>;
  expandedFolders: Set<string>;
}): Array<FlatRowEntry> => {
  const result: Array<FlatRowEntry> = [];

  const walk = (nodes: Array<TreeNode>, depth: number): void => {
    for (const node of nodes) {
      result.push({ node, depth });
      if (node.type === "directory" && expandedFolders.has(node.path)) {
        walk(node.children, depth + 1);
      }
    }
  };

  walk(roots, 0);
  return result;
};

/** Case-insensitive substring search on file paths. Returns matching entries and a path set for filtering. */
export const filterFilesBySubstring = (
  files: ReadonlyArray<{ path: string }>,
  query: string,
): { results: Array<FlatFileEntry>; resultCount: number; matchingPaths: Set<string> } => {
  if (query === "") {
    return { results: [], resultCount: 0, matchingPaths: new Set() };
  }

  const lowerQuery = query.toLowerCase();
  const results: Array<FlatFileEntry> = [];

  for (const file of files) {
    if (file.path.toLowerCase().includes(lowerQuery)) {
      const segments = file.path.split("/");
      const name = segments[segments.length - 1];
      const parentPath = segments.length > 1 ? segments.slice(0, -1).join("/") : "";
      results.push({ path: file.path, name, parentPath });
    }
  }

  const matchingPaths = new Set(results.map((r) => r.path));
  return { results, resultCount: results.length, matchingPaths };
};

/** Collect all files (regardless of status) into a flat list for the "all" tab flat mode. */
export const getAllFiles = (roots: Array<TreeNode>): Array<FlatFileEntry> => {
  const entries: Array<FlatFileEntry> = [];

  const collect = (nodes: Array<TreeNode>): void => {
    for (const node of nodes) {
      if (node.type === "file") {
        const lastSlash = node.path.lastIndexOf("/");
        entries.push({
          path: node.path,
          name: node.name,
          parentPath: lastSlash > 0 ? node.path.slice(0, lastSlash) : "",
          status: node.status,
          errorMessage: node.errorMessage,
        });
      }

      if (node.type === "directory") {
        collect(node.children);
      }
    }
  };

  collect(roots);

  entries.sort((a, b) => {
    const parentCompare = a.parentPath.localeCompare(b.parentPath);
    if (parentCompare !== 0) {
      return parentCompare;
    }
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });

  return entries;
};

export const getChangedFiles = (roots: Array<TreeNode>): Array<FlatFileEntry> => {
  const entries: Array<FlatFileEntry> = [];

  const collect = (nodes: Array<TreeNode>): void => {
    for (const node of nodes) {
      if (node.type === "file" && node.status != null) {
        const lastSlash = node.path.lastIndexOf("/");
        entries.push({
          path: node.path,
          name: node.name,
          parentPath: lastSlash > 0 ? node.path.slice(0, lastSlash) : "",
          status: node.status,
          errorMessage: node.errorMessage,
        });
      }

      if (node.type === "directory") {
        collect(node.children);
      }
    }
  };

  collect(roots);

  // Sort by parent directory then alphabetically
  entries.sort((a, b) => {
    const parentCompare = a.parentPath.localeCompare(b.parentPath);
    if (parentCompare !== 0) {
      return parentCompare;
    }
    return a.name.toLowerCase().localeCompare(b.name.toLowerCase());
  });

  return entries;
};

const getExtension = (fileName: string): string => {
  const lastDot = fileName.lastIndexOf(".");
  if (lastDot < 0) {
    return "";
  }
  return fileName.slice(lastDot + 1).toLowerCase();
};

export const isBinaryFile = (fileName: string): boolean => {
  return BINARY_EXTENSIONS.has(getExtension(fileName));
};

export const isSupportedImageFormat = (fileName: string): boolean => {
  return SUPPORTED_IMAGE_EXTENSIONS.has(getExtension(fileName));
};

/**
 * Truncate a directory path for display by keeping the first and last segments
 * and replacing the middle with "…". Prioritises showing the last segment
 * (closest parent) since it provides the most context about where a file lives.
 *
 *   "sculptor/frontend/src/components" → "sculptor/…/components"
 *   "imbue_core/imbue_core"            → "imbue_core/imbue_core" (unchanged)
 */
export const truncateMiddlePath = (dirPath: string, maxSegments: number = 3): string => {
  const segments = dirPath.split("/");
  if (segments.length <= maxSegments) return dirPath;

  const first = segments[0];
  const last = segments[segments.length - 1];
  return `${first}/\u2026/${last}`;
};
