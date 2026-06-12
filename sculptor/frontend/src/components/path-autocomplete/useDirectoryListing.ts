import { useCallback } from "react";

import type { DirectoryEntry } from "~/api";
import { listDirectories } from "~/api";

type UseDirectoryListingResult = {
  fetchDirectories: (path: string) => Promise<Array<DirectoryEntry>>;
};

export const useDirectoryListing = (): UseDirectoryListingResult => {
  const fetchDirectories = useCallback(async (path: string): Promise<Array<DirectoryEntry>> => {
    const { data } = await listDirectories({
      query: { path },
      meta: { skipWsAck: true },
    });
    return data;
  }, []);

  return { fetchDirectories };
};
