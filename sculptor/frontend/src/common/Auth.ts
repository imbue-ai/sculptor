const SESSION_TOKEN_ENDPOINT = "api/v1/session-token";

export const SESSION_TOKEN_HEADER_NAME = "x-session-token";

let sessionToken: string | undefined = undefined;

/*
 * Initialize the session token - serves as a CSRF protection mechanism.
 */
export const initializeSessionToken = async (): Promise<void> => {
  if (!window.sculptor) {
    // As a backup, outside of the electron context, initialize the session token using through the samesite cookie.
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

export const setupAuthHeaders = (headers: Headers): undefined => {
  const sessionToken = getSessionToken();
  if (sessionToken) {
    headers.set(SESSION_TOKEN_HEADER_NAME, sessionToken);
  }
};
