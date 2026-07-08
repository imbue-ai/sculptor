export type FileListEntry = { path: string; type: "file" | "directory" };

export type FileStatus = "M" | "A" | "D" | "R";

export type ViewMode = "tree" | "flat";

export type TreeNode = {
  name: string;
  path: string;
  type: "file" | "directory";
  children: Array<TreeNode>;
  status?: FileStatus;
  errorMessage?: string;
};

export type FlatFileEntry = {
  path: string;
  name: string;
  parentPath: string;
  status?: FileStatus;
  errorMessage?: string;
};

export type FileBrowserState = {
  expandedFolders: Array<string>;
  changesExpandedFolders: Array<string>;
  // Folders the Changes tree has already auto-expanded once. The tree opens each
  // folder the first time it appears and records it here (persisted, not a per-mount
  // ref), so a folder the user then collapses stays collapsed across remounts,
  // change ticks, and workspace switches, while genuinely new changed folders still
  // open on first sight. Optional because per-workspace snapshots persisted before
  // this field existed load without it; readers must coalesce (`?? []`), which this
  // `?` enforces at the type level.
  changesAutoExpandedFolders?: Array<string>;
  viewMode: ViewMode;
  searchQuery: string;
  searchOpen: boolean;
  scrollPosition: number;
};

export type FileContextMenuContext = {
  filePath: string;
  isFolder: boolean;
  fileStatus?: FileStatus;
  isBinary: boolean;
  source: "tree" | "flat-list" | "search" | "diff-header" | "combined-diff-header";
};

export type PerFileDiff = {
  filePath: string;
  previousFilePath: string | null;
  status: FileStatus;
  diffString: string;
  addedLines: number;
  removedLines: number;
};
