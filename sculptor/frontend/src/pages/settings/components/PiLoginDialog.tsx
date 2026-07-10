import { Cross1Icon } from "@radix-ui/react-icons";
import { Dialog, Flex, IconButton, Spinner, Text } from "@radix-ui/themes";
import { type ReactElement, useCallback, useEffect, useState } from "react";

import { ElementIds, finishPiLogin, getPiLoginStatus, startPiLogin } from "~/api";

import { PiLoginTerminal } from "./PiLoginTerminal.tsx";

/** How often the open modal polls for pi having performed the credential change, so it
 *  auto-closes (and the Providers area refetches) without a manual Done. */
const PI_LOGIN_STATUS_POLL_INTERVAL_MS = 1200;

/** What the Providers area hands the modal: which provider and which direction.
 *  `providerId` is null for the empty-state "Authenticate a provider" CTA (pi's own
 *  TUI picks the provider). */
export type PiLoginRequestView = {
  providerId: string | null;
  displayName: string;
  mode: "login" | "logout";
};

type PiLoginDialogProps = {
  request: PiLoginRequestView;
  /** Called after the session is torn down; the parent clears the request and refetches. */
  onClose: () => void;
};

/**
 * Centered modal hosting the interactive pi /login (or /logout) session, which starts
 * as soon as the modal mounts. While the terminal is live, Escape and outside-clicks
 * are suppressed (Escape is a keystroke pi consumes) — the user leaves via Done, which
 * tears the PTY down. pi writes ~/.pi/agent/auth.json itself.
 */
export const PiLoginDialog = ({ request, onClose }: PiLoginDialogProps): ReactElement => {
  const [activeLoginId, setActiveLoginId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  // Kick off the interactive terminal as soon as the modal mounts (the parent remounts
  // the dialog per request, so this fires once per open). A session that resolves after
  // the effect is torn down (dialog closed, or a StrictMode remount) is never adopted,
  // so reap its PTY instead of leaking it.
  useEffect(() => {
    let isActive = true;
    void (async (): Promise<void> => {
      try {
        const response = await startPiLogin({
          body: { mode: request.mode, providerId: request.providerId ?? undefined },
          meta: { skipWsAck: true },
        });
        if (!response.data) {
          return;
        }

        if (isActive) {
          setActiveLoginId(response.data.loginId);
        } else {
          await finishPiLogin({ path: { login_id: response.data.loginId }, meta: { skipWsAck: true } });
        }
      } catch {
        if (isActive) {
          setErrorMessage("Could not start the pi session. Check that pi is installed in Settings → Pi.");
        }
      }
    })();

    return (): void => {
      isActive = false;
    };
  }, [request.mode, request.providerId]);

  const teardown = useCallback(async (): Promise<void> => {
    const loginId = activeLoginId;
    setActiveLoginId(null);
    if (loginId !== null) {
      try {
        await finishPiLogin({ path: { login_id: loginId }, meta: { skipWsAck: true } });
      } catch {
        // Best-effort teardown; the PTY is also reaped on WebSocket close.
      }
    }
    onClose();
  }, [activeLoginId, onClose]);

  // Auto-advance: while the terminal is live, poll the backend for pi having performed
  // the credential change (provider added on login / removed on logout). On completion
  // the modal closes and the Providers area refetches — no manual Done.
  useEffect(() => {
    if (activeLoginId === null) {
      return;
    }
    let isCancelled = false;
    const interval = window.setInterval(() => {
      void (async (): Promise<void> => {
        try {
          const response = await getPiLoginStatus({ path: { login_id: activeLoginId }, meta: { skipWsAck: true } });
          if (!isCancelled && response.data?.completed === true) {
            isCancelled = true;
            window.clearInterval(interval);
            void teardown();
          }
        } catch {
          // Transient (e.g. the session is briefly not found) — keep polling until teardown.
        }
      })();
    }, PI_LOGIN_STATUS_POLL_INTERVAL_MS);
    return (): void => {
      isCancelled = true;
      window.clearInterval(interval);
    };
  }, [activeLoginId, teardown]);

  const isLogin = request.mode === "login";
  const title = isLogin ? `Authenticate ${request.displayName}` : `Disconnect ${request.displayName}`;
  const terminalGuidance = isLogin
    ? request.providerId === null
      ? "Select a provider in the pi login screen below and complete sign-in. This window closes automatically when done."
      : `Choose ${request.displayName} in the pi login screen below and complete sign-in. This window closes automatically when done.`
    : `Disconnecting ${request.displayName} from pi — this window closes automatically when done.`;

  return (
    <Dialog.Root open onOpenChange={(open) => !open && void teardown()}>
      <Dialog.Content
        maxWidth="640px"
        data-testid={ElementIds.PI_LOGIN_DIALOG}
        onEscapeKeyDown={(event) => activeLoginId !== null && event.preventDefault()}
        onPointerDownOutside={(event) => activeLoginId !== null && event.preventDefault()}
      >
        <Flex align="center" gap="3" mb="3">
          <Dialog.Title size="3" mb="0" style={{ flexGrow: 1 }}>
            {title}
          </Dialog.Title>
          <Dialog.Close>
            <IconButton variant="ghost" color="gray" aria-label="Close">
              <Cross1Icon />
            </IconButton>
          </Dialog.Close>
        </Flex>

        {errorMessage !== null ? (
          <Text size="2" color="red">
            {errorMessage}
          </Text>
        ) : activeLoginId !== null ? (
          <Flex direction="column" gap="2" data-testid={ElementIds.PI_PROVIDER_ACTIONS}>
            <Text size="2" color="gray">
              {terminalGuidance}
            </Text>
            <PiLoginTerminal loginId={activeLoginId} onDone={() => void teardown()} />
          </Flex>
        ) : (
          <Flex align="center" justify="center" p="5">
            <Spinner />
          </Flex>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};
