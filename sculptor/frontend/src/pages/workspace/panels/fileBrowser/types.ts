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
