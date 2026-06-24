import { Button, Flex, Spinner, Switch, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ElementIds, getActiveProjects, getMostRecentlyUsedProject, WorkspaceInitializationStrategy } from "~/api";
import { isDismissibleOverlayOpen } from "~/common/overlayUtils.ts";
import { lastUsedAgentTypeAtom, type StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { projectsArrayAtom, updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import { defaultModelAtom, isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useCreateWorkspace } from "~/common/state/hooks/useCreateWorkspace.ts";
import { useRepoInfo } from "~/common/state/hooks/useRepoInfo.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import { BranchSelector } from "~/components/BranchSelector.tsx";
import { KeyboardHint } from "~/components/KeyboardHint.tsx";
import { AgentTypeSelect } from "~/components/newWorkspace/AgentTypeSelect.tsx";
import { BranchNameField } from "~/components/newWorkspace/BranchNameField.tsx";
import { ModeSelect } from "~/components/newWorkspace/ModeSelect.tsx";
import {
  keepNewWorkspaceModalOpenAtom,
  lastWorkspaceCreationSettingsAtom,
} from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { RepoSelector } from "~/components/RepoSelector.tsx";
import { Toast, type ToastContent, ToastType } from "~/components/Toast.tsx";
import { getMetaKey, isModifierPressed } from "~/electron/utils.ts";
import { useBranchNamePreview } from "~/pages/add-workspace/hooks/useBranchNamePreview.ts";

import styles from "./NewWorkspaceForm.module.scss";

const PROMPT_MAX_TEXTAREA_HEIGHT_PX = 240;

type NewWorkspaceFormProps = {
  /** Repo to pre-select (from a repo group's "+"); overrides the MRU seed. */
  presetProjectId?: string;
  /**
   * Text to seed the prompt textarea with on mount. Used by the empty
   * first-run page to default the very first prompt to `/sculptor:help`
   * (FIRST-04). A mount-time snapshot the user can freely edit.
   */
  initialPrompt?: string;
  /** Called after a successful create when "keep open" is off. */
  onCreated: () => void;
};

/**
 * The WSC-05 new-workspace form: a borderless title input, an auto-growing
 * prompt textarea, a breadcrumb row of context pills (repo / agent type / mode /
 * branch), and a footer (keep-open switch + Cmd+Enter hint + Create). Field
 * values are LOCAL component state (the modal is ephemeral), seeded from
 * `lastWorkspaceCreationSettingsAtom` and the preset repo. Reuses this branch's
 * RepoSelector / BranchSelector / BranchNameField and the factored create hook.
 */
export const NewWorkspaceForm = ({
  presetProjectId,
  initialPrompt,
  onCreated,
}: NewWorkspaceFormProps): ReactElement => {
  // State and hooks — atoms
  const projects = useAtomValue(projectsArrayAtom);
  const updateProjects = useSetAtom(updateProjectsAtom);
  const lastSettings = useAtomValue(lastWorkspaceCreationSettingsAtom);
  const lastUsedAgentType = useAtomValue(lastUsedAgentTypeAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const defaultModel = useAtomValue(defaultModelAtom);
  const [isKeepOpen, setIsKeepOpen] = useAtom(keepNewWorkspaceModalOpenAtom);

  // State and hooks — seed the local form state once, from the preset repo (if
  // any) then the MRU settings. Reading the seed lazily keeps it a mount-time
  // snapshot the user can freely change without it being clobbered by later
  // atom updates.
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(
    () => presetProjectId ?? lastSettings?.projectId ?? null,
  );
  const [workspaceName, setWorkspaceName] = useState<string>("");
  const [prompt, setPrompt] = useState<string>(() => initialPrompt ?? "");
  const [mode, setMode] = useState<WorkspaceInitializationStrategy>(
    () => lastSettings?.initStrategy ?? WorkspaceInitializationStrategy.WORKTREE,
  );
  const [agentTypeValue, setAgentTypeValue] = useState<StoredAgentType>(() => {
    const seed = lastSettings?.agentType ?? lastUsedAgentType;
    // A stored "pi" is unusable when pi-agent is off — fall back to Claude.
    return seed === "pi" && !isPiAgentEnabled ? "claude" : seed;
  });
  const [userSelectedBranch, setUserSelectedBranch] = useState<string | undefined>(() => lastSettings?.sourceBranch);
  // `null` means "use the auto-filled preview"; any string means the user has
  // taken over. Both the value and the manual flag collapse into one piece of
  // state so they can never disagree.
  const [branchNameOverride, setBranchNameOverride] = useState<string | null>(null);
  const [shuffleNonce, setShuffleNonce] = useState<number>(0);
  const [isLoadingProjects, setIsLoadingProjects] = useState<boolean>(true);
  const [toast, setToast] = useState<ToastContent | null>(null);

  // State and hooks — external
  const { registrations } = useTerminalAgentRegistrations();
  const { repoInfo, fetchRepoInfo, fetchCurrentBranch } = useRepoInfo(selectedProjectId ?? "");
  const { isCreating, createWorkspace } = useCreateWorkspace();
  const nameInputRef = useRef<HTMLInputElement>(null);
  const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const isBranchNameManuallyEdited = branchNameOverride !== null;
  const {
    preview: branchNamePreview,
    displayedValue: effectiveBranchName,
    isLoading: isBranchNamePreviewLoading,
    collision: branchNameCollision,
  } = useBranchNamePreview({
    projectId: selectedProjectId,
    workspaceName,
    mode,
    override: branchNameOverride,
    shuffleNonce,
  });

  const sourceBranch = useMemo(() => userSelectedBranch ?? repoInfo?.currentBranch, [userSelectedBranch, repoInfo]);

  // Effects — load projects on mount. Fall back to the MRU project, then the
  // first project, only when there is no valid seeded selection.
  useEffect(() => {
    let isCancelled = false;
    const loadProjects = async (): Promise<void> => {
      try {
        const [projectsResponse, mruResponse] = await Promise.all([
          getActiveProjects({ meta: { skipWsAck: true } }),
          getMostRecentlyUsedProject({ meta: { skipWsAck: true } }),
        ]);
        if (isCancelled) return;

        const activeProjects = projectsResponse.data ?? [];
        updateProjects(activeProjects);

        setSelectedProjectId((current) => {
          if (current !== null && activeProjects.some((p) => p.objectId === current)) {
            return current;
          }
          const mruProjectId = mruResponse.data;
          if (mruProjectId && activeProjects.some((p) => p.objectId === mruProjectId)) {
            return mruProjectId;
          }
          return activeProjects.length > 0 ? activeProjects[0].objectId : null;
        });
      } catch (error) {
        console.error("Failed to load projects:", error);
        if (!isCancelled) {
          setToast({ title: "Failed to load repositories", type: ToastType.ERROR });
        }
      } finally {
        if (!isCancelled) {
          setIsLoadingProjects(false);
        }
      }
    };
    void loadProjects();
    return (): void => {
      isCancelled = true;
    };
  }, [updateProjects]);

  // Effects — refresh branch info when the selected project changes.
  useEffect(() => {
    if (!selectedProjectId) return;
    fetchCurrentBranch();
    fetchRepoInfo();
  }, [selectedProjectId, fetchCurrentBranch, fetchRepoInfo]);

  // Effects — auto-grow the prompt textarea up to a cap (no `field-sizing`
  // hack: measure scrollHeight and apply it, clamped, on every change).
  useEffect(() => {
    const textarea = promptTextareaRef.current;
    if (!textarea) return;
    textarea.style.height = "auto";
    textarea.style.height = `${Math.min(textarea.scrollHeight, PROMPT_MAX_TEXTAREA_HEIGHT_PX)}px`;
  }, [prompt]);

  // Functions and callbacks
  const handleProjectChange = useCallback((nextProjectId: string): void => {
    setSelectedProjectId(nextProjectId);
    // Switching repos invalidates branch choices made against the old repo.
    setBranchNameOverride(null);
    setUserSelectedBranch(undefined);
  }, []);

  const handleModeChange = useCallback((nextMode: WorkspaceInitializationStrategy): void => {
    setMode(nextMode);
    setBranchNameOverride(null);
  }, []);

  const handleShuffle = useCallback((): void => {
    // Return to auto-fill mode and force a fresh preview fetch (re-rolls the
    // random slug when the title is blank).
    setBranchNameOverride(null);
    setShuffleNonce((prev) => prev + 1);
  }, []);

  const isSubmitDisabled =
    selectedProjectId === null ||
    isCreating ||
    (mode === WorkspaceInitializationStrategy.WORKTREE &&
      (effectiveBranchName.trim() === "" || isBranchNamePreviewLoading)) ||
    (repoInfo !== null && repoInfo.recentBranches?.length === 0);

  const handleSubmit = useCallback(async (): Promise<void> => {
    if (isSubmitDisabled || selectedProjectId === null) return;

    const trimmedBranch = effectiveBranchName.trim();
    if (mode === WorkspaceInitializationStrategy.WORKTREE && !trimmedBranch) {
      setToast({ title: "Branch name is required for worktree workspaces", type: ToastType.ERROR });
      return;
    }

    const result = await createWorkspace({
      projectId: selectedProjectId,
      workspaceName,
      prompt,
      mode,
      sourceBranch,
      branchName: effectiveBranchName,
      agentTypeValue,
      registrations,
      defaultModel,
    });

    if (!result.ok) {
      if (result.error.kind === "branch-collision") {
        setToast({ title: `Branch '${result.error.branchName}' already exists`, type: ToastType.ERROR });
      } else {
        setToast({
          title: "",
          description: (
            <div>
              <b>Failed to create workspace</b>
              <br />
              <pre>{String(result.error.cause)}</pre>
            </div>
          ),
          type: ToastType.ERROR,
        });
      }
      return;
    }

    if (isKeepOpen) {
      // Decision B8: keep the dialog open for rapid multi-create — reset the
      // per-workspace fields but retain the repo + agent type (+ mode/source).
      setWorkspaceName("");
      setPrompt("");
      setBranchNameOverride(null);
      setShuffleNonce((prev) => prev + 1);
      nameInputRef.current?.focus();
    } else {
      onCreated();
    }
  }, [
    isSubmitDisabled,
    selectedProjectId,
    effectiveBranchName,
    mode,
    createWorkspace,
    workspaceName,
    prompt,
    sourceBranch,
    agentTypeValue,
    registrations,
    defaultModel,
    isKeepOpen,
    onCreated,
  ]);

  // Effects — Cmd+Enter creates from anywhere in the form. An overlay open over
  // the form (e.g. the Add Repository dialog or an open Select) owns Cmd+Enter for
  // its own action. The form's OWN host modal is ignored: when rendered inside the
  // new-workspace dialog the form is itself within a `role="dialog"`, so without the
  // ignore it would always treat its own modal as a blocker and Cmd+Enter would
  // never fire. The inline first-run form has no host dialog, so the ignore is null.
  useEffect(() => {
    const handleGlobalKeyDown = (e: KeyboardEvent): void => {
      if (e.key !== "Enter" || !isModifierPressed(e)) return;
      const hostDialog = formRef.current?.closest('[role="dialog"][data-state="open"]') ?? null;
      if (isDismissibleOverlayOpen(hostDialog)) return;
      e.preventDefault();
      void handleSubmit();
    };
    document.addEventListener("keydown", handleGlobalKeyDown);
    return (): void => document.removeEventListener("keydown", handleGlobalKeyDown);
  }, [handleSubmit]);

  // JSX and rendering logic
  if (isLoadingProjects) {
    return (
      <Flex align="center" justify="center" className={styles.loading}>
        <Spinner size="3" />
      </Flex>
    );
  }

  return (
    <>
      <Flex ref={formRef} direction="column" className={styles.form} data-testid={ElementIds.NEW_WORKSPACE_FORM}>
        <input
          ref={nameInputRef}
          type="text"
          value={workspaceName}
          onChange={(e): void => setWorkspaceName(e.target.value)}
          placeholder="Untitled workspace"
          className={styles.titleInput}
          data-testid={ElementIds.WORKSPACE_NAME_INPUT}
          autoFocus
        />

        <textarea
          ref={promptTextareaRef}
          value={prompt}
          onChange={(e): void => setPrompt(e.target.value)}
          placeholder="Describe a task for the agent (optional)"
          className={styles.promptTextarea}
          data-testid={ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA}
          rows={2}
        />

        <Flex align="center" gap="4" wrap="wrap" className={styles.contextRow}>
          <RepoSelector
            projects={projects}
            selectedProjectId={selectedProjectId}
            onProjectChange={handleProjectChange}
          />

          <AgentTypeSelect value={agentTypeValue} onChange={setAgentTypeValue} />

          <ModeSelect value={mode} onChange={handleModeChange} />

          {repoInfo ? (
            mode === WorkspaceInitializationStrategy.IN_PLACE ? (
              <Tooltip content="In-place workspaces use the current branch in your repository">
                <span style={{ display: "flex" }}>
                  <BranchSelector
                    fetchRepoInfo={fetchRepoInfo}
                    repoInfo={repoInfo}
                    setUserSelectedBranch={setUserSelectedBranch}
                    sourceBranch={sourceBranch}
                    disabled={true}
                    triggerVariant="ghost"
                  />
                </span>
              </Tooltip>
            ) : (
              <BranchSelector
                fetchRepoInfo={fetchRepoInfo}
                repoInfo={repoInfo}
                setUserSelectedBranch={setUserSelectedBranch}
                sourceBranch={sourceBranch}
                triggerVariant="ghost"
              />
            )
          ) : null}
        </Flex>

        <BranchNameField
          mode={mode}
          value={effectiveBranchName}
          isManuallyEdited={isBranchNameManuallyEdited}
          isLoading={isBranchNamePreviewLoading}
          collision={branchNameCollision}
          preview={branchNamePreview}
          onUserEdit={(value): void => setBranchNameOverride(value)}
          onReset={(): void => setBranchNameOverride(null)}
          onShuffle={handleShuffle}
          disabled={isCreating}
        />

        <Flex align="center" justify="between" className={styles.footer}>
          <Text as="label" size="1" className={styles.keepOpenLabel}>
            <Switch
              size="1"
              checked={isKeepOpen}
              onCheckedChange={setIsKeepOpen}
              data-testid={ElementIds.NEW_WORKSPACE_KEEP_OPEN_SWITCH}
            />
            Keep open
          </Text>

          <Flex align="center" gap="3">
            <KeyboardHint keys={`${getMetaKey()}↵`} label="create" />
            <Button
              onClick={(): void => void handleSubmit()}
              disabled={isSubmitDisabled}
              aria-label="Create workspace"
              data-testid={ElementIds.NEW_WORKSPACE_CREATE_BUTTON}
              size="2"
            >
              Create workspace
            </Button>
          </Flex>
        </Flex>
      </Flex>

      <Toast
        open={!!toast}
        onOpenChange={(open) => !open && setToast(null)}
        description={toast?.description}
        duration={5000}
        title={toast?.title}
        type={toast?.type}
      />
    </>
  );
};
