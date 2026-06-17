const host = window.__SCULPTOR_HOST__;
if (!host || !host.tanstackReactQuery) {
  throw new Error(
    "Sculptor plugin runtime: window.__SCULPTOR_HOST__.tanstackReactQuery missing.",
  );
}
const T = host.tanstackReactQuery;

// Plugins share the host's QueryClient (resolved via context — plugin panels
// render under the host's QueryClientProvider). Key convention: the first
// element of every plugin query key MUST be the plugin id; the host's keys
// live under the reserved "sculptor" prefix. See plugins/README.md.
//
// QueryClient / QueryClientProvider are deliberately NOT exported: plugins
// consume the host's client, they don't construct their own. A second client
// nested into the tree would cut host components rendered inside plugin
// subtrees off from the shared cache.
export const useQuery = T.useQuery;
export const useQueries = T.useQueries;
export const useInfiniteQuery = T.useInfiniteQuery;
export const useSuspenseQuery = T.useSuspenseQuery;
export const useSuspenseQueries = T.useSuspenseQueries;
export const useMutation = T.useMutation;
export const useMutationState = T.useMutationState;
export const useQueryClient = T.useQueryClient;
export const useIsFetching = T.useIsFetching;
export const useIsMutating = T.useIsMutating;
export const keepPreviousData = T.keepPreviousData;
export const skipToken = T.skipToken;
