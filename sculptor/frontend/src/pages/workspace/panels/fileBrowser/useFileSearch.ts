import { useMemo } from "react";

import { useWorkspaceFiles } from "~/common/state/hooks/useWorkspaceFiles.ts";

import type { FlatFileEntry } from "./types/fileBrowser.ts";
import { filterFilesBySubstring } from "./utils/fileTree.ts";

const EMPTY_MATCHING_PATHS = new Set<string>();

type UseFileSearchResult = {
  results: Array<FlatFileEntry>;
  resultCount: number;
  matchingPaths: Set<string>;
};

/** Searches workspace files by case-insensitive substring match on file path. */
export const useFileSearch = (workspaceId: string, query: string): UseFileSearchResult => {
  const { data: files } = useWorkspaceFiles(workspaceId);

  return useMemo(() => {
    if (!files || query === "") {
      return { results: [], resultCount: 0, matchingPaths: EMPTY_MATCHING_PATHS };
    }
    return filterFilesBySubstring(files, query);
  }, [files, query]);
};
