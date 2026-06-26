// Session-token CSRF protection, mirroring sculptor/sculptor/web/auth.py.
//
// When SESSION_TOKEN is configured (the Electron launcher sets it in the
// backend's environment), every request under /api/ must present the token in
// the x-session-token header, the same-named query param, or the same-named
// cookie. When SESSION_TOKEN is unset, auth is disabled and all requests pass
// (matching the Python `expected_token is None` short-circuit). The token lives
// in process memory only and is never persisted.

export const SESSION_TOKEN_HEADER_NAME = "x-session-token";

// Query-param names whose value is a session token. The token is accepted as a
// query param because browsers cannot set custom headers on a WebSocket
// handshake, but that means it rides in the request URL — so it must be redacted
// before the URL lands in any log line. We cover the header-derived name plus
// the generic aliases a client might use.
const REDACTED_TOKEN_QUERY_PARAM_NAMES: ReadonlySet<string> = new Set([
  SESSION_TOKEN_HEADER_NAME,
  "session_token",
  "token",
]);
const REDACTED_TOKEN_PLACEHOLDER = "REDACTED";

// Replace any session-token query-param value in a request URL with a redaction
// placeholder, leaving the path and all other params intact. Returns the URL
// unchanged when it carries no token param (so non-token requests log verbatim).
export function redactSessionTokenInUrl(rawUrl: string): string {
  const queryStart = rawUrl.indexOf("?");
  if (queryStart === -1) {
    return rawUrl;
  }
  const pathPart = rawUrl.slice(0, queryStart);
  const params = new URLSearchParams(rawUrl.slice(queryStart + 1));
  let redacted = false;
  for (const name of REDACTED_TOKEN_QUERY_PARAM_NAMES) {
    if (params.has(name)) {
      params.set(name, REDACTED_TOKEN_PLACEHOLDER);
      redacted = true;
    }
  }
  if (!redacted) {
    return rawUrl;
  }
  return `${pathPart}?${params.toString()}`;
}

// WebSocket close code used when a handshake is rejected for a bad/missing
// token. 4401 mirrors HTTP 401 in the application-private 4000-4999 range; WS
// endpoints accept-then-close with this code so the browser sees a real close
// frame instead of an opaque 1006.
export const WEBSOCKET_INVALID_SESSION_TOKEN_CLOSE_CODE = 4401;

export const SESSION_TOKEN_PROTECTED_API_PREFIXES = ["/api/"];

export const SESSION_TOKEN_EXEMPT_PATHS = [
  "/api/v1/health",
  "/api/v1/session-token",
  // Developer-only tracing endpoint; no auth so Electron main (a separate
  // process with no shared cookie jar) can post to it. See auth.py.
  "/api/v1/trace/batch",
];

export function getExpectedSessionToken(env: NodeJS.ProcessEnv = process.env): string | undefined {
  // Present (even empty) means auth is enabled with that value; absent disables
  // auth — matching pydantic's `SESSION_TOKEN: SecretStr | None = None`.
  return env.SESSION_TOKEN;
}

export function isProtectedPath(path: string): boolean {
  if (SESSION_TOKEN_EXEMPT_PATHS.includes(path)) {
    return false;
  }
  return SESSION_TOKEN_PROTECTED_API_PREFIXES.some((prefix) => path.startsWith(prefix));
}

export function parseCookies(header: string | undefined): Record<string, string> {
  const cookies: Record<string, string> = {};
  if (header === undefined) {
    return cookies;
  }
  for (const part of header.split(";")) {
    const index = part.indexOf("=");
    if (index === -1) {
      continue;
    }
    const key = part.slice(0, index).trim();
    if (key !== "") {
      cookies[key] = part.slice(index + 1).trim();
    }
  }
  return cookies;
}

export function hasValidToken(
  presented: { header?: string; query?: string; cookie?: string },
  expected: string,
): boolean {
  return presented.header === expected || presented.query === expected || presented.cookie === expected;
}
