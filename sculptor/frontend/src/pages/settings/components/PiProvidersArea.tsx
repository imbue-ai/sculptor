import { ExclamationTriangleIcon, LockClosedIcon, PlusIcon } from "@radix-ui/react-icons";
import { Box, Button, Callout, Code, Flex, Spinner, Text } from "@radix-ui/themes";
import { type ReactElement, type ReactNode, useCallback, useMemo, useState } from "react";

import type { AuthenticatedProviderEntry } from "~/api";
import { ElementIds } from "~/api";
import { getProviderDisplayName } from "~/common/modelConstants";
import { usePiAuthenticatedProviders } from "~/common/state/hooks/usePiAuthenticatedProviders";
import { BlandCircle } from "~/components/PulsingCircle.tsx";

import { PiLoginDialog, type PiLoginRequestView } from "./PiLoginDialog.tsx";
import styles from "./PiProvidersArea.module.scss";
import { groupProviders } from "./piProvidersGrouping.ts";

const displayNameFor = (provider: AuthenticatedProviderEntry): string =>
  provider.displayName || getProviderDisplayName(provider.providerId);

const SectionEyebrow = ({ children }: { children: ReactNode }): ReactElement => (
  <Text size="1" weight="bold" color="gray" style={{ textTransform: "uppercase", letterSpacing: "0.06em" }}>
    {children}
  </Text>
);

const ProviderMark = ({ provider, size }: { provider: AuthenticatedProviderEntry; size: number }): ReactElement => (
  <Flex
    align="center"
    justify="center"
    flexShrink="0"
    style={{
      width: `${size}px`,
      height: `${size}px`,
      borderRadius: "var(--radius-3)",
      border: "1px solid var(--gray-6)",
      backgroundColor: "var(--gray-3)",
      fontWeight: 600,
      fontSize: `${Math.round(size * 0.42)}px`,
      textTransform: "uppercase",
    }}
  >
    {displayNameFor(provider).charAt(0)}
  </Flex>
);

/** A first-class card for an authenticated provider. auth.json-backed providers can
 *  be disconnected via pi /logout; env-detected-only providers can't (no entry to
 *  remove), so they show how to clear the variable instead. */
const ConnectedCard = ({
  provider,
  onDisconnect,
}: {
  provider: AuthenticatedProviderEntry;
  onDisconnect: (provider: AuthenticatedProviderEntry) => void;
}): ReactElement => {
  const canDisconnect = provider.inAuthJson;
  return (
    <Box
      data-testid={`${ElementIds.PI_PROVIDER_CARD}-${provider.providerId}`}
      style={{
        border: "1px solid var(--gray-5)",
        borderRadius: "var(--radius-4)",
        backgroundColor: "var(--gray-1)",
        padding: "var(--space-4)",
      }}
    >
      <Flex align="center" gap="3">
        <ProviderMark provider={provider} size={32} />
        <Text weight="medium" style={{ flexGrow: 1, minWidth: 0 }}>
          {displayNameFor(provider)}
        </Text>
        <Flex align="center" gap="2" flexShrink="0">
          <BlandCircle size={8} className={styles.connectedDot} />
          <Text size="2" color="green">
            Connected
          </Text>
        </Flex>
        {canDisconnect && (
          <Button
            variant="soft"
            color="red"
            onClick={() => onDisconnect(provider)}
            data-testid={`${ElementIds.PI_PROVIDER_DISCONNECT_BUTTON}-${provider.providerId}`}
          >
            Disconnect
          </Button>
        )}
      </Flex>
      {!canDisconnect && (
        <Text size="1" color="gray" mt="2" style={{ display: "block" }}>
          Connected via environment variable {provider.envVarNames[0] ?? "—"} — clear that variable to disconnect.
        </Text>
      )}
    </Box>
  );
};

/** A tidy grid cell for an unauthenticated single-key provider; clicking opens the
 *  login modal. */
const AddProviderCell = ({
  provider,
  onAdd,
}: {
  provider: AuthenticatedProviderEntry;
  onAdd: (provider: AuthenticatedProviderEntry) => void;
}): ReactElement => (
  <Flex
    align="center"
    gap="3"
    px="3"
    py="2"
    onClick={() => onAdd(provider)}
    data-testid={`${ElementIds.PI_PROVIDER_ADD_CELL}-${provider.providerId}`}
    style={{
      cursor: "pointer",
      border: "1px solid var(--gray-5)",
      borderRadius: "var(--radius-3)",
      backgroundColor: "var(--gray-1)",
    }}
  >
    <ProviderMark provider={provider} size={28} />
    <Text weight="medium" size="2" style={{ flexGrow: 1, minWidth: 0 }}>
      {displayNameFor(provider)}
    </Text>
    <PlusIcon style={{ color: "var(--indigo-11)", width: 18, height: 18 }} aria-hidden />
  </Flex>
);

/** Multi-value providers usable this session via env vars, but whose full standalone
 *  persistence is deferred — surfaced as one explainer callout. */
const SessionOnlyCallout = ({ providers }: { providers: ReadonlyArray<AuthenticatedProviderEntry> }): ReactElement => (
  <Callout.Root color="amber" data-testid={ElementIds.PI_PROVIDERS_GROUP_SESSION_ONLY}>
    <Callout.Icon>
      <ExclamationTriangleIcon />
    </Callout.Icon>
    <Callout.Text>
      <Text weight="bold">{providers.map(displayNameFor).join(", ")}</Text> need endpoint/region configuration from
      environment variables. They work for this session, but full standalone persistence is deferred to a later release.
    </Callout.Text>
  </Callout.Root>
);

const ConnectFirstHero = ({ onAuthenticate }: { onAuthenticate: () => void }): ReactElement => (
  <Box
    style={{
      border: "1px solid var(--gray-5)",
      borderRadius: "var(--radius-4)",
      backgroundColor: "var(--gray-1)",
    }}
  >
    <Flex direction="column" align="center" gap="3" py="6" px="5" style={{ textAlign: "center" }}>
      <LockClosedIcon width="26" height="26" color="var(--gray-8)" />
      <Text size="4" weight="medium">
        Connect your first provider
      </Text>
      <Text size="2" color="gray" style={{ maxWidth: "420px" }}>
        You have not authenticated any LLM providers yet. Connect one to start using pi — Sculptor opens an interactive
        pi /login and pi stores the credential.
      </Text>
      <Button variant="solid" onClick={onAuthenticate}>
        Authenticate a provider
      </Button>
    </Flex>
  </Box>
);

export const PiProvidersArea = (): ReactElement => {
  const { providers, isPending, refetch } = usePiAuthenticatedProviders();
  const [loginRequest, setLoginRequest] = useState<PiLoginRequestView | null>(null);

  const grouping = useMemo(() => groupProviders(providers), [providers]);

  const openLogin = useCallback((provider: AuthenticatedProviderEntry): void => {
    setLoginRequest({
      providerId: provider.providerId,
      displayName: displayNameFor(provider),
      mode: "login",
    });
  }, []);

  const openLogout = useCallback((provider: AuthenticatedProviderEntry): void => {
    setLoginRequest({
      providerId: provider.providerId,
      displayName: displayNameFor(provider),
      mode: "logout",
    });
  }, []);

  const openAgnosticLogin = useCallback((): void => {
    setLoginRequest({ providerId: null, displayName: "a provider", mode: "login" });
  }, []);

  const handleDialogClose = useCallback((): void => {
    setLoginRequest(null);
    // Refetch so a newly connected/disconnected provider moves between sections; the
    // picker is refreshed separately by the backend's login-teardown broadcast.
    void refetch();
  }, [refetch]);

  return (
    <Flex direction="column" gap="4" py="4">
      <Flex direction="column" gap="1">
        <Text weight="medium">Providers</Text>
        <Text size="2" color="gray">
          Authenticate the LLM providers that pi supports. The list of connected providers is synced with{" "}
          <Code>~/.pi/agent/auth.json</Code>.
        </Text>
      </Flex>

      {isPending ? (
        <Spinner size="1" />
      ) : providers.length === 0 ? (
        <Text size="2" color="gray">
          No providers available.
        </Text>
      ) : (
        <>
          {grouping.connected.length > 0 ? (
            <Flex direction="column" gap="2" data-testid={ElementIds.PI_PROVIDERS_GROUP_CONNECTED}>
              <SectionEyebrow>Connected · {grouping.connected.length}</SectionEyebrow>
              {grouping.connected.map((provider) => (
                <ConnectedCard key={provider.providerId} provider={provider} onDisconnect={openLogout} />
              ))}
            </Flex>
          ) : (
            <ConnectFirstHero onAuthenticate={openAgnosticLogin} />
          )}

          {grouping.available.length > 0 && (
            <Flex direction="column" gap="2" data-testid={ElementIds.PI_PROVIDERS_GROUP_AVAILABLE}>
              <SectionEyebrow>{grouping.connected.length > 0 ? "Add a provider" : "Or add directly"}</SectionEyebrow>
              <Box style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: "var(--space-2)" }}>
                {grouping.available.map((provider) => (
                  <AddProviderCell key={provider.providerId} provider={provider} onAdd={openLogin} />
                ))}
              </Box>
            </Flex>
          )}

          {grouping.sessionOnly.length > 0 && <SessionOnlyCallout providers={grouping.sessionOnly} />}
        </>
      )}

      {loginRequest !== null && <PiLoginDialog request={loginRequest} onClose={handleDialogClose} />}
    </Flex>
  );
};
