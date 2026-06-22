import { Badge, Box, Flex, Spinner, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { type ReactElement, useMemo, useState } from "react";

import type { AuthenticatedProviderEntry } from "~/api";
import { ElementIds, ProviderGroup } from "~/api";
import { getProviderDisplayName } from "~/common/modelConstants";
import { piAuthenticatedProvidersAtom } from "~/common/state/atoms/piAuthenticatedProviders";

import { groupProviders, isAuthenticated } from "./piProvidersGrouping.ts";

const SESSION_ONLY_EXPLAINER = "Works this session via environment variables; full standalone persistence is deferred.";

const displayNameFor = (provider: AuthenticatedProviderEntry): string =>
  provider.displayName || getProviderDisplayName(provider.providerId);

const StatusDot = ({ color }: { color: string }): ReactElement => (
  <Box
    style={{
      width: "8px",
      height: "8px",
      borderRadius: "var(--radius-full)",
      backgroundColor: color,
      flexShrink: 0,
    }}
  />
);

const dotColorFor = (provider: AuthenticatedProviderEntry): string => {
  if (provider.group === ProviderGroup.SESSION_ONLY) {
    return provider.envDetected ? "var(--amber-9)" : "var(--gray-6)";
  }
  return isAuthenticated(provider) ? "var(--green-9)" : "var(--gray-8)";
};

const ProviderRow = ({
  provider,
  isSelected,
  onSelect,
}: {
  provider: AuthenticatedProviderEntry;
  isSelected: boolean;
  onSelect: (providerId: string) => void;
}): ReactElement => (
  <Flex
    align="center"
    gap="2"
    px="2"
    py="1"
    onClick={() => onSelect(provider.providerId)}
    data-testid={`${ElementIds.PI_PROVIDER_ROW}-${provider.providerId}`}
    style={{
      cursor: "pointer",
      borderRadius: "var(--radius-2)",
      backgroundColor: isSelected ? "var(--gray-4)" : undefined,
    }}
  >
    <StatusDot color={dotColorFor(provider)} />
    <Text size="2">{displayNameFor(provider)}</Text>
  </Flex>
);

const RailGroup = ({
  title,
  testId,
  providers,
  selectedId,
  onSelect,
}: {
  title: string;
  testId: string;
  providers: ReadonlyArray<AuthenticatedProviderEntry>;
  selectedId: string | null;
  onSelect: (providerId: string) => void;
}): ReactElement | null => {
  if (providers.length === 0) {
    return null;
  }
  return (
    <Flex direction="column" gap="1" mb="3" data-testid={testId}>
      <Text size="1" weight="bold" color="gray" style={{ textTransform: "uppercase", letterSpacing: "0.04em" }}>
        {title}
      </Text>
      {providers.map((provider) => (
        <ProviderRow
          key={provider.providerId}
          provider={provider}
          isSelected={provider.providerId === selectedId}
          onSelect={onSelect}
        />
      ))}
    </Flex>
  );
};

const ConnectedSource = ({ provider }: { provider: AuthenticatedProviderEntry }): ReactElement => {
  if (provider.inAuthJson) {
    return (
      <Text size="2" color="gray">
        Imported from ~/.pi/agent/auth.json
      </Text>
    );
  }
  return (
    <Text size="2" color="gray">
      Detected via environment variable {provider.envVarNames[0] ?? "—"}
    </Text>
  );
};

const ProviderDetail = ({ provider }: { provider: AuthenticatedProviderEntry }): ReactElement => {
  const isSessionOnly = provider.group === ProviderGroup.SESSION_ONLY;
  const isConnected = isAuthenticated(provider);
  return (
    <Flex direction="column" gap="3" data-testid={ElementIds.PI_PROVIDER_DETAIL}>
      <Flex align="center" gap="2">
        <Text weight="medium">{displayNameFor(provider)}</Text>
        <Badge color={isSessionOnly ? "amber" : "gray"} variant="soft">
          {isSessionOnly ? "Session-only" : "Single-key"}
        </Badge>
      </Flex>

      <Box data-testid={ElementIds.PI_PROVIDER_DETAIL_STATUS}>
        {isSessionOnly ? (
          <Flex direction="column" gap="1">
            <Text size="2" color={provider.envDetected ? "green" : "gray"}>
              {provider.envDetected ? "Active this session (environment variables)" : "Not configured"}
            </Text>
            <Text size="2" color="gray">
              {SESSION_ONLY_EXPLAINER}
            </Text>
          </Flex>
        ) : isConnected ? (
          <Flex direction="column" gap="1">
            <Text size="2" color="green">
              Connected
            </Text>
            <ConnectedSource provider={provider} />
          </Flex>
        ) : (
          <Text size="2" color="gray">
            Not connected
          </Text>
        )}
      </Box>

      <Text size="2" color="gray">
        Unlocks {displayNameFor(provider)} models
      </Text>

      {/* Mount point for Authenticate/Disconnect, the inline login terminal, and the
          paste-key form added in later tasks. Session-only providers carry no auth
          actions (their persistence is deferred). */}
      {!isSessionOnly && <Box data-testid={ElementIds.PI_PROVIDER_ACTIONS} />}
    </Flex>
  );
};

export const PiProvidersArea = (): ReactElement => {
  const providersLoadable = useAtomValue(piAuthenticatedProvidersAtom);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const providers = useMemo(
    () => (providersLoadable.state === "hasData" ? providersLoadable.data : []),
    [providersLoadable],
  );
  const grouping = useMemo(() => groupProviders(providers), [providers]);
  const orderedProviders = useMemo(
    () => [...grouping.connected, ...grouping.available, ...grouping.sessionOnly],
    [grouping],
  );

  const defaultId = grouping.connected[0]?.providerId ?? orderedProviders[0]?.providerId ?? null;
  const effectiveId =
    selectedId !== null && providers.some((provider) => provider.providerId === selectedId) ? selectedId : defaultId;
  const selected = providers.find((provider) => provider.providerId === effectiveId) ?? null;

  return (
    <Flex direction="column" gap="2" py="4">
      <Text weight="medium">Providers</Text>
      <Text size="2" color="gray">
        Authenticate the LLM providers that pi supports. Connected providers are imported from your existing pi
        credentials.
      </Text>

      {providersLoadable.state === "loading" ? (
        <Spinner size="1" />
      ) : providers.length === 0 ? (
        <Text size="2" color="gray">
          No providers available.
        </Text>
      ) : (
        <Flex gap="5" mt="2" align="start">
          <Box width="240px" flexShrink="0" data-testid={ElementIds.PI_PROVIDERS_RAIL}>
            <RailGroup
              title="Connected"
              testId={ElementIds.PI_PROVIDERS_GROUP_CONNECTED}
              providers={grouping.connected}
              selectedId={effectiveId}
              onSelect={setSelectedId}
            />
            <RailGroup
              title="Available"
              testId={ElementIds.PI_PROVIDERS_GROUP_AVAILABLE}
              providers={grouping.available}
              selectedId={effectiveId}
              onSelect={setSelectedId}
            />
            <RailGroup
              title="Session-only"
              testId={ElementIds.PI_PROVIDERS_GROUP_SESSION_ONLY}
              providers={grouping.sessionOnly}
              selectedId={effectiveId}
              onSelect={setSelectedId}
            />
          </Box>
          <Box flexGrow="1">{selected !== null && <ProviderDetail provider={selected} />}</Box>
        </Flex>
      )}
    </Flex>
  );
};
