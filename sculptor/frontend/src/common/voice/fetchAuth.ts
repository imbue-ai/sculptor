// The speech libraries fetch model weights with a bare fetch() that carries no
// session token, but GET /api/v1/voice-models/* sits behind the /api guard.
// This helper patches fetch only for the duration of a model-loading action:
// voice-model requests gain auth, every other fetch passes through untouched,
// and the unpatched fetch is restored when the action settles.
//
// Parameterized rather than reading auth state itself so it works in both
// realms that load models: the renderer (vad-web's Silero fetch) and the ASR
// worker (Moonshine's files), each patching its own realm's fetch.

export type VoiceModelFetchAuth = {
  /** Absolute base URL of the backend voice-models endpoint. */
  modelsBase: string;
  /** Session token to append as a query param; null when the same-origin
   *  cookie carries auth (web builds). */
  token: string | null;
  /** The query-param name the backend accepts the token under. */
  tokenParam: string;
};

const extractRequestUrl = (input: RequestInfo | URL): string => {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
};

const authenticateUrl = (url: string, auth: VoiceModelFetchAuth): string => {
  if (auth.token === null) return url;
  const resolved = new URL(url);
  if (!resolved.searchParams.has(auth.tokenParam)) {
    resolved.searchParams.set(auth.tokenParam, auth.token);
  }
  return resolved.href;
};

export const withVoiceModelFetchAuth = async <T>(auth: VoiceModelFetchAuth, action: () => Promise<T>): Promise<T> => {
  const unpatchedFetch = globalThis.fetch;
  const callFetch = unpatchedFetch.bind(globalThis);
  const patched = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (!extractRequestUrl(input).startsWith(auth.modelsBase)) {
      return callFetch(input, init);
    }
    return callFetch(authenticateUrl(extractRequestUrl(input), auth), { ...init, credentials: "include" });
  };
  globalThis.fetch = patched;
  try {
    return await action();
  } finally {
    // Another patcher may have wrapped fetch meanwhile; only restore while the
    // patch is still on top.
    if (globalThis.fetch === patched) {
      globalThis.fetch = unpatchedFetch;
    }
  }
};
