import { Button, Skeleton, Switch, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { EffortLevel } from "~/api";
import {
  ElementIds,
  getActiveProjects,
  getMostRecentlyUsedProject,
  type LlmModel,
  WorkspaceInitializationStrategy,
} from "~/api";
import { isDismissibleOverlayOpen } from "~/common/overlayUtils.ts";
import { lastUsedAgentTypeAtom, type StoredAgentType } from "~/common/state/atoms/agentTabs.ts";
import { projectsArrayAtom, updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import {
  defaultEffortLevelAtom,
  defaultModelAtom,
  isDefaultFastModeAtom,
  isPiAgentEnabledAtom,
} from "~/common/state/atoms/userConfig.ts";
import { useCreateWorkspace } from "~/common/state/hooks/useCreateWorkspace.ts";
import { useRepoInfo } from "~/common/state/hooks/useRepoInfo.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import { AgentSettingsControls } from "~/components/AgentSettingsControls.tsx";
import { BranchSelector } from "~/components/BranchSelector.tsx";
import { KeyboardHint } from "~/components/KeyboardHint.tsx";
import { AgentTypeSelect } from "~/components/newWorkspace/AgentTypeSelect.tsx";
import { BranchNameField } from "~/components/newWorkspace/BranchNameField.tsx";
import { useBranchNamePreview } from "~/components/newWorkspace/hooks/useBranchNamePreview.ts";
import { ModeSelect } from "~/components/newWorkspace/ModeSelect.tsx";
import {
  keepNewWorkspaceModalOpenAtom,
  lastWorkspaceCreationSettingsAtom,
} from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { RepoSelector } from "~/components/RepoSelector.tsx";
import { resolveStoredAgentType } from "~/components/sections/addPanelCore.ts";
import { Toast, type ToastContent, ToastType } from "~/components/Toast.tsx";
import { getMetaKey, isModifierPressed } from "~/electron/utils.ts";

import styles from "./NewWorkspaceForm.module.scss";

const PROMPT_MAX_TEXTAREA_HEIGHT_PX = 240;

type NewWorkspaceFormProps = {
  /** Repo to pre-select (from a repo group's "+"); overrides the MRU seed. */
  presetProjectId?: string;
  /**
   * Text to seed the prompt textarea with on mount. Used by the empty
   * first-run page to default the very first prompt to `/sculptor:help`.
   * A mount-time snapshot the user can freely edit.
   */
  initialPrompt?: string;
  /** Called after a successful create when "keep open" is off. */
  onCreated: () => void;
};

/**
 * The new-workspace form: a borderless title input, an auto-growing
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
  const defaultEffortLevel = useAtomValue(defaultEffortLevelAtom);
  const isDefaultFastMode = useAtomValue(isDefaultFastModeAtom);
  const [isKeepOpen, setIsKeepOpen] = useAtom(keepNewWorkspaceModalOpenAtom);

  // Per-prompt agent-settings overrides — model / effort / fast mode / plan
  // mode. Seeded once from the user's defaults; surfaced beneath the prompt only
  // after the user has typed something (no prompt → the defaults apply silently
  // on create). The form remounts per open (keyed on the preset repo), so these
  // re-seed from the current defaults each time rather than staying sticky.
  const [agentModel, setAgentModel] = useState<LlmModel>(defaultModel as LlmModel);
  const [agentEffort, setAgentEffort] = useState<EffortLevel>(defaultEffortLevel as EffortLevel);
  const [isAgentFastMode, setIsAgentFastMode] = useState<boolean>(isDefaultFastMode);
  const [isAgentPlanMode, setIsAgentPlanMode] = useState<boolean>(false);

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
    // The shared pi-disabled fallback. A bare "terminal" stays: it is a
    // legitimate first-agent choice here.
    return resolveStoredAgentType(seed, isPiAgentEnabled);
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
  const { repoInfo, fetchRepoInfo, fetchCurrentBranch } = useRepoInfo(selectedProjectId);
  const { isCreating, createWorkspace } = useCreateWorkspace();
  const nameInputRef = useRef<HTMLInputElement>(null);
  const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const formRef = useRef<HTMLDivElement>(null);

  const isBranchNameManuallyEdited = branchNameOverride !== null;
  const {
    displayedValue: effectiveBranchName,
    isLoading: isBranchNamePreviewLoading,
    status: branchNameStatus,
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

  // Effects — auto-select a repo the moment it's added through the RepoSelector's
  // Add Repository dialog, so the user lands on the repo they just added instead
  // of having to pick it from the dropdown. Tracks the previously-seen project
  // ids and selects whichever id appears that wasn't there before.
  const prevProjectIdsRef = useRef<Set<string>>(new Set(projects.map((p) => p.objectId)));
  useEffect(() => {
    const addedProjects = projects.filter((p) => !prevProjectIdsRef.current.has(p.objectId));
    prevProjectIdsRef.current = new Set(projects.map((p) => p.objectId));
    if (addedProjects.length === 0) return;
    // A freshly added repo replaces the selection, so branch choices made
    // against the previous repo no longer apply.
    setSelectedProjectId(addedProjects[addedProjects.length - 1].objectId);
    setBranchNameOverride(null);
    setUserSelectedBranch(undefined);
  }, [projects]);

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
    (repoInfo !== null && repoInfo.recentBranches?.length === 0) ||
    // A name the validator has flagged — illegal ref or existing branch — hard
    // blocks Create; the backend re-checks at create time as the backstop.
    branchNameStatus === "exists" ||
    branchNameStatus === "invalid";

  const handleSubmit = useCallback(async (): Promise<void> => {
    if (isSubmitDisabled || selectedProjectId === null) return;

    const result = await createWorkspace({
      projectId: selectedProjectId,
      workspaceName,
      prompt,
      mode,
      sourceBranch,
      branchName: effectiveBranchName,
      agentTypeValue,
      registrations,
      defaultModel: agentModel,
      effort: agentEffort,
      fastMode: isAgentFastMode,
      enterPlanMode: isAgentPlanMode,
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
      // Keep the dialog open for rapid multi-create — reset the
      // per-workspace fields but retain the repo + agent type (+ mode/source)
      // and the per-prompt agent settings. Plan mode is the exception: it is
      // a per-task choice, so it resets to off rather than silently carrying
      // into the next workspace.
      setWorkspaceName("");
      setPrompt("");
      setIsAgentPlanMode(false);
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
    agentModel,
    agentEffort,
    isAgentFastMode,
    isAgentPlanMode,
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
  //
  // The form renders immediately from cached state rather than blocking behind a
  // spinner: `projects` and the per-project `repoInfo` are session atoms, so a
  // repeat open paints instantly. Only genuinely-cold pieces fall back to a
  // skeleton — the repo crumb until a project resolves, and the source-branch
  // chip until its `repoInfo` arrives (a fresh fetch on every open, since the
  // source branch is the one field we always re-source from git).

  // Breadcrumb repo crumb — an avatar initial + repo name, in place of the
  // default `📁 repo <name>` trigger, so the top context row reads like a
  // Linear-style breadcrumb.
  const currentProject = projects.find((p) => p.objectId === selectedProjectId);
  const crumbName = currentProject?.name ?? "Select repo";
  const crumbInitial = (currentProject?.name?.trim()?.[0] ?? "?").toUpperCase();
  const isPromptEmpty = prompt.trim() === "";

  // Skeleton the crumb only on a cold first open (no cached project resolved yet
  // while the initial project fetch is in flight); otherwise the real selector
  // renders. With zero repos the selector is a disabled "Select repo" chip (its
  // trigger can't open, so there is no add-repo affordance in that state).
  const isRepoCrumbLoading = isLoadingProjects && !currentProject;

  return (
    <>
      <div ref={formRef} className={styles.shell} data-testid={ElementIds.NEW_WORKSPACE_FORM}>
        {/* ── Top breadcrumb: repo crumb → agent → environment → source → new branch ── */}
        <div className={styles.context}>
          {isRepoCrumbLoading ? (
            <Skeleton className={styles.crumbSkeleton} />
          ) : (
            <RepoSelector
              projects={projects}
              selectedProjectId={selectedProjectId}
              onProjectChange={handleProjectChange}
              className={styles.crumbTrigger}
              triggerContent={
                <span className={styles.crumb}>
                  <span className={styles.crumbIco} aria-hidden>
                    {crumbInitial}
                  </span>
                  <span className={styles.crumbName}>{crumbName}</span>
                </span>
              }
            />
          )}

          <AgentTypeSelect value={agentTypeValue} onChange={setAgentTypeValue} className={styles.toolbarPill} />

          <ModeSelect value={mode} onChange={handleModeChange} className={styles.toolbarPill} />

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
                    className={styles.toolbarPill}
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
                className={styles.toolbarPill}
              />
            )
          ) : selectedProjectId || isLoadingProjects ? (
            <Skeleton className={styles.branchSkeleton} />
          ) : null}
        </div>

        {/* ── Body: title (+ branch subtitle) + first-task prompt ── */}
        <div className={styles.body}>
          <div className={styles.titleGroup}>
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

            {/* Borderless, iconless branch — reads as an editable subtitle of the
                title (worktree/clone only; in-place uses the current branch). */}
            {mode !== WorkspaceInitializationStrategy.IN_PLACE ? (
              <BranchNameField
                mode={mode}
                value={effectiveBranchName}
                isManuallyEdited={isBranchNameManuallyEdited}
                isLoading={isBranchNamePreviewLoading}
                status={branchNameStatus}
                onUserEdit={(value): void => setBranchNameOverride(value)}
                onShuffle={handleShuffle}
                disabled={isCreating}
                variant="plain"
              />
            ) : null}
          </div>

          <textarea
            ref={promptTextareaRef}
            value={prompt}
            onChange={(e): void => setPrompt(e.target.value)}
            placeholder="Describe a task for the agent (optional)"
            className={styles.promptTextarea}
            data-testid={ElementIds.NEW_WORKSPACE_PROMPT_TEXTAREA}
            rows={2}
          />

          {/* Per-prompt agent settings (plan / fast / effort / model). Always
              rendered so the row reserves its space; hidden via `visibility`
              until the user has typed a prompt so the modal doesn't jump. */}
          <div className={styles.agentSettings} data-visible={!isPromptEmpty} aria-hidden={isPromptEmpty}>
            <AgentSettingsControls
              model={agentModel}
              onModelChange={setAgentModel}
              effort={agentEffort}
              onEffortChange={setAgentEffort}
              isFastMode={isAgentFastMode}
              onFastModeToggle={(): void => setIsAgentFastMode((v) => !v)}
              isPlanMode={isAgentPlanMode}
              onPlanModeToggle={(): void => setIsAgentPlanMode((v) => !v)}
            />
          </div>
        </div>

        {/* ── Footer: keep-open toggle + Cmd+Enter hint + Create ── */}
        <div className={styles.footer}>
          <div className={styles.footerLeft}>
            <label className={styles.keepOpenLabel}>
              <Switch
                size="1"
                checked={isKeepOpen}
                onCheckedChange={setIsKeepOpen}
                data-testid={ElementIds.NEW_WORKSPACE_KEEP_OPEN_SWITCH}
              />
              Keep open
            </label>
          </div>

          <div className={styles.footerRight}>
            {!isSubmitDisabled ? (
              <span className={styles.shortcutHint}>
                <KeyboardHint keys={`${getMetaKey()}↵`} label="to create" />
              </span>
            ) : null}
            <Button
              onClick={(): void => void handleSubmit()}
              disabled={isSubmitDisabled}
              aria-label="Create workspace"
              data-testid={ElementIds.NEW_WORKSPACE_CREATE_BUTTON}
              size="2"
              color="indigo"
            >
              Create workspace
            </Button>
          </div>
        </div>
      </div>

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
