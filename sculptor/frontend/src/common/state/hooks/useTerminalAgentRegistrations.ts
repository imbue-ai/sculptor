import { useCallback, useState } from "react";

import type { TerminalAgentRegistration } from "~/api";
import { listTerminalAgentRegistrations } from "~/api";

/**
 * Fetch the current terminal-agent registrations on demand.
 *
 * Callers invoke `refresh` when their menu/select opens so the entries
 * track the registrations directory without a restart (REQ-REG-3) — the
 * backend re-reads the directory per request.
 */
export const useTerminalAgentRegistrations = (): {
  registrations: Array<TerminalAgentRegistration>;
  refresh: () => void;
} => {
  const [registrations, setRegistrations] = useState<Array<TerminalAgentRegistration>>([]);

  const refresh = useCallback((): void => {
    // Plain read: skip the request tracker's WS-ack wait (this endpoint
    // never publishes a stream update to acknowledge).
    listTerminalAgentRegistrations({ meta: { skipWsAck: true } })
      .then((response) => {
        setRegistrations(response.data?.registrations ?? []);
      })
      .catch((error: unknown) => {
        console.error("Failed to load terminal-agent registrations:", error);
      });
  }, []);

  return { registrations, refresh };
};
