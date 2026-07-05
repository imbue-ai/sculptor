import { Button, Flex, IconButton, Popover, Switch, Text } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { X } from "lucide-react";
import type { ReactElement } from "react";

import { ElementIds } from "~/api";
import { useInstallUpdate } from "~/app/hooks/useInstallUpdate.ts";
import { getUpdateChannelDisplayName, getUpdateStatusText } from "~/common/autoUpdateUtils.ts";
import { autoUpdateStatusAtom, updateChannelAtom } from "~/common/state/atoms/autoUpdate.ts";
import { healthCheckDataAtom } from "~/common/state/atoms/backend.ts";
import { useDevPanel } from "~/common/state/hooks/useDevPanel.ts";

import { useReactGrab } from "../../components/devPanel/hooks/useReactGrab.ts";
import { useTanstackDevtools } from "../../components/devPanel/hooks/useTanstackDevtools.ts";
import { useTanstackEventLog } from "../../components/devPanel/hooks/useTanstackEventLog.ts";
import styles from "./VersionPopover.module.scss";

type InfoRowProps = {
  label: string;
  value: string | undefined;
  testId?: string;
};

const InfoRow = ({ label, value, testId }: InfoRowProps): ReactElement => (
  <Flex justify="between" gap="4">
    <Text size="1" color="gray">
      {label}
    </Text>
    <Text size="1" className={styles.value} data-testid={testId}>
      {value ?? "—"}
    </Text>
  </Flex>
);

const SECONDS_PER_HOUR = 3600;
const SECONDS_PER_MINUTE = 60;

const formatDiskSpace = (gb: number | undefined): string | undefined => {
  if (gb === undefined) {
    return undefined;
  }
  return `${gb.toFixed(1)} GB`;
};

const formatUptime = (seconds: number | undefined): string | undefined => {
  if (seconds === undefined) {
    return undefined;
  }
  const hours = Math.floor(seconds / SECONDS_PER_HOUR);
  const minutes = Math.floor((seconds % SECONDS_PER_HOUR) / SECONDS_PER_MINUTE);
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
};

export const VersionPopover = (): ReactElement => {
  const healthCheckData = useAtomValue(healthCheckDataAtom);
  const autoUpdateStatus = useAtomValue(autoUpdateStatusAtom);
  const updateChannel = useAtomValue(updateChannelAtom);
  const { isDevPanelOpen, showDevPanel, hideDevPanel } = useDevPanel();
  const reactGrab = useReactGrab();
  const tanstackDevtools = useTanstackDevtools();
  const tanstackEventLog = useTanstackEventLog();
  const { install, isInstalling } = useInstallUpdate();

  return (
    <Popover.Root open={isDevPanelOpen} onOpenChange={(open) => (open ? showDevPanel() : hideDevPanel())}>
      <Popover.Trigger>
        <Text data-testid={ElementIds.VERSION} className={styles.trigger}>
          {healthCheckData?.version}
          {(autoUpdateStatus?.type === "ready" || autoUpdateStatus?.type === "downloading") && (
            <span className={styles.updateDot} data-testid={ElementIds.UPDATE_DOT} />
          )}
        </Text>
      </Popover.Trigger>
      <Popover.Content
        className={styles.content}
        side="top"
        align="end"
        sideOffset={8}
        data-testid={ElementIds.VERSION_POPOVER_CONTENT}
      >
        <Flex direction="column" gap="3">
          <Flex justify="between" align="center">
            <Text size="2" weight="medium">
              Version Details
            </Text>
            <Popover.Close>
              <IconButton variant="ghost" size="1" className={styles.closeButton}>
                <X size={14} />
              </IconButton>
            </Popover.Close>
          </Flex>
          <Flex direction="column" gap="2" className={styles.details}>
            <InfoRow label="Version" value={healthCheckData?.version} />
            <InfoRow label="Git SHA" value={healthCheckData?.gitSha} />
            {healthCheckData?.ciJobId && <InfoRow label="CI Job" value={healthCheckData.ciJobId} />}
            {healthCheckData?.ciRef && <InfoRow label="Source" value={healthCheckData.ciRef} />}
          </Flex>
          <Text size="2" weight="medium" mt="1">
            Updates
          </Text>
          <Flex direction="column" gap="2" className={styles.details}>
            <InfoRow
              label="Channel"
              value={updateChannel ? getUpdateChannelDisplayName(updateChannel) : undefined}
              testId={ElementIds.VERSION_POPOVER_CHANNEL}
            />
            <InfoRow
              label="Status"
              value={getUpdateStatusText(autoUpdateStatus, updateChannel, healthCheckData?.version)}
              testId={ElementIds.VERSION_POPOVER_STATUS}
            />
            {autoUpdateStatus?.type === "ready" && (
              <Button
                size="1"
                variant="soft"
                disabled={isInstalling}
                onClick={install}
                data-testid={ElementIds.VERSION_POPOVER_RESTART_BUTTON}
              >
                {isInstalling ? "Restarting..." : "Install and restart"}
              </Button>
            )}
          </Flex>
          <Text size="2" weight="medium" mt="1">
            Diagnostics
          </Text>
          <Flex direction="column" gap="2" className={styles.details}>
            <InfoRow
              label="Platform"
              value={healthCheckData ? `${healthCheckData.platform} ${healthCheckData.platformVersion}` : undefined}
            />
            <InfoRow label="Uptime" value={formatUptime(healthCheckData?.uptimeSeconds)} />
            <InfoRow label="Active Agents" value={healthCheckData?.activeTaskCount?.toString()} />
            <InfoRow label="Free Disk" value={formatDiskSpace(healthCheckData?.freeDiskGb)} />
            <InfoRow label="Data Directory" value={healthCheckData?.dataDirectory} />
            <InfoRow label="Install Mode" value={healthCheckData?.installMode} />
            <InfoRow label="Install Path" value={healthCheckData?.installPath} />
            <InfoRow
              label="Claude CLI"
              value={healthCheckData?.dependenciesStatus?.claude?.version ?? undefined}
              testId={ElementIds.CLAUDE_CLI_VERSION_POPOVER}
            />
            <InfoRow label="Claude Path" value={healthCheckData?.dependenciesStatus?.claude?.path ?? undefined} />
            <InfoRow
              label="Claude Mode"
              value={healthCheckData?.dependenciesStatus?.claude?.mode ?? undefined}
              testId={ElementIds.CLAUDE_CLI_MODE_POPOVER}
            />
          </Flex>
          <Text size="2" weight="medium" mt="1">
            Dev Tools
          </Text>
          <Flex direction="column" gap="2" className={styles.details}>
            <Flex justify="between" align="center" gap="4">
              <Text size="1" color="gray">
                React Grab
              </Text>
              <Switch size="1" checked={reactGrab.isEnabled} onCheckedChange={reactGrab.handleCheckedChange} />
            </Flex>
            <Flex justify="between" align="center" gap="4">
              <Text size="1" color="gray">
                TanStack Devtools
              </Text>
              <Switch
                size="1"
                checked={tanstackDevtools.isEnabled}
                onCheckedChange={tanstackDevtools.handleCheckedChange}
                data-testid={ElementIds.VERSION_POPOVER_TANSTACK_DEVTOOLS_SWITCH}
              />
            </Flex>
            <Flex justify="between" align="center" gap="4">
              <Text size="1" color="gray">
                TanStack event log
              </Text>
              <Switch
                size="1"
                checked={tanstackEventLog.isEnabled}
                onCheckedChange={tanstackEventLog.handleCheckedChange}
              />
            </Flex>
          </Flex>
        </Flex>
      </Popover.Content>
    </Popover.Root>
  );
};
