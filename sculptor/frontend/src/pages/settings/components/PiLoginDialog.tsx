import { Cross1Icon } from "@radix-ui/react-icons";
import { Button, Dialog, Flex, IconButton, Spinner, Text } from "@radix-ui/themes";
import { type ReactElement, useCallback, useEffect, useState } from "react";

import { ElementIds, finishPiLogin, startPiLogin } from "~/api";

import { PiLoginTerminal } from "./PiLoginTerminal.tsx";
import { PiPasteKeyForm } from "./PiPasteKeyForm.tsx";

/** What the Providers area hands the modal: which provider, which direction, and
 *  whether a single-key paste path is offered. `providerId` is null for the
 *  empty-state "Authenticate a provider" CTA (pi's own TUI picks the provider). */
export type PiLoginRequestView = {
  providerId: string | null;
  displayName: string;
  mode: "login" | "logout";
  canPasteKey: boolean;
};

type DialogView = "chooser" | "terminal" | "paste";

type PiLoginDialogProps = {
  request: PiLoginRequestView;
  /** Called after the session is torn down; the parent clears the request and refetches. */
  onClose: () => void;
};

/**
 * Centered modal hosting the interactive pi /login (or /logout) session. Login opens
 * to a chooser ("Open pi login" terminal vs. "Paste API key instead"); logout starts
 * the /logout terminal immediately. While the terminal is live, Escape and
 * outside-clicks are suppressed (Escape is a keystroke pi consumes) — the user leaves
 * via Done, which tears the PTY down. pi writes ~/.pi/agent/auth.json itself.
 */
export const PiLoginDialog = ({ request, onClose }: PiLoginDialogProps): ReactElement => {
  const [view, setView] = useState<DialogView>(request.mode === "logout" ? "terminal" : "chooser");
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

  // pi /logout has no chooser — kick off its interactive terminal as soon as the modal
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

  const isLogin = request.mode === "login";
  const title = isLogin ? `Authenticate ${request.displayName}` : `Disconnect ${request.displayName}`;
  const verb = isLogin ? "authenticate" : "log out";
  const terminalGuidance =
    request.providerId === null
      ? "Select a provider in the pi login screen below, then click Done."
      : `In the pi selector below, choose ${request.displayName} to ${verb}, then click Done.`;

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

        {view === "chooser" && (
          <Flex direction="column" gap="3">
            <Text size="2" color="gray">
              Opening pi login launches an interactive session; pi writes the credential to ~/.pi/agent/auth.json
              itself. One path covers both API-key and OAuth/subscription providers.
            </Text>
            <Flex gap="2" wrap="wrap">
              <Button
                variant="solid"
                onClick={() => void startSession()}
                data-testid={ElementIds.PI_PROVIDER_AUTHENTICATE_BUTTON}
              >
                Open pi login
              </Button>
              {request.canPasteKey && request.providerId !== null && (
                <Button
                  variant="soft"
                  onClick={() => setView("paste")}
                  data-testid={ElementIds.PI_PROVIDER_PASTE_KEY_SWITCH}
                >
                  Paste API key instead
                </Button>
              )}
            </Flex>
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

        {view === "paste" && request.providerId !== null && (
          <Flex direction="column" gap="3">
            <Text size="2" color="gray">
              Paste an API key for {request.displayName}. Written merge-safe to ~/.pi/agent/auth.json.
            </Text>
            <PiPasteKeyForm providerId={request.providerId} onSaved={() => void teardown()} />
            <Button variant="ghost" size="1" style={{ alignSelf: "flex-start" }} onClick={() => setView("chooser")}>
              ← Back to pi login
            </Button>
          </Flex>
        )}
      </Dialog.Content>
    </Dialog.Root>
  );
};
