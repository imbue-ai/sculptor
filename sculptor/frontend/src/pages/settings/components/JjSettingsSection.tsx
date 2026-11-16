import { CheckCircledIcon, CrossCircledIcon, ExclamationTriangleIcon } from "@radix-ui/react-icons";
import { Box, Button, Flex, Link, Progress, Select, Spinner, Text, TextField } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { type ReactElement, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";

import type { CiBabysitterConfig, DependencyInfo, JjIdentity, Project } from "../../../api";
import { ElementIds, setJjIdentity, UserConfigField } from "../../../api";
import { dependenciesStatusAtom, refreshDependenciesStatus } from "../../../common/state/atoms/dependenciesStatus";
import { projectsArrayAtom } from "../../../common/state/atoms/projects.ts";
import {
  ciBabysitterConfigAtom,
  ciBabysitterJjMergeConflictPromptAtom,
  ciBabysitterJjPipelineFailedPromptAtom,
  ciBabysitterMergeConflictPromptAtom,
  ciBabysitterPipelineFailedPromptAtom,
  commitPromptAtom,
  jjCommitPromptAtom,
  jjPrCreationPromptAtom,
  jjSnapshotMaxNewFileSizeMibAtom,
  prCreationPromptAtom,
} from "../../../common/state/atoms/userConfig";
import { useOpenSettings } from "../../../common/state/hooks/useOpenSettings.ts";
import { useManagedDependency } from "../hooks/useManagedDependency";
import { JjAvailabilityCallout } from "./JjAvailabilityCallout.tsx";
import { JjIdentityRow } from "./JjIdentityRow.tsx";
import { JjPromptSettingRow } from "./JjPromptSettingRow.tsx";
import { SettingRow } from "./SettingRow.tsx";
import { SettingsSectionLayout } from "./SettingsSection.tsx";

const JJ_DOCS_URL = "https://jj-vcs.github.io/jj/latest/";
const MIN_SNAPSHOT_SIZE_MIB = 1;
const MAX_SNAPSHOT_SIZE_MIB = 1024;

// Suggested jj wordings. Sculptor appends its own jj instructions (the bookmark
// and the pull request's base) to whichever prompt is sent.
const SUGGESTED_JJ_COMMIT_PROMPT =
  "Describe the working-copy change with a comprehensive message and start a new change on top of it with `jj commit -m`. Leave no work outside the described change.";
const SUGGESTED_JJ_PR_CREATION_PROMPT =
  "Push my work to origin with jj and create a pull request using the GitHub CLI (gh). Write a clear description summarizing the changes.";
const SUGGESTED_JJ_CI_PIPELINE_FAILED_PROMPT =
  "Investigate the failing pipeline for this PR, identify the root cause and fix the code. Describe the change, move the PR's bookmark onto it, and push it with `jj git push`.";
const SUGGESTED_JJ_CI_MERGE_CONFLICT_PROMPT =
  "This PR has a merge conflict with its base branch. Fetch with `jj git fetch`, rebase this workspace's revisions onto the target bookmark with `jj rebase`, resolve the conflicts, and push the PR's bookmark with `jj git push`.";

const JjRepositoriesRow = ({
  projects,
  onConfigure,
}: {
  projects: ReadonlyArray<Project>;
  onConfigure: (projectId: string) => void;
}): ReactElement => (
  <SettingRow
    title="Repositories using jj"
    description="Repositories whose new workspaces are jj workspaces. Turn jj on or off in a repository's settings."
    data-testid={ElementIds.JJ_REPOSITORIES}
  >
    {projects.length === 0 ? (
      <Text size="2" color="gray">
        No repository uses jj for new workspaces yet.
      </Text>
    ) : (
      <Flex direction="column" gap="2" align="end">
        {projects.map((project) => (
          <Flex key={project.objectId} align="center" gap="3">
            <Text size="2">{project.name}</Text>
            <Link
              href="#"
              size="2"
              onClick={(e) => {
                e.preventDefault();
                onConfigure(project.objectId);
              }}
            >
              Configure
            </Link>
          </Flex>
        ))}
      </Flex>
    )}
  </SettingRow>
);

/** Where the status row says an in-range jj comes from. */
const describeJjSource = (jj: DependencyInfo): string => {
  if (jj.source === "MANAGED") {
    return "Managed";
  }
  // Managed mode runs a jj on PATH while no managed copy is installed.
  return jj.mode === "MANAGED" ? "On your PATH, until the managed copy is installed" : "External binary";
};

type JjSettingsSectionProps = {
  onSettingChange: (field: UserConfigField, value: unknown) => Promise<void>;
};

export const JjSettingsSection = ({ onSettingChange }: JjSettingsSectionProps): ReactElement => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const snapshotSizeMib = useAtomValue(jjSnapshotMaxNewFileSizeMibAtom);
  const commitPrompt = useAtomValue(commitPromptAtom);
  const jjCommitPrompt = useAtomValue(jjCommitPromptAtom);
  const prCreationPrompt = useAtomValue(prCreationPromptAtom);
  const jjPrCreationPrompt = useAtomValue(jjPrCreationPromptAtom);
  const ciBabysitterConfig = useAtomValue(ciBabysitterConfigAtom);
  const pipelineFailedPrompt = useAtomValue(ciBabysitterPipelineFailedPromptAtom);
  const jjPipelineFailedPrompt = useAtomValue(ciBabysitterJjPipelineFailedPromptAtom);
  const mergeConflictPrompt = useAtomValue(ciBabysitterMergeConflictPromptAtom);
  const jjMergeConflictPrompt = useAtomValue(ciBabysitterJjMergeConflictPromptAtom);
  const projects = useAtomValue(projectsArrayAtom);
  const openSettings = useOpenSettings();
  // Set when an Edit prompt menu opened the page for one of its prompts.
  const [searchParams] = useSearchParams();
  const focusPrompt = searchParams.get("focusPrompt");

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

  // Identity and PATH changes made outside Sculptor send no event, so check again
  // whenever the page opens. The re-checked status arrives on the stream.
  useEffect(() => {
    void refreshDependenciesStatus();
  }, []);

  const handleRecheck = async (): Promise<void> => {
    setIsRechecking(true);
    await refreshDependenciesStatus();
    setIsRechecking(false);
  };

  // The backend publishes the status with the new identity on the stream.
  // skipWsAck: the endpoint opens no data-model transaction, so no stream
  // acknowledgement ever follows.
  const saveIdentity = useCallback(async (identity: JjIdentity): Promise<void> => {
    await setJjIdentity({ body: identity, meta: { skipWsAck: true } });
  }, []);

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

  // The babysitter's settings are one nested object; the whole object is sent
  // so the optimistic copy keeps its other fields.
  const saveCiBabysitterPrompt = (
    overrides: Pick<CiBabysitterConfig, "jjPipelineFailedPrompt"> | Pick<CiBabysitterConfig, "jjMergeConflictPrompt">,
  ): void => {
    void onSettingChange(UserConfigField.CI_BABYSITTER, { ...ciBabysitterConfig, ...overrides });
  };

  const jjProjects = projects.filter((project) => project.useJjForNewWorkspaces);
  const minimumVersion = jj?.versionRange?.minVersion ?? null;
  const loginShellJj = dependenciesStatus?.loginShellJj ?? null;

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
                v{jj.version} — {describeJjSource(jj)}
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

      {loginShellJj && (
        <SettingRow
          title="jj in your terminal"
          description="Your shell profile puts another jj first on PATH, so workspace terminals run it, while agents run the jj above."
        >
          <Text size="2" style={{ wordBreak: "break-all" }}>
            {loginShellJj.version === null
              ? `${loginShellJj.path} (no recognizable version)`
              : `${loginShellJj.path} (jj ${loginShellJj.version})`}
          </Text>
        </SettingRow>
      )}

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

      <JjPromptSettingRow
        title="jj commit prompt"
        description="Sent instead of the commit prompt when you click Commit in a jj workspace. Sculptor adds what to do with the workspace's bookmark."
        value={jjCommitPrompt}
        gitPrompt={commitPrompt}
        suggestedPrompt={SUGGESTED_JJ_COMMIT_PROMPT}
        onSave={(value) => void onSettingChange(UserConfigField.JJ_COMMIT_PROMPT, value)}
        shouldFocusOnMount={focusPrompt === "commit"}
        data-testid={ElementIds.JJ_COMMIT_PROMPT_SETTING}
      />

      <JjPromptSettingRow
        title="jj PR creation prompt"
        description="Sent instead of the PR creation prompt when you click Create PR in a jj workspace. Sculptor adds the bookmark to push and the branch to open the pull request into."
        value={jjPrCreationPrompt}
        gitPrompt={prCreationPrompt}
        suggestedPrompt={SUGGESTED_JJ_PR_CREATION_PROMPT}
        onSave={(value) => void onSettingChange(UserConfigField.JJ_PR_CREATION_PROMPT, value)}
        shouldFocusOnMount={focusPrompt === "pr-creation"}
        data-testid={ElementIds.JJ_PR_CREATION_PROMPT_SETTING}
      />

      <JjPromptSettingRow
        title="jj CI Babysitter pipeline prompt"
        description="Sent instead of the CI Babysitter's pipeline-failed prompt when the pull request comes from a jj workspace."
        value={jjPipelineFailedPrompt}
        gitPrompt={pipelineFailedPrompt}
        suggestedPrompt={SUGGESTED_JJ_CI_PIPELINE_FAILED_PROMPT}
        onSave={(value) => saveCiBabysitterPrompt({ jjPipelineFailedPrompt: value })}
        data-testid={ElementIds.JJ_CI_PIPELINE_FAILED_PROMPT_SETTING}
      />

      <JjPromptSettingRow
        title="jj CI Babysitter merge conflict prompt"
        description="Sent instead of the CI Babysitter's merge-conflict prompt when the pull request comes from a jj workspace."
        value={jjMergeConflictPrompt}
        gitPrompt={mergeConflictPrompt}
        suggestedPrompt={SUGGESTED_JJ_CI_MERGE_CONFLICT_PROMPT}
        onSave={(value) => saveCiBabysitterPrompt({ jjMergeConflictPrompt: value })}
        data-testid={ElementIds.JJ_CI_MERGE_CONFLICT_PROMPT_SETTING}
      />

      <JjRepositoriesRow projects={jjProjects} onConfigure={(projectId) => openSettings("REPOSITORIES", projectId)} />

      <SettingRow title="Documentation" description="How jj works, and how it differs from git.">
        <Link href={JJ_DOCS_URL} target="_blank" rel="noreferrer" size="2">
          jj documentation
        </Link>
      </SettingRow>
    </SettingsSectionLayout>
  );
};
