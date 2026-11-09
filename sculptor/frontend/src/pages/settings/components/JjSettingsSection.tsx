import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import { Box, Button, Flex, Link, Progress, Select, Spinner, Text, TextField } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { type ReactElement, useCallback, useEffect, useState } from "react";

import type { JjIdentity } from "../../../api";
import { ElementIds, getDependenciesStatus, setJjIdentity, UserConfigField } from "../../../api";
import { dependenciesStatusAtom } from "../../../common/state/atoms/dependenciesStatus";
import { jjSnapshotMaxNewFileSizeMibAtom } from "../../../common/state/atoms/userConfig";
import { useManagedDependency } from "../hooks/useManagedDependency";
import { JjAvailabilityCallout } from "./JjAvailabilityCallout.tsx";
import { JjIdentityRow } from "./JjIdentityRow.tsx";
import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";

const JJ_DOCS_URL = "https://jj-vcs.github.io/jj/latest/";
const MIN_SNAPSHOT_SIZE_MIB = 1;
const MAX_SNAPSHOT_SIZE_MIB = 1024;

type JjSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const JjSettingsSection = ({ onSettingChange }: JjSettingsSectionProps): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  const snapshotSizeMib = useAtomValue(jjSnapshotMaxNewFileSizeMibAtom);

  // Reset the draft when the saved value changes, during render rather than in an effect.
  const [snapshotSizeValue, setSnapshotSizeValue] = useState(String(snapshotSizeMib));
  const [prevSnapshotSizeMib, setPrevSnapshotSizeMib] = useState(snapshotSizeMib);
  if (prevSnapshotSizeMib !== snapshotSizeMib) {
    setPrevSnapshotSizeMib(snapshotSizeMib);
    setSnapshotSizeValue(String(snapshotSizeMib));
  }
  const [isRechecking, setIsRechecking] = useState(false);

  const {
    info: jj,
    displayMode,
    isModeSettling,
    handleModeChange,
    isInstalling,
    handleInstall,
    installProgress,
    progressPercent,
    isManagedUpToDate,
    effectiveInstallError,
    customPathInput,
    setCustomPathInput,
    handleApplyCustomPath,
  } = useManagedDependency({ tool: "JJ", onSettingChange });

  // skipWsAck: the dependencies endpoints open no data-model transaction, so no WS
  // acknowledgment ever follows.
  const refreshStatus = useCallback(async (): Promise<void> => {
    try {
      const { data } = await getDependenciesStatus({ meta: { skipWsAck: true } });
      if (data) setDependenciesStatus(data);
    } catch {
      // Best-effort; the stream keeps delivering status.
    }
  }, [setDependenciesStatus]);

  // Identity and PATH changes made outside Sculptor send no event, so check again
  // whenever the page opens.
  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const handleRecheck = async (): Promise<void> => {
    setIsRechecking(true);
    await refreshStatus();
    setIsRechecking(false);
  };

  const saveIdentity = useCallback(
    async (identity: JjIdentity): Promise<void> => {
      const { data } = await setJjIdentity({ body: identity, meta: { skipWsAck: true } });
      if (data) setDependenciesStatus(data);
    },
    [setDependenciesStatus],
  );

  const handleSnapshotSizeBlur = (): void => {
    const parsed = parseInt(snapshotSizeValue, 10);
    if (isNaN(parsed) || parsed < MIN_SNAPSHOT_SIZE_MIB || parsed > MAX_SNAPSHOT_SIZE_MIB) {
      setSnapshotSizeValue(String(snapshotSizeMib));
      return;
    }

    if (parsed !== snapshotSizeMib) {
      void onSettingChange(UserConfigField.JJ_SNAPSHOT_MAX_NEW_FILE_SIZE_MIB, parsed);
    }
  };

  const minimumVersion = jj?.versionRange?.minVersion ?? null;

  return (
    <SettingsSectionLayout description="Jujutsu (jj) is a version control system that works on top of git. Sculptor uses it only when the check below passes.">
      <Flex direction="column" gap="3" mb="4">
        {dependenciesStatus === null ? (
          <Flex align="center" gap="2" data-testid={ElementIds.JJ_AVAILABILITY}>
            <Spinner size="1" />
            <Text size="2">Checking jj…</Text>
          </Flex>
        ) : (
          <JjAvailabilityCallout
            readiness={dependenciesStatus.jjReadiness}
            jj={dependenciesStatus.jj}
            minimumVersion={minimumVersion ?? "—"}
          />
        )}
        <Flex>
          <Button
            variant="soft"
            onClick={() => void handleRecheck()}
            disabled={isRechecking}
            data-testid={ElementIds.JJ_RECHECK_BUTTON}
          >
            {isRechecking && <Spinner size="1" />}
            Re-check
          </Button>
        </Flex>
      </Flex>

      <SettingRow
        title="Binary Source"
        description="How Sculptor locates jj. Managed prefers Sculptor's downloaded, version-pinned copy, falling back to a jj on your PATH until one is installed."
      >
        <Flex align="center" gap="2">
          <Select.Root value={displayMode} onValueChange={handleModeChange}>
            <Select.Trigger variant="soft" data-testid={ElementIds.JJ_MODE_SELECTOR} />
            <Select.Content>
              <Select.Item value="MANAGED" data-testid={ElementIds.JJ_MODE_OPTION_MANAGED}>
                Managed
              </Select.Item>
              <Select.Item value="CUSTOM" data-testid={ElementIds.JJ_MODE_OPTION_CUSTOM}>
                Custom
              </Select.Item>
            </Select.Content>
          </Select.Root>
          {isModeSettling && <Spinner size="1" />}
        </Flex>
      </SettingRow>

      <SettingRow
        title="Status"
        description="Whether the configured jj is installed and at or above the minimum version."
      >
        <Flex align="center" gap="2" data-testid={ElementIds.JJ_STATUS}>
          {dependenciesStatus === null || isModeSettling ? (
            <Spinner size="1" />
          ) : jj?.isVersionInRange === true ? (
            <Flex align="center" gap="2">
              <CheckCircledIcon color="var(--green-9)" />
              <Text size="2" color="green" data-testid={ElementIds.JJ_UP_TO_DATE}>
                {jj.source === "EXTERNAL" ? `v${jj.version} — External binary` : `v${jj.version} — Managed`}
              </Text>
            </Flex>
          ) : jj?.isVersionInRange === false ? (
            <Flex align="center" gap="2">
              <ExclamationTriangleIcon color="var(--orange-9)" />
              <Text size="2" color="orange">
                v{jj.version} — Needs {minimumVersion} or a newer compatible version
              </Text>
            </Flex>
          ) : displayMode === "CUSTOM" && !jj?.path ? (
            <Text size="2" color="gray">
              No path configured
            </Text>
          ) : (
            <Flex align="center" gap="2">
              <CrossCircledIcon color="var(--red-9)" />
              <Text size="2" color="red">
                {jj?.path ? "Does not run" : "Not installed"}
              </Text>
            </Flex>
          )}
        </Flex>
      </SettingRow>

      {displayMode === "MANAGED" && (
        <SettingRow title="Managed Installation" description="Install or update the managed jj binary.">
          <Box>
            {isInstalling || installProgress ? (
              <Flex direction="column" gap="2" minWidth="200px" data-testid={ElementIds.JJ_INSTALL_PROGRESS}>
                <Flex align="center" gap="2">
                  <Spinner size="1" />
                  <Text size="2">Installing...</Text>
                </Flex>
                {progressPercent !== null && <Progress value={progressPercent} />}
              </Flex>
            ) : effectiveInstallError ? (
              <Flex direction="column" gap="2">
                <Text size="2" color="red">
                  {effectiveInstallError}
                </Text>
                <Button variant="soft" onClick={handleInstall} data-testid={ElementIds.JJ_INSTALL_BUTTON}>
                  Retry
                </Button>
              </Flex>
            ) : isManagedUpToDate ? (
              <Text size="2" color="green">
                Up to date
              </Text>
            ) : (
              <Button variant="soft" onClick={handleInstall} data-testid={ElementIds.JJ_INSTALL_BUTTON}>
                Install jj
              </Button>
            )}
          </Box>
        </SettingRow>
      )}

      <SettingRow
        title="Minimum version"
        description="Sculptor runs this jj release or any later 0.x one. The managed copy is this release."
      >
        <Text size="2" data-testid={ElementIds.JJ_MINIMUM_VERSION}>
          {minimumVersion ?? "—"}
        </Text>
      </SettingRow>

      <SettingRow title="Detected version" description="Version reported by `jj --version`.">
        <Text size="2" data-testid={ElementIds.JJ_VERSION}>
          {jj?.version ?? "Not installed"}
        </Text>
      </SettingRow>

      <SettingRow title="Active path" description="Resolved path to the jj binary in use.">
        <Text size="2" style={{ wordBreak: "break-all" }}>
          {jj?.path ?? "—"}
        </Text>
      </SettingRow>

      {displayMode === "CUSTOM" && (
        <SettingRow title="Binary path" description="Absolute path or command name (e.g. /opt/homebrew/bin/jj or jj).">
          <Flex gap="2" align="center">
            <TextField.Root
              placeholder="/opt/homebrew/bin/jj or jj"
              value={customPathInput}
              onChange={(e) => setCustomPathInput(e.target.value)}
              data-testid={ElementIds.JJ_BINARY_PATH_INPUT}
              style={{ minWidth: "300px" }}
            />
            <Button variant="soft" onClick={handleApplyCustomPath} data-testid={ElementIds.JJ_BINARY_PATH_APPLY}>
              Apply
            </Button>
          </Flex>
        </SettingRow>
      )}

      {dependenciesStatus !== null && (
        <JjIdentityRow readiness={dependenciesStatus.jjReadiness} onSave={saveIdentity} />
      )}

      <SettingRow
        title="Maximum new file size"
        description="Largest new file jj snapshots in a jj workspace. jj leaves bigger new files untracked; its own 1 MiB default leaves updated lockfiles out."
      >
        <TextField.Root
          type="number"
          min={MIN_SNAPSHOT_SIZE_MIB}
          max={MAX_SNAPSHOT_SIZE_MIB}
          value={snapshotSizeValue}
          onChange={(e) => setSnapshotSizeValue(e.target.value)}
          onBlur={handleSnapshotSizeBlur}
          data-testid={ElementIds.JJ_SNAPSHOT_SIZE_INPUT}
          style={{ width: 140 }}
        >
          <TextField.Slot side="right">
            <Text size="1" color="gray">
              MiB
            </Text>
          </TextField.Slot>
        </TextField.Root>
      </SettingRow>

      <SettingRow title="Documentation" description="How jj works, and how it differs from git.">
        <Link href={JJ_DOCS_URL} target="_blank" rel="noreferrer" size="2">
          jj documentation
        </Link>
      </SettingRow>
    </SettingsSectionLayout>
  );
};
