import { Cross1Icon } from "@radix-ui/react-icons";
import { Button, Dialog, Flex, IconButton, Spinner, Text } from "@radix-ui/themes";
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

type DialogView = "intro" | "terminal";

type PiLoginDialogProps = {
  request: PiLoginRequestView;
  /** Called after the session is torn down; the parent clears the request and refetches. */
  onClose: () => void;
};

/**
 * Centered modal hosting the interactive pi /login (or /logout) session. Login shows a
 * short intro whose single "Open pi login" action launches the terminal; logout starts
 * the /logout terminal immediately. While the terminal is live, Escape and
 * outside-clicks are suppressed (Escape is a keystroke pi consumes) — the user leaves
 * via Done, which tears the PTY down. pi writes ~/.pi/agent/auth.json itself.
 */
export const PiLoginDialog = ({ request, onClose }: PiLoginDialogProps): ReactElement => {
  const [view, setView] = useState<DialogView>(request.mode === "logout" ? "terminal" : "intro");
  const [activeLoginId, setActiveLoginId] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const startSession = useCallback(async (): Promise<void> => {
    setErrorMessage(null);
    try {
      const response = await startPiLogin({
        body: { mode: request.mode, providerId: request.providerId ?? undefined },
        meta: { skipWsAck: true },
      });
      if (response.data) {
        setActiveLoginId(response.data.loginId);
        setView("terminal");
      }
    } catch {
      setErrorMessage("Could not start the pi session. Check that pi is installed in Settings → Pi.");
    }
  }, [request]);

  // pi /logout has no intro step — kick off its interactive terminal as soon as the modal
  // mounts (the parent remounts the dialog per request, so this fires once per open).
  useEffect(() => {
    if (request.mode !== "logout") {
      return;
    }

    let isActive = true;
    void (async (): Promise<void> => {
      try {
        const response = await startPiLogin({
          body: { mode: "logout", providerId: request.providerId ?? undefined },
          meta: { skipWsAck: true },
        });
        if (isActive && response.data) {
          setActiveLoginId(response.data.loginId);
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
    if (view !== "terminal" || activeLoginId === null) {
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
  }, [view, activeLoginId, teardown]);

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
        onEscapeKeyDown={(event) => view === "terminal" && event.preventDefault()}
        onPointerDownOutside={(event) => view === "terminal" && event.preventDefault()}
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

        {view === "intro" && (
          <Flex direction="column" gap="3">
            <Text size="2" color="gray">
              Continue your login with a Pi interactive session
            </Text>
            <Button
              variant="solid"
              onClick={() => void startSession()}
              data-testid={ElementIds.PI_PROVIDER_AUTHENTICATE_BUTTON}
              style={{ alignSelf: "flex-start" }}
            >
              Open pi login
            </Button>
            {errorMessage !== null && (
              <Text size="2" color="red">
                {errorMessage}
              </Text>
            )}
          </Flex>
        )}

        {view === "terminal" &&
          (activeLoginId !== null ? (
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
          ))}
      </Dialog.Content>
    </Dialog.Root>
  );
};
