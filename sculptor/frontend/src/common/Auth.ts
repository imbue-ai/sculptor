const SESSION_TOKEN_ENDPOINT = "api/v1/session-token";

export const SESSION_TOKEN_HEADER_NAME = "x-session-token";

let sessionToken: string | undefined = undefined;

/*
 * Initialize the session token - serves as a CSRF protection mechanism.
 */
export const initializeSessionToken = async (): Promise<void> => {
  if (!window.sculptor) {
    // As a backup, outside of the electron context, initialize the session token through the samesite cookie.
    // API_URL_BASE is "" for the web build (same-origin); use `||` (not `??`) so the empty string
    // falls back to the page origin — `new URL(endpoint, "")` throws "is not a valid URL".
    const sessionTokenInitializationURL = new URL(SESSION_TOKEN_ENDPOINT, API_URL_BASE || window.location.origin);
    // This sets the session token cookie.
    await fetch(sessionTokenInitializationURL.toString(), { method: "GET" });
  } else {
    sessionToken = await window.sculptor.getSessionToken();
  }
};

export const getSessionToken = (): string | undefined => {
  return sessionToken;
};

export const setupAuthHeaders = (headers: Headers): void => {
  const token = getSessionToken();
  if (token) {
    headers.set(SESSION_TOKEN_HEADER_NAME, token);
  }
};
