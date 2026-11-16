import { Box, Button, Flex, Link, Spinner, Switch, Text, Tooltip } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { GitForkIcon } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useEffect, useState } from "react";

import type { ProjectJjState } from "~/api";
import { ElementIds } from "~/api";
import { isJjAvailableAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { projectJjStateAtomFamily } from "~/common/state/atoms/projectJjState.ts";
import { type ToastContent, ToastType } from "~/common/state/atoms/toasts.ts";
import { useOpenSettings } from "~/common/state/hooks/useOpenSettings.ts";
import { useColocateProjectMutation, useUseJjForNewWorkspacesMutation } from "~/common/state/mutations/projectJj.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";
import { SettingsSection } from "~/pages/settings/sections.ts";

import { JjColocationDialog } from "./JjColocationDialog.tsx";
import styles from "./RepoJjControls.module.scss";
import {
  type ColocationSwitchState,
  getColocationSwitchState,
  getUseJjSwitchState,
  type UseJjSwitchState,
} from "./repoJjControlState.ts";

const JJ_UNAVAILABLE_TOOLTIP = "Ensure that jujutsu VCS is available in the settings panel to use these features";
const COLOCATION_LOCKED_TOOLTIP =
  "Sculptor will not destroy your jj colocation. Use the command line to complete this if you are sure.";
const NOT_COLOCATED_TOOLTIP = "Initialize the jujutsu colocation first";
const INITIALIZING_TEXT = "Initializing jujutsu colocation";

// How long a colocation request the server accepted waits for the stream to
// report it before the switch falls back to whatever the stream says.
const COLOCATION_SETTLE_TIMEOUT_MS = 10_000;

type RepoJjControlsProps = {
  projectId: string;
  projectPath: string;
  // The project row's stored flag, as the stream delivered it.
  useJjForNewWorkspaces: boolean;
  setToast: (toast: ToastContent | null) => void;
};

/** A repository's two jj switches: colocate it with jj, and use jj for its new workspaces. */
export const RepoJjControls = ({
  projectId,
  projectPath,
  useJjForNewWorkspaces,
  setToast,
}: RepoJjControlsProps): ReactElement => {
  const isJjAvailable = useAtomValue(isJjAvailableAtom);
  const jjState = useAtomValue(projectJjStateAtomFamily(projectId));
  const [isDialogOpen, setIsDialogOpen] = useState<boolean>(false);
  const openSettings = useOpenSettings();
  const { isColocationRequested, requestColocation } = useColocationRequest({ projectId, jjState, setToast });
  const {
    mutate: saveUseJj,
    isPending: isUseJjPending,
    variables: useJjVariables,
  } = useUseJjForNewWorkspacesMutation({
    onError: (error): void => {
      setToast({ type: ToastType.ERROR, title: getErrorMessage(error, "Failed to save the jj setting") });
    },
  });

  const colocationState = getColocationSwitchState({ isJjAvailable, jjState, isColocationRequested });
  const useJjState = getUseJjSwitchState({
    isJjAvailable,
    colocation: jjState?.colocation,
    storedValue: useJjForNewWorkspaces,
    requestedValue: isUseJjPending ? useJjVariables?.useJjForNewWorkspaces : undefined,
  });

  const handleColocationConfirm = (): void => {
    setIsDialogOpen(false);
    requestColocation();
  };

  const handleUseJjCheckedChange = (isChecked: boolean): void => {
    saveUseJj({ projectId, useJjForNewWorkspaces: isChecked });
  };

  return (
    <Box className={styles.jjControls}>
      <Text as="div" className={styles.sectionLabel}>
        <GitForkIcon size={14} />
        Jujutsu
      </Text>
      <Flex direction="column" gap="2">
        <Flex align="center" gap="2" wrap="wrap">
          <SwitchTooltip content={colocationTooltip(colocationState)}>
            <Switch
              size="1"
              checked={colocationState.kind === "ON_LOCKED"}
              disabled={!isColocationSwitchEnabled(colocationState)}
              onCheckedChange={() => setIsDialogOpen(true)}
              aria-label="Is this repository a colocated jj repository?"
              data-testid={ElementIds.REPO_JJ_COLOCATION_SWITCH}
            />
          </SwitchTooltip>
          <Text size="2">Is this repository a colocated jj repository?</Text>
          {colocationState.kind === "INITIALIZING" && (
            <Flex align="center" gap="1">
              <Spinner size="1" />
              <Text size="1" color="gray">
                {INITIALIZING_TEXT}
              </Text>
            </Flex>
          )}
        </Flex>
        {colocationState.kind === "FAILED" && (
          <Flex align="center" gap="2" className={styles.indented}>
            <Text size="1" color="red" className={styles.error} data-testid={ElementIds.JJ_COLOCATION_ERROR}>
              {colocationState.error}
            </Text>
            <Button size="1" variant="soft" onClick={requestColocation}>
              Retry
            </Button>
          </Flex>
        )}
        <Flex align="center" gap="2">
          <SwitchTooltip content={useJjTooltip(useJjState)}>
            <Switch
              size="1"
              checked={useJjState.isChecked}
              disabled={useJjState.kind !== "ENABLED" || isUseJjPending}
              onCheckedChange={handleUseJjCheckedChange}
              aria-label="Use jj for new workspaces created in this repository"
              data-testid={ElementIds.REPO_JJ_USE_FOR_NEW_WORKSPACES_SWITCH}
            />
          </SwitchTooltip>
          <Text size="2">Use jj for new workspaces created in this repository</Text>
        </Flex>
        <Text size="1" className={`${styles.hint} ${styles.indented}`}>
          New workspaces in this repository are jj workspaces, with no git inside. Existing workspaces keep their kind.
        </Text>
        {colocationState.kind === "UNAVAILABLE" && (
          <Link
            href="#"
            size="1"
            onClick={(e) => {
              e.preventDefault();
              openSettings(SettingsSection.JJ);
            }}
          >
            Open Jujutsu settings
          </Link>
        )}
      </Flex>
      <JjColocationDialog
        projectId={projectId}
        projectPath={projectPath}
        isOpen={isDialogOpen}
        onClose={() => setIsDialogOpen(false)}
        onConfirm={handleColocationConfirm}
      />
    </Box>
  );
};

/**
 * A colocation request, held from the click until the stream answers it. The
 * stream publishes a repository's jj state only when it changes, so any state
 * newer than the one the request was made against is the server's answer. A
 * request the server refused is reported in a toast and leaves the switch to
 * the stream at once.
 */
const useColocationRequest = ({
  projectId,
  jjState,
  setToast,
}: {
  projectId: string;
  jjState: ProjectJjState | null;
  setToast: (toast: ToastContent | null) => void;
}): { isColocationRequested: boolean; requestColocation: () => void } => {
  const { mutate, reset, isPending, isSuccess } = useColocateProjectMutation({
    onError: (error): void => {
      setToast({ type: ToastType.ERROR, title: getErrorMessage(error, "Failed to initialize the jujutsu colocation") });
    },
  });
  const [jjStateAtRequest, setJjStateAtRequest] = useState<ProjectJjState | null>(null);
  const hasStreamAnswered = jjState !== jjStateAtRequest;

  useEffect((): (() => void) | undefined => {
    if (!isSuccess) {
      return undefined;
    }

    if (hasStreamAnswered) {
      reset();
      return undefined;
    }
    const timeout = window.setTimeout(reset, COLOCATION_SETTLE_TIMEOUT_MS);
    return (): void => window.clearTimeout(timeout);
  }, [isSuccess, hasStreamAnswered, reset]);

  const requestColocation = (): void => {
    setJjStateAtRequest(jjState);
    mutate({ projectId });
  };

  return { isColocationRequested: (isPending || isSuccess) && !hasStreamAnswered, requestColocation };
};

const isColocationSwitchEnabled = (state: ColocationSwitchState): boolean =>
  state.kind === "OFF" || state.kind === "FAILED";

const colocationTooltip = (state: ColocationSwitchState): string | undefined => {
  switch (state.kind) {
    case "UNAVAILABLE":
      return JJ_UNAVAILABLE_TOOLTIP;
    case "ON_LOCKED":
      return COLOCATION_LOCKED_TOOLTIP;
    case "INITIALIZING":
    case "FAILED":
    case "OFF":
      return undefined;
  }
};

const useJjTooltip = (state: UseJjSwitchState): string | undefined => {
  switch (state.kind) {
    case "UNAVAILABLE":
      return JJ_UNAVAILABLE_TOOLTIP;
    case "NOT_COLOCATED":
      return NOT_COLOCATED_TOOLTIP;
    case "ENABLED":
      return undefined;
  }
};

/** A disabled switch gets no pointer events, so its tooltip hangs off a wrapper. */
const SwitchTooltip = ({ content, children }: { content: string | undefined; children: ReactNode }): ReactElement => (
  <Tooltip content={content} hidden={content === undefined}>
    <span className={styles.switchWrapper}>{children}</span>
  </Tooltip>
);
