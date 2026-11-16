import { useQuery } from "@tanstack/react-query";

import type { JjBookmarkChoice } from "~/api";
import { listProjectJjBookmarks } from "~/api";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";

type JjBookmarkChoices = {
  /** The bookmarks in jj's order; undefined until fetched, or when the fetch failed. */
  bookmarks: ReadonlyArray<JjBookmarkChoice> | undefined;
  isFetching: boolean;
  /** Fetch again, e.g. when the picker opens, since bookmarks move without telling the frontend. */
  refetch: () => void;
};

/**
 * The bookmarks a new jj workspace in a colocated repository can start from.
 * No stream frame reports bookmark changes, so this is an ordinary fetch.
 */
export const useJjBookmarkChoices = (inputs: { projectId: string | null; isEnabled: boolean }): JjBookmarkChoices => {
  const { projectId, isEnabled } = inputs;
  const query = useQuery({
    queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "project", projectId, "jjBookmarkChoices"] as const,
    queryFn: async (): Promise<ReadonlyArray<JjBookmarkChoice>> => {
      const { data } = await listProjectJjBookmarks({ path: { project_id: projectId ?? "" } });
      return data.bookmarks;
    },
    enabled: projectId !== null && isEnabled,
    retry: false,
  });
  return {
    bookmarks: query.data,
    isFetching: query.isFetching,
    refetch: (): void => {
      void query.refetch();
    },
  };
};
