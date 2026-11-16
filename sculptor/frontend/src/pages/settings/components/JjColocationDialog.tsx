import { CrossCircledIcon, ExclamationTriangleIcon, InfoCircledIcon } from "@radix-ui/react-icons";
import { Button, Callout, Code, Dialog, Flex, Spinner, Text } from "@radix-ui/themes";
import { useQuery } from "@tanstack/react-query";
import type { ReactElement, ReactNode } from "react";

import type { JjColocationBlocker, JjColocationPreflight, JjColocationWarning } from "~/api";
import { ElementIds, getProjectJjPreflight } from "~/api";
import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";
import { getErrorMessage } from "~/common/utils/errors.ts";

import styles from "./JjColocationDialog.module.scss";
import { OpenJjSettingsLink } from "./OpenJjSettingsLink.tsx";

// The repository's own blockers. JJ_UNAVAILABLE is worded by the backend,
// which sends its reason with the pre-flight.
type RepositoryBlocker = Exclude<JjColocationBlocker, "JJ_UNAVAILABLE">;

const BLOCKER_COPY = {
  JJ_REPOSITORY_NOT_COLOCATED:
    "This repository has a .jj directory that is not colocated with its .git. Sculptor never deletes a .jj directory: remove it yourself, then try again.",
  SUBMODULES: "This repository uses git submodules, which jj workspaces cannot hold.",
  LFS: "This repository uses Git LFS, which jj workspaces cannot hold.",
  GIT_OPERATION_IN_PROGRESS:
    "git has stopped in a merge, rebase, cherry-pick or revert. Finish or abort it, then try again.",
} as const satisfies Record<RepositoryBlocker, string>;

const isRepositoryBlocker = (blocker: JjColocationBlocker): blocker is RepositoryBlocker =>
  blocker !== "JJ_UNAVAILABLE";

const WARNING_COPY = {
  HOOKS: "This repository has git hooks. Hooks do not run in jj workspaces.",
  SPARSE_CHECKOUT: "This repository uses a sparse checkout, which works differently in jj workspaces.",
} as const satisfies Record<JjColocationWarning, string>;

const UNCOMMITTED_CHANGES_COPY = "Your uncommitted changes become jj's working-copy commit.";

type JjColocationDialogProps = {
  projectId: string;
  projectPath: string;
  isOpen: boolean;
  onClose: () => void;
  onConfirm: () => void;
};

/** Confirms colocating a repository with jj, after showing what its pre-flight found. */
export const JjColocationDialog = ({
  projectId,
  projectPath,
  isOpen,
  onClose,
  onConfirm,
}: JjColocationDialogProps): ReactElement => {
  return (
    <Dialog.Root open={isOpen} onOpenChange={onClose}>
      <Dialog.Content className={styles.dialogContent} data-testid={ElementIds.JJ_COLOCATION_DIALOG}>
        <Dialog.Title>Initialize jujutsu colocation</Dialog.Title>
        {/* Content mounts only while open, so every opening reads a fresh pre-flight. */}
        <JjColocationDialogBody projectId={projectId} projectPath={projectPath} onConfirm={onConfirm} />
      </Dialog.Content>
    </Dialog.Root>
  );
};

type PreflightResult =
  { status: "loading" } | { status: "error"; message: string } | { status: "loaded"; preflight: JjColocationPreflight };

const usePreflight = (projectId: string): PreflightResult => {
  const query = useQuery({
    queryKey: [SCULPTOR_QUERY_KEY_PREFIX, "projectJjPreflight", projectId] as const,
    queryFn: async (): Promise<JjColocationPreflight> => {
      const { data } = await getProjectJjPreflight({ path: { project_id: projectId } });
      return data;
    },
    // A pre-flight describes the repository right now. Each mount fetches it,
    // and a cached one is never shown while that fetch is in flight.
    gcTime: 0,
    staleTime: 0,
    retry: false,
  });
  if (query.isFetching || query.isPending) {
    return { status: "loading" };
  }

  if (query.isError) {
    return { status: "error", message: getErrorMessage(query.error, "Cannot read the repository") };
  }
  return { status: "loaded", preflight: query.data };
};

const JjColocationDialogBody = ({
  projectId,
  projectPath,
  onConfirm,
}: {
  projectId: string;
  projectPath: string;
  onConfirm: () => void;
}): ReactElement => {
  const preflight = usePreflight(projectId);
  const canConfirm = preflight.status === "loaded" && preflight.preflight.blockers.length === 0;

  return (
    <Flex direction="column" gap="3">
      <Text size="2">
        Sculptor will run <Code>jj git init --colocate</Code> in <Code>{projectPath}</Code>. When it finishes, new
        workspaces in this repository are jj workspaces.
      </Text>
      <Text size="2">
        Git keeps working in this repository: your files, your branch and HEAD stay as they are. Afterwards git shows
        untracked files as added, because jj records them.
      </Text>
      <JjColocationPreflightFindings preflight={preflight} />
      <Flex gap="3" justify="end" className={styles.actions}>
        <Dialog.Close>
          <Button variant="soft" color="gray">
            Cancel
          </Button>
        </Dialog.Close>
        <Button
          variant="solid"
          onClick={onConfirm}
          disabled={!canConfirm}
          data-testid={ElementIds.JJ_COLOCATION_DIALOG_CONFIRM}
        >
          Initialize
        </Button>
      </Flex>
    </Flex>
  );
};

const JjColocationPreflightFindings = ({ preflight }: { preflight: PreflightResult }): ReactElement => {
  if (preflight.status === "loading") {
    return (
      <Flex align="center" gap="2">
        <Spinner size="1" />
        <Text size="2" color="gray">
          Checking the repository…
        </Text>
      </Flex>
    );
  }

  if (preflight.status === "error") {
    return (
      <PreflightCallout color="red" icon={<CrossCircledIcon />}>
        {preflight.message}
      </PreflightCallout>
    );
  }
  const { blockers, warnings, hasUncommittedChanges, jjUnavailableReason } = preflight.preflight;
  return (
    <>
      {jjUnavailableReason !== null && (
        <PreflightCallout color="red" icon={<CrossCircledIcon />}>
          {jjUnavailableReason}. <OpenJjSettingsLink />
        </PreflightCallout>
      )}
      {blockers.filter(isRepositoryBlocker).map((blocker) => (
        <PreflightCallout key={blocker} color="red" icon={<CrossCircledIcon />}>
          {BLOCKER_COPY[blocker]}
        </PreflightCallout>
      ))}
      {warnings.map((warning) => (
        <PreflightCallout key={warning} color="amber" icon={<ExclamationTriangleIcon />}>
          {WARNING_COPY[warning]}
        </PreflightCallout>
      ))}
      {hasUncommittedChanges && (
        <PreflightCallout color="gray" icon={<InfoCircledIcon />}>
          {UNCOMMITTED_CHANGES_COPY}
        </PreflightCallout>
      )}
    </>
  );
};

const PreflightCallout = ({
  color,
  icon,
  children,
}: {
  color: "red" | "amber" | "gray";
  icon: ReactElement;
  children: ReactNode;
}): ReactElement => (
  <Callout.Root color={color} size="1">
    <Callout.Icon>{icon}</Callout.Icon>
    <Callout.Text>{children}</Callout.Text>
  </Callout.Root>
);
