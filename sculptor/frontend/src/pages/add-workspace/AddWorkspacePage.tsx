import { Flex, Select, Spinner, Text } from "@radix-ui/themes";
import { useAtomValue, useSetAtom } from "jotai";
import { BlocksIcon, BotIcon } from "lucide-react";
import { posthog } from "posthog-js";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";

import type { LlmModel } from "../../api";
import {
  createWorkspaceAgent,
  createWorkspaceV2,
  ElementIds,
  getActiveProjects,
  getMostRecentlyUsedProject,
  HarnessName,
  WorkspaceInitializationStrategy,
} from "../../api";
import { HTTPException } from "../../common/Errors.ts";
import { useIsMobile } from "../../common/hooks/useLayoutMode.ts";
import { useImbueNavigate } from "../../common/NavigateUtils.ts";
import { projectsArrayAtom, updateProjectsAtom } from "../../common/state/atoms/projects.ts";
import {
  defaultModelAtom,
  isCloneWorkspacesEnabledAtom,
  isInPlaceWorkspacesEnabledAtom,
  isMultiHarnessEnabledAtom,
} from "../../common/state/atoms/userConfig.ts";
import {
  clearDraftCreatingAtom,
  convertNewWorkspaceToTabAtom,
  markDraftCreatingAtom,
} from "../../common/state/atoms/workspaces.ts";
import { useDraftTabName } from "../../common/state/hooks/usePromptDraft.ts";
import { useRepoInfo } from "../../common/state/hooks/useRepoInfo.ts";
import { RepoSelector } from "../../components/RepoSelector.tsx";
import { Toast, type ToastContent, ToastType } from "../../components/Toast.tsx";
import styles from "./AddWorkspacePage.module.scss";
import { BranchNameField } from "./components/BranchNameField.tsx";
import { NewWorkspaceForm } from "./components/NewWorkspaceForm.tsx";
import { useBranchNamePreview } from "./hooks/useBranchNamePreview.ts";
import { MobileNewWorkspace } from "./MobileNewWorkspace.tsx";

export const AddWorkspacePage = (): ReactElement => {
  const { draftId } = useParams<{ draftId: string }>();
  if (!draftId) {
    throw new Error("AddWorkspacePage requires a draftId route parameter");
  }
  const { navigateToAgent } = useImbueNavigate();
  const isMobile = useIsMobile();
  const isInPlaceWorkspacesEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneWorkspacesEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);
  const isMultiHarnessEnabled = useAtomValue(isMultiHarnessEnabledAtom);
  // Worktree mode is always the default; the selector only appears when an
  // opt-in mode (clone or in-place) has been enabled and the user has more
  // than one option to choose from.
  const isModeSelectorVisible = isInPlaceWorkspacesEnabled || isCloneWorkspacesEnabled;
  const defaultModelPreference = useAtomValue(defaultModelAtom);
  const convertNewWorkspaceToTab = useSetAtom(convertNewWorkspaceToTabAtom);
  const markDraftCreating = useSetAtom(markDraftCreatingAtom);
  const clearDraftCreating = useSetAtom(clearDraftCreatingAtom);
  const nameInputRef = useRef<HTMLInputElement>(null);

  // Project state — read from global atom so AddRepoDialog updates are reflected immediately
  const projects = useAtomValue(projectsArrayAtom);
  const updateProjects = useSetAtom(updateProjectsAtom);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [isLoadingProjects, setIsLoadingProjects] = useState(true);

  // Form state. Worktree is the default mode; clone and in-place are opt-in.
  const [mode, setMode] = useState<WorkspaceInitializationStrategy>(WorkspaceInitializationStrategy.WORKTREE);
  // DELIBERATE-TEMPORARY: workspace-bound harness selection.
  const [harness, setHarness] = useState<HarnessName>(HarnessName.CLAUDE);
  const [workspaceNameDraft, setWorkspaceNameDraft] = useDraftTabName(draftId);
  const workspaceName = workspaceNameDraft ?? "";
  const setWorkspaceName = useCallback(
    (value: string) => setWorkspaceNameDraft(value || null),
    [setWorkspaceNameDraft],
  );
  const [isPending, setIsPending] = useState(false);
  const [toast, setToast] = useState<ToastContent | null>(null);
  // `null` means "use the auto-filled preview"; any string means the user has
  // taken over and we render their override. Both the value and the manual flag
  // collapse into one piece of state so they can never disagree.
  const [branchNameOverride, setBranchNameOverride] = useState<string | null>(null);
  const isBranchNameManuallyEdited = branchNameOverride !== null;
  // Bumped to pull a fresh auto-generated branch name (mobile "regenerate" ⇄).
  const [regenerationNonce, setRegenerationNonce] = useState(0);
  // `null` means "branch from the derived default" (origin/main). A string is
  // the user's explicit source-branch pick (mobile Source pill). Desktop has no
  // source picker, so this stays null there.
  const [userSelectedSourceBranch, setUserSelectedSourceBranch] = useState<string | null>(null);

  const handleModeChange = useCallback((nextMode: WorkspaceInitializationStrategy): void => {
    setMode(nextMode);
    setBranchNameOverride(null);
  }, []);

  const handleProjectChange = useCallback((nextProjectId: string | null): void => {
    setSelectedProjectId(nextProjectId);
    setBranchNameOverride(null);
    setUserSelectedSourceBranch(null);
  }, []);

  // Drop any manual edit and pull a fresh auto-generated name from the backend.
  const handleRegenerateBranchName = useCallback((): void => {
    setBranchNameOverride(null);
    setRegenerationNonce((n) => n + 1);
  }, []);

  // Single source of truth for the branch-name field. The hook owns preview
  // fetching and the debounced collision check; the parent owns the override.
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
    regenerationNonce,
  });

  // Repo info for the selected project
  const { repoInfo, fetchRepoInfo, fetchCurrentBranch } = useRepoInfo(selectedProjectId ?? "");

  // New workspaces always branch from the latest upstream default (origin/main)
  // so they start from the freshest state; there is no source-branch picker.
  // Fall back to origin/master, then the repo's current branch, for repos
  // without an origin/main (e.g. a local-only or master-default repo).
  const sourceBranch = useMemo(() => {
    const remoteDefault =
      repoInfo?.remoteBranches?.find((branch) => branch === "origin/main") ??
      repoInfo?.remoteBranches?.find((branch) => branch === "origin/master");
    return remoteDefault ?? repoInfo?.currentBranch;
  }, [repoInfo]);

  // The branch new work forks from: the user's explicit pick (mobile Source
  // pill) if any, otherwise the derived default. Desktop never sets an override
  // so it keeps branching from origin/main exactly as before.
  const effectiveSourceBranch = userSelectedSourceBranch ?? sourceBranch;

  // Load projects on mount into global atom
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

        // Default to MRU project (response is a project ID string), fallback to first project
        const mruProjectId = mruResponse.data;
        if (mruProjectId && activeProjects.some((p) => p.objectId === mruProjectId)) {
          setSelectedProjectId(mruProjectId);
        } else if (activeProjects.length > 0) {
          setSelectedProjectId(activeProjects[0].objectId);
        }
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

  // Auto-select newly added projects
  const prevProjectIdsRef = useRef(new Set(projects.map((p) => p.objectId)));
  useEffect(() => {
    const currentIds = new Set(projects.map((p) => p.objectId));
    const newIds = projects.filter((p) => !prevProjectIdsRef.current.has(p.objectId));
    prevProjectIdsRef.current = currentIds;

    if (newIds.length > 0) {
      setSelectedProjectId(newIds[newIds.length - 1].objectId);
    }
  }, [projects]);

  // Refresh branch info when project changes
  useEffect(() => {
    if (!selectedProjectId) return;
    fetchCurrentBranch();
    fetchRepoInfo();
  }, [selectedProjectId, fetchCurrentBranch, fetchRepoInfo]);

  const handleSubmit = useCallback(async (): Promise<void> => {
    if (isPending || !selectedProjectId) return;

    const trimmedBranch = effectiveBranchName.trim();
    if (mode === WorkspaceInitializationStrategy.WORKTREE && !trimmedBranch) {
      setToast({
        title: "Branch name is required for worktree workspaces",
        type: ToastType.ERROR,
      });
      return;
    }

    const requestedBranchName =
      mode === WorkspaceInitializationStrategy.IN_PLACE
        ? undefined
        : mode === WorkspaceInitializationStrategy.WORKTREE
          ? trimmedBranch
          : trimmedBranch || undefined;

    setIsPending(true);
    try {
      // Signal that this pseudo-tab is creating a workspace so the WebSocket
      // handler (updateWorkspacesAtom) won't auto-open the new workspace as
      // a duplicate tab.  The flag is cleared by convertNewWorkspaceToTab.
      markDraftCreating(draftId);

      // Create workspace
      const wsResponse = await createWorkspaceV2({
        body: {
          projectId: selectedProjectId,
          initializationStrategy: mode,
          sourceBranch: mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : effectiveSourceBranch,
          description: workspaceName.trim() || "Untitled workspace",
          requestedBranchName,
          harness,
        },
      });

      if (!wsResponse.data) {
        throw new Error("Failed to create workspace — no response data");
      }

      const workspaceId = wsResponse.data.objectId;

      // The API call waits for WebSocket confirmation (via request tracker),
      // so the workspace is already in workspaceIdsAtom.  Replace the
      // pseudo-tab with the real workspace tab in its same position.
      convertNewWorkspaceToTab({ draftId, workspaceId });
      setWorkspaceNameDraft(null);

      // Create first agent (no prompt in the simplified form)
      const agentResponse = await createWorkspaceAgent({
        path: { workspace_id: workspaceId },
        body: {
          model: defaultModelPreference as LlmModel,
        },
      });

      if (!agentResponse.data) {
        throw new Error("Failed to create agent — no response data");
      }

      posthog.capture("workspace.created", {
        workspace_id: workspaceId,
        agent_id: agentResponse.data.id,
        mode,
        has_workspace_name: workspaceName.trim().length > 0,
        // Branch names are user-entered text (they can encode feature/ticket/
        // customer names), so record only whether one was chosen.
        has_source_branch: effectiveSourceBranch != null,
      });

      // Navigate to the new workspace + agent
      navigateToAgent(workspaceId, agentResponse.data.id);
    } catch (error) {
      // Clear the pending-creation flag so auto-open resumes normally.
      clearDraftCreating(draftId);
      console.error("Failed to create workspace:", error);
      if (error instanceof HTTPException && error.status === 409) {
        setToast({
          title: `Branch '${trimmedBranch}' already exists`,
          type: ToastType.ERROR,
        });
      } else {
        setToast({
          title: "",
          description: (
            <div>
              <b>Failed to create workspace</b>
              <br />
              <pre>{"" + error}</pre>
            </div>
          ),
          type: ToastType.ERROR,
        });
      }
    } finally {
      setIsPending(false);
    }
  }, [
    isPending,
    selectedProjectId,
    draftId,
    mode,
    harness,
    effectiveSourceBranch,
    workspaceName,
    effectiveBranchName,
    defaultModelPreference,
    navigateToAgent,
    setWorkspaceNameDraft,
    convertNewWorkspaceToTab,
    markDraftCreating,
    clearDraftCreating,
  ]);

  // When nothing on the page has meaningful focus, arrow keys should move
  // focus to the workspace name input so the user can start navigating.
  useEffect(() => {
    const handleArrowKey = (e: KeyboardEvent): void => {
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;

      // Only intercept when focus is on the document body (i.e. nothing
      // interactive is focused). Other elements like inputs and the
      // recent workspaces area have their own arrow key handlers.
      if (document.activeElement !== document.body) return;

      e.preventDefault();
      nameInputRef.current?.focus();
    };

    document.addEventListener("keydown", handleArrowKey);
    return (): void => document.removeEventListener("keydown", handleArrowKey);
  }, []);

  if (isLoadingProjects) {
    return (
      <Flex align="center" justify="center" height="var(--app-height)">
        <Spinner size="3" />
      </Flex>
    );
  }

  // The single mobile branch point for the landing (L1-L4). MobileNewWorkspace
  // is pure presentation over the same create-workspace core wired above —
  // name draft, project selection, sourceBranch default, and handleSubmit are
  // passed straight in, so nothing is duplicated.
  if (isMobile) {
    return (
      <MobileNewWorkspace
        workspaceName={workspaceName}
        onWorkspaceNameChange={setWorkspaceName}
        nameInputRef={nameInputRef}
        isPending={isPending}
        onSubmit={handleSubmit}
        projects={projects}
        selectedProjectId={selectedProjectId}
        onProjectChange={handleProjectChange}
        repoInfo={repoInfo}
        fetchRepoInfo={fetchRepoInfo}
        branchName={effectiveBranchName}
        isBranchNameLoading={isBranchNamePreviewLoading}
        branchNameCollision={branchNameCollision}
        onBranchNameChange={setBranchNameOverride}
        onRegenerateBranchName={handleRegenerateBranchName}
        sourceBranch={effectiveSourceBranch}
        onSourceBranchChange={setUserSelectedSourceBranch}
      />
    );
  }

  return (
    <>
      <Flex direction="column" align="center" justify="center" className={styles.container}>
        <Flex direction="column" align="center" gap="5" className={styles.content}>
          <Text className={styles.headerTitle}>Name your workspace</Text>

          <NewWorkspaceForm
            workspaceName={workspaceName}
            onWorkspaceNameChange={setWorkspaceName}
            nameInputRef={nameInputRef}
            repoInfo={repoInfo}
            isPending={isPending}
            isSubmitDisabled={
              mode === WorkspaceInitializationStrategy.WORKTREE &&
              (effectiveBranchName.trim() === "" || isBranchNamePreviewLoading)
            }
            onSubmit={handleSubmit}
            autoFocus
            branchField={
              <BranchNameField
                mode={mode}
                value={effectiveBranchName}
                isManuallyEdited={isBranchNameManuallyEdited}
                isLoading={isBranchNamePreviewLoading}
                collision={branchNameCollision}
                preview={branchNamePreview}
                onUserEdit={(value): void => setBranchNameOverride(value)}
                onReset={(): void => setBranchNameOverride(null)}
                disabled={isPending}
              />
            }
          >
            {/* Project/repo selector */}
            <RepoSelector
              projects={projects}
              selectedProjectId={selectedProjectId}
              onProjectChange={handleProjectChange}
              className={styles.compactSelector}
            />

            {/* Harness selector — gated behind the experimental multi-harness flag.
                When off, the picker is hidden and `harness` stays Claude, so new
                workspaces use Claude exactly as they did before multi-harness shipped.
                DELIBERATE-TEMPORARY: workspace-bound harness selection. */}
            {isMultiHarnessEnabled && (
              <Select.Root size="1" value={harness} onValueChange={(value) => setHarness(value as HarnessName)}>
                <Select.Trigger
                  variant="ghost"
                  className={styles.compactSelector}
                  data-testid={ElementIds.HARNESS_SELECTOR}
                >
                  <Flex align="center" gap="1">
                    <BotIcon size={12} />
                    <Text className={styles.selectorLabel}>harness</Text>
                    {harness === HarnessName.PI ? "pi (experimental)" : "Claude"}
                  </Flex>
                </Select.Trigger>
                <Select.Content position="popper" side="bottom" sideOffset={5}>
                  <Select.Item value={HarnessName.CLAUDE} data-testid={ElementIds.HARNESS_OPTION_CLAUDE}>
                    Claude
                  </Select.Item>
                  <Select.Item value={HarnessName.PI} data-testid={ElementIds.HARNESS_OPTION_PI}>
                    pi (experimental)
                  </Select.Item>
                </Select.Content>
              </Select.Root>
            )}

            {/* Mode selector — shown when any experimental workspace mode is enabled */}
            {isModeSelectorVisible && (
              <Select.Root
                size="1"
                value={mode}
                onValueChange={(value) => handleModeChange(value as WorkspaceInitializationStrategy)}
              >
                <Select.Trigger
                  variant="ghost"
                  className={styles.compactSelector}
                  data-testid={ElementIds.MODE_SELECTOR}
                >
                  <Flex align="center" gap="1">
                    <BlocksIcon size={12} />
                    <Text className={styles.selectorLabel}>environment</Text>
                    {mode === WorkspaceInitializationStrategy.IN_PLACE
                      ? "In-place"
                      : mode === WorkspaceInitializationStrategy.WORKTREE
                        ? "Worktree"
                        : "Clone"}
                  </Flex>
                </Select.Trigger>
                <Select.Content position="popper" side="bottom" sideOffset={5}>
                  <Select.Item
                    value={WorkspaceInitializationStrategy.WORKTREE}
                    data-testid={ElementIds.MODE_OPTION_WORKTREE}
                  >
                    Worktree
                  </Select.Item>
                  {isCloneWorkspacesEnabled && (
                    <Select.Item
                      value={WorkspaceInitializationStrategy.CLONE}
                      data-testid={ElementIds.MODE_OPTION_CLONE}
                    >
                      Clone
                    </Select.Item>
                  )}
                  {isInPlaceWorkspacesEnabled && (
                    <Select.Item
                      value={WorkspaceInitializationStrategy.IN_PLACE}
                      data-testid={ElementIds.MODE_OPTION_IN_PLACE}
                    >
                      In-place
                    </Select.Item>
                  )}
                </Select.Content>
              </Select.Root>
            )}
          </NewWorkspaceForm>
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
