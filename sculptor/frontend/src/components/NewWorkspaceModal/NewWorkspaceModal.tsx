import { Button, Flex, IconButton, Select, Spinner, Switch, Text, Tooltip } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { BlocksIcon, X } from "lucide-react";
import type { KeyboardEvent, ReactElement } from "react";
import { useCallback, useEffect, useRef, useState } from "react";

import {
  createWorkspaceAgent,
  createWorkspaceV2,
  EffortLevel,
  ElementIds,
  getActiveProjects,
  getMostRecentlyUsedProject,
  type LlmModel,
  sendWorkspaceAgentMessages,
  WorkspaceInitializationStrategy,
} from "../../api";
import { HTTPException } from "../../common/Errors.ts";
import { useImbueNavigate } from "../../common/NavigateUtils.ts";
import { projectsArrayAtom, updateProjectsAtom } from "../../common/state/atoms/projects.ts";
import {
  defaultEffortLevelAtom,
  defaultModelAtom,
  isCloneWorkspacesEnabledAtom,
  isDefaultFastModeAtom,
  isInPlaceWorkspacesEnabledAtom,
} from "../../common/state/atoms/userConfig.ts";
import { useRepoInfo } from "../../common/state/hooks/useRepoInfo.ts";
import { getMetaKey, isModifierPressed } from "../../electron/utils.ts";
import { AgentSettingsControls } from "../AgentSettingsControls.tsx";
import { BranchSelector } from "../BranchSelector.tsx";
import { commandPaletteOpenAtom } from "../CommandPalette/atoms.ts";
import { KeyboardHint } from "../KeyboardHint.tsx";
import { PaletteDialog } from "../PaletteDialog";
import { RepoSelector } from "../RepoSelector.tsx";
import { Toast, type ToastContent, ToastType } from "../Toast.tsx";
import {
  draftBranchNameOverrideAtom,
  draftInitializationModeAtom,
  draftInitialPromptAtom,
  draftSelectedProjectIdAtom,
  draftUserSelectedBranchAtom,
  draftWorkspaceNameAtom,
  newWorkspaceModalEntrySourceAtom,
  newWorkspaceModalOpenAtom,
  resetDraftAtom,
} from "./atoms.ts";
import { BranchNameField } from "./BranchNameField.tsx";
import { validateBranchName } from "./branchNameValidation.ts";
import styles from "./NewWorkspaceModal.module.scss";
import { useBranchNamePreview } from "./useBranchNamePreview.ts";

export const NewWorkspaceModal = (): ReactElement => {
  const [isOpen, setIsOpen] = useAtom(newWorkspaceModalOpenAtom);
  const entrySource = useAtomValue(newWorkspaceModalEntrySourceAtom);
  const setCommandPaletteOpen = useSetAtom(commandPaletteOpenAtom);
  const { navigateToAgent } = useImbueNavigate();

  const isInPlaceEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);
  // Worktree is the always-available default mode; the selector only
  // matters when an alternative (clone or in-place) is opted into.
  const isModeSelectorVisible = isInPlaceEnabled || isCloneEnabled;
  const defaultModelPreference = useAtomValue(defaultModelAtom);
  const defaultEffortLevel = useAtomValue(defaultEffortLevelAtom);
  const isDefaultFastMode = useAtomValue(isDefaultFastModeAtom);

  // Per-prompt agent-settings overrides — model / effort / fast mode /
  // plan mode. Local state seeded from the user's default preferences;
  // only surfaced in the UI once the user has typed an initial prompt
  // (no prompt → the defaults will apply silently). Reset to the
  // current defaults each time the modal opens (see effect below) so
  // overrides are per-task, not sticky across opens, and changes the
  // user makes in Settings flow through without a page reload.
  const [agentModel, setAgentModel] = useState<LlmModel>(defaultModelPreference as LlmModel);
  const [agentEffort, setAgentEffort] = useState<EffortLevel>((defaultEffortLevel as EffortLevel) ?? EffortLevel.XHIGH);
  const [isAgentFastMode, setIsAgentFastMode] = useState<boolean>(isDefaultFastMode);
  const [isAgentPlanMode, setIsAgentPlanMode] = useState<boolean>(false);

  useEffect(() => {
    if (!isOpen) return;
    setAgentModel(defaultModelPreference as LlmModel);
    setAgentEffort((defaultEffortLevel as EffortLevel) ?? EffortLevel.XHIGH);
    setIsAgentFastMode(isDefaultFastMode);
    setIsAgentPlanMode(false);
    // Deliberately only re-fires on the isOpen transition. Including
    // the default-* values in deps would clobber a user's mid-session
    // overrides if their config refreshed (e.g. websocket push) while
    // the modal was open.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isOpen]);

  const projects = useAtomValue(projectsArrayAtom);
  const updateProjects = useSetAtom(updateProjectsAtom);
  const resetDraft = useSetAtom(resetDraftAtom);

  const [workspaceName, setWorkspaceName] = useAtom(draftWorkspaceNameAtom);
  const [selectedProjectId, setSelectedProjectId] = useAtom(draftSelectedProjectIdAtom);
  const [userSelectedBranch, setUserSelectedBranch] = useAtom(draftUserSelectedBranchAtom);
  const [mode, setMode] = useAtom(draftInitializationModeAtom);
  const [branchNameOverride, setBranchNameOverride] = useAtom(draftBranchNameOverrideAtom);
  const [initialPrompt, setInitialPrompt] = useAtom(draftInitialPromptAtom);

  const [isLoadingProjects, setIsLoadingProjects] = useState(false);
  const [hasLoadedProjects, setHasLoadedProjects] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [toast, setToast] = useState<ToastContent | null>(null);
  // "Create more" keeps the modal open after a successful create so
  // the user can fire off several workspaces back-to-back without
  // navigating into each one. Off by default — most users create one
  // workspace and want to land in it. Lives as local state (rather
  // than an atom) so each new modal session starts fresh.
  const [isCreateMore, setIsCreateMore] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const branchInputRef = useRef<HTMLInputElement>(null);

  const isManuallyEditedBranch = branchNameOverride !== null;

  // Lazy-load projects the first time the modal opens. Subsequent opens
  // reuse the global projects atom; AddRepoDialog updates push into it.
  //
  // The in-flight guard is a ref (not the `isLoadingProjects` state) so
  // toggling it doesn't re-trigger the effect mid-fetch; otherwise the
  // cleanup would cancel the load between `setIsLoadingProjects(true)`
  // and the `await`, leaving the loading state stuck on and the submit
  // button permanently disabled.
  const isLoadProjectsInFlightRef = useRef(false);
  useEffect(() => {
    if (!isOpen || hasLoadedProjects || isLoadProjectsInFlightRef.current) return;
    isLoadProjectsInFlightRef.current = true;
    let isCancelled = false;

    const loadProjects = async (): Promise<void> => {
      setIsLoadingProjects(true);
      let didSucceed = false;
      try {
        const [projectsResponse, mruResponse] = await Promise.all([
          getActiveProjects({ meta: { skipWsAck: true } }),
          getMostRecentlyUsedProject({ meta: { skipWsAck: true } }),
        ]);
        if (isCancelled) return;
        const activeProjects = projectsResponse.data ?? [];
        updateProjects(activeProjects);

        // Functional update: only seed a default if the user hasn't
        // already picked a project (the atom persists across opens).
        // Reading via `prev` keeps `selectedProjectId` out of the
        // effect's dep array — otherwise loading would tear down and
        // re-run mid-flight when we set it below.
        const mruProjectId = mruResponse.data;
        setSelectedProjectId((prev) => {
          if (prev != null) return prev;
          if (mruProjectId && activeProjects.some((p) => p.objectId === mruProjectId)) {
            return mruProjectId;
          }

          if (activeProjects.length > 0) {
            return activeProjects[0].objectId;
          }
          return prev;
        });
        didSucceed = true;
      } catch (error) {
        console.error("Failed to load projects:", error);
        if (!isCancelled) {
          setToast({ title: "Failed to load repositories", type: ToastType.ERROR });
        }
      } finally {
        isLoadProjectsInFlightRef.current = false;
        if (!isCancelled) {
          setIsLoadingProjects(false);
          // Only flip the cached-load flag on success. On failure leave it
          // false so the next modal open re-runs this effect — otherwise
          // the user would have to hard-reload the page to recover from a
          // transient backend error.
          if (didSucceed) {
            setHasLoadedProjects(true);
          }
        }
      }
    };

    void loadProjects();
    return (): void => {
      isCancelled = true;
    };
  }, [isOpen, hasLoadedProjects, updateProjects, setSelectedProjectId]);

  // Auto-select newly added projects.
  const prevProjectIdsRef = useRef(new Set(projects.map((p) => p.objectId)));
  useEffect(() => {
    const currentIds = new Set(projects.map((p) => p.objectId));
    const newIds = projects.filter((p) => !prevProjectIdsRef.current.has(p.objectId));
    prevProjectIdsRef.current = currentIds;
    if (newIds.length > 0) {
      setSelectedProjectId(newIds[newIds.length - 1].objectId);
    }
  }, [projects, setSelectedProjectId]);

  // Branch name preview + collision detection.
  const {
    displayedValue: effectiveBranchName,
    isLoading: isBranchNamePreviewLoading,
    collision: branchNameCollision,
    shuffle: shuffleBranchName,
  } = useBranchNamePreview({
    projectId: selectedProjectId,
    workspaceName,
    mode,
    override: branchNameOverride,
  });

  const { repoInfo, fetchRepoInfo, fetchCurrentBranch } = useRepoInfo(selectedProjectId ?? "");

  const sourceBranch = userSelectedBranch ?? repoInfo?.currentBranch;

  // Refresh branch info when the project changes OR the modal opens —
  // the source repo's current branch can change underneath us between
  // opens (a user switching branches in their terminal, or an
  // integration test calling `git checkout` between operations), and a
  // stale `repoInfo.currentBranch` would silently feed the wrong source
  // to createWorkspaceV2.
  useEffect(() => {
    if (!selectedProjectId) return;
    if (!isOpen) return;
    fetchCurrentBranch();
    fetchRepoInfo();
  }, [selectedProjectId, isOpen, fetchCurrentBranch, fetchRepoInfo]);

  // Override Radix's default first-focusable autofocus to land on the
  // title input. preventDefault() suppresses Radix's own focus, and the
  // .focus() call runs synchronously inside the same event so there's
  // no race with the focus trap.
  const handleOpenAutoFocus = useCallback((e: Event): void => {
    e.preventDefault();
    nameInputRef.current?.focus();
  }, []);

  // Recovery shortcuts that fire even when focus is on document.body
  // (Radix's focus trap doesn't keep focus pinned — clicking the
  // overlay or pressing Tab past the last focusable element can leave
  // body active). The per-input arrow handlers below only fire when
  // an input is focused, so without this listener the modal becomes
  // keyboard-dead after a stray blur. Cmd+I mirrors the global
  // `focus_input` keybinding (which is suppressed while a dismissible
  // overlay is open — see usePageLayoutKeyboardShortcuts).
  useEffect(() => {
    if (!isOpen) return;
    const handleWindowKeyDown = (e: globalThis.KeyboardEvent): void => {
      const target = e.target as HTMLElement | null;
      const isInsideInput =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable === true;
      if (isInsideInput) return;
      if (e.key === "ArrowUp" || e.key === "ArrowDown") {
        e.preventDefault();
        nameInputRef.current?.focus();
        return;
      }

      if (e.key === "i" && isModifierPressed(e)) {
        e.preventDefault();
        nameInputRef.current?.focus();
      }
    };
    window.addEventListener("keydown", handleWindowKeyDown);
    return (): void => window.removeEventListener("keydown", handleWindowKeyDown);
  }, [isOpen]);

  const handleModeChange = useCallback(
    (nextMode: WorkspaceInitializationStrategy): void => {
      setMode(nextMode);
      setBranchNameOverride(null);
    },
    [setMode, setBranchNameOverride],
  );

  const handleProjectChange = useCallback(
    (nextProjectId: string): void => {
      setSelectedProjectId(nextProjectId);
      setBranchNameOverride(null);
      setUserSelectedBranch(null);
    },
    [setSelectedProjectId, setBranchNameOverride, setUserSelectedBranch],
  );

  const handleSubmit = useCallback(async (): Promise<void> => {
    if (isPending || !selectedProjectId) return;

    const trimmedBranch = effectiveBranchName.trim();

    // Silently bail when worktree mode requires a branch name we
    // don't have yet. The button's disabled state + the red-border
    // / "required" caption on the field already tell the user why
    // submission isn't happening; a toast on top of that is noise.
    if (mode === WorkspaceInitializationStrategy.WORKTREE && trimmedBranch === "") {
      return;
    }

    // Same silent-bail when the branch name violates git's ref-format
    // rules — submit is already disabled for click, this guards the
    // Cmd+Enter path so an invalid name never reaches the API.
    if (mode !== WorkspaceInitializationStrategy.IN_PLACE && validateBranchName(trimmedBranch) !== null) {
      return;
    }

    const requestedBranchName =
      mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : trimmedBranch === "" ? undefined : trimmedBranch;

    setIsPending(true);
    try {
      const wsResponse = await createWorkspaceV2({
        body: {
          projectId: selectedProjectId,
          initializationStrategy: mode,
          sourceBranch: mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : sourceBranch,
          description: workspaceName.trim() || "Untitled workspace",
          requestedBranchName,
        },
      });

      if (!wsResponse.data) {
        throw new Error("Failed to create workspace — no response data");
      }

      const workspaceId = wsResponse.data.objectId;

      const agentResponse = await createWorkspaceAgent({
        path: { workspace_id: workspaceId },
        body: { model: agentModel },
      });

      if (!agentResponse.data) {
        throw new Error("Failed to create agent — no response data");
      }

      const agentId = agentResponse.data.id;

      // If the user typed an initial prompt, send it as the first
      // message to the new agent before navigating. The agent is
      // ready to receive messages on `createWorkspaceAgent` resolve;
      // sending here (rather than queuing in an atom for the agent
      // UI) keeps the path simple and matches `useChatData.sendMessage`.
      // Per-agent settings (effort / fastMode / planMode) ride along
      // on the same request — same wiring ChatInput uses, so the
      // initial message starts with the user's chosen settings
      // instead of silently snapping to defaults.
      const trimmedPrompt = initialPrompt.trim();
      if (trimmedPrompt) {
        try {
          await sendWorkspaceAgentMessages({
            path: { workspace_id: workspaceId, agent_id: agentId },
            body: {
              message: trimmedPrompt,
              model: agentModel,
              effort: agentEffort,
              fastMode: isAgentFastMode,
              enterPlanMode: isAgentPlanMode || undefined,
            },
          });
        } catch (sendError) {
          // Workspace + agent already exist — surface the prompt
          // failure but still navigate so the user can retry from
          // the agent UI without losing the workspace they created.
          console.error("Failed to send initial prompt:", sendError);
          setToast({
            title: "Workspace created, but the initial message failed to send",
            type: ToastType.ERROR,
          });
        }
      }

      resetDraft();
      if (isCreateMore) {
        // "Create more" mode: stay in the modal, refocus the title so
        // the user can immediately start typing the next one, and
        // surface a toast as the only confirmation that the previous
        // create succeeded (the form has already been reset).
        setToast({
          title: `Workspace "${workspaceName.trim() || "Untitled workspace"}" created`,
          type: ToastType.SUCCESS,
        });
        nameInputRef.current?.focus();
      } else {
        setIsOpen(false);
        navigateToAgent(workspaceId, agentId);
      }
    } catch (error) {
      console.error("Failed to create workspace:", error);
      if (error instanceof HTTPException && error.status === 409) {
        setToast({ title: `Branch '${trimmedBranch}' already exists`, type: ToastType.ERROR });
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
    effectiveBranchName,
    mode,
    sourceBranch,
    workspaceName,
    initialPrompt,
    agentModel,
    agentEffort,
    isAgentFastMode,
    isAgentPlanMode,
    navigateToAgent,
    resetDraft,
    setIsOpen,
    isCreateMore,
  ]);

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLDivElement>): void => {
      // Cmd+Enter submits from anywhere in the modal.
      if (e.key === "Enter" && isModifierPressed(e.nativeEvent)) {
        e.preventDefault();
        e.stopPropagation();
        void handleSubmit();
      }
    },
    [handleSubmit],
  );

  // Esc / back-arrow handling for the "entered via Cmd+K" path: Esc
  // (or an ArrowLeft on an empty focused input — see below) returns
  // the user to the command palette command list. The modal closes,
  // the palette re-opens — only one of the two surfaces is on screen
  // at a time, so this re-creates the "swap in place" feel without
  // two overlapping overlays. Declared here so the arrow-key handlers
  // below can close over it.
  const returnToPalette = useCallback((): void => {
    setIsOpen(false);
    setCommandPaletteOpen(true);
  }, [setIsOpen, setCommandPaletteOpen]);

  // ── Arrow-key navigation between the three primary inputs ──────────
  //
  // Branch ⇅ Title ⇅ Prompt — matches the visual stack (branch field
  // sits between the context bar and the title now). The textarea
  // preserves its multi-line cursor movement: ArrowUp only escapes
  // when the caret is on the first line. The two single-line inputs
  // hijack the keys unconditionally — there's no intra-input vertical
  // movement to lose.
  //
  // When entered from Cmd+K, ArrowLeft with the caret at position 0
  // (and no selection) returns to the palette — matches the palette's
  // own back-affordance, which uses the same `selectionEnd === 0` test.
  // Comparing the caret position (rather than `value === ""`) preserves
  // ordinary mid-input caret movement once the user has typed anything.
  // Modifier keys mean it's a text-edit gesture (extend selection, jump
  // to line edge) — don't hijack those.
  const isPaletteEntry = entrySource === "palette";
  const handleArrowLeftBack = useCallback(
    (e: KeyboardEvent<HTMLInputElement | HTMLTextAreaElement>): boolean => {
      if (e.key !== "ArrowLeft") return false;
      if (!isPaletteEntry) return false;
      if (e.shiftKey || e.metaKey || e.ctrlKey || e.altKey) return false;
      if (e.currentTarget.selectionEnd !== 0) return false;
      e.preventDefault();
      returnToPalette();
      return true;
    },
    [isPaletteEntry, returnToPalette],
  );

  const handleBranchKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>): void => {
      if (handleArrowLeftBack(e)) return;
      if (e.key === "ArrowDown") {
        e.preventDefault();
        nameInputRef.current?.focus();
        return;
      }

      // Plain Enter advances to the title; Cmd+Enter is handled at the
      // modal level (submit) and falls through here unmodified.
      if (e.key === "Enter" && !isModifierPressed(e.nativeEvent)) {
        e.preventDefault();
        nameInputRef.current?.focus();
      }
    },
    [handleArrowLeftBack],
  );

  const handleTitleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLInputElement>): void => {
      if (handleArrowLeftBack(e)) return;
      if (e.key === "ArrowUp") {
        e.preventDefault();
        branchInputRef.current?.focus();
        return;
      }

      if (e.key === "ArrowDown") {
        e.preventDefault();
        promptTextareaRef.current?.focus();
        return;
      }

      // Plain Enter advances to the prompt; Cmd+Enter still submits via
      // the modal-level handler.
      if (e.key === "Enter" && !isModifierPressed(e.nativeEvent)) {
        e.preventDefault();
        promptTextareaRef.current?.focus();
      }
    },
    [handleArrowLeftBack],
  );

  const handlePromptKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>): void => {
      if (handleArrowLeftBack(e)) return;
      const ta = e.currentTarget;
      if (e.key === "ArrowUp") {
        const beforeCaret = ta.value.substring(0, ta.selectionStart ?? 0);
        if (!beforeCaret.includes("\n")) {
          e.preventDefault();
          nameInputRef.current?.focus();
        }
      }
    },
    [handleArrowLeftBack],
  );

  const handleOpenChange = useCallback(
    (next: boolean): void => {
      if (next) {
        setIsOpen(true);
        return;
      }
      // While a creation is in flight, refuse to close so the user
      // doesn't accidentally cancel the request mid-flight.
      if (isPending) return;
      setIsOpen(false);
    },
    [setIsOpen, isPending],
  );

  const handleEscapeKeyDown = useCallback(
    (e: globalThis.KeyboardEvent): void => {
      if (entrySource === "palette") {
        e.preventDefault();
        returnToPalette();
      }
    },
    [entrySource, returnToPalette],
  );

  // Toast lives outside the `isOpen` gate so transient toasts set right
  // before closing the modal (e.g. initial-message-failed → setToast →
  // setIsOpen(false)) aren't unmounted before the user can read them.
  // It must stay at a stable React position across `isOpen` flips —
  // returning a different shape (single element vs. fragment) would
  // remount the Toast and lose any in-flight one. The PaletteDialog /
  // Radix Dialog handle the actual show/hide of the modal body via
  // `open={isOpen}`, so we always render the same fragment.
  const toastNode = (
    <Toast
      open={!!toast}
      onOpenChange={(open) => !open && setToast(null)}
      description={toast?.description}
      duration={5000}
      title={toast?.title}
      type={toast?.type}
    />
  );

  const hasNoBranches = repoInfo?.recentBranches?.length === 0;
  // Suppress the required-error visuals while the auto-fill preview is
  // still loading — `effectiveBranchName` is `""` during that window
  // and we don't want a red flash before the suggested name lands.
  const isBranchNameRequired =
    mode === WorkspaceInitializationStrategy.WORKTREE &&
    effectiveBranchName.trim() === "" &&
    !isBranchNamePreviewLoading;
  // Branch-name validation per git's ref-format rules. Drives both
  // the inline error message in the field and the disabled submit —
  // without this, an invalid name (e.g. trailing `/`) silently makes
  // it to the API and fails workspace creation after the click.
  const branchNameValidationError =
    mode === WorkspaceInitializationStrategy.IN_PLACE ? null : validateBranchName(effectiveBranchName.trim());
  const isSubmitDisabled =
    !selectedProjectId ||
    hasNoBranches ||
    isPending ||
    isLoadingProjects ||
    isBranchNameRequired ||
    branchNameValidationError !== null;
  const submitTooltipContent = !selectedProjectId
    ? "Select a repository first"
    : hasNoBranches
      ? "No branches available in this repository"
      : isBranchNameRequired
        ? "Branch name is required"
        : branchNameValidationError !== null
          ? branchNameValidationError
          : isPending
            ? "Creating workspace..."
            : null;

  const selectedProject = projects.find((p) => p.objectId === selectedProjectId);
  const crumbName = selectedProject?.name ?? null;
  const crumbInitial = crumbName != null && crumbName.length > 0 ? crumbName.charAt(0).toUpperCase() : "·";
  const isPromptEmpty = initialPrompt.trim() === "";

  return (
    <>
      <PaletteDialog
        open={isOpen}
        onOpenChange={handleOpenChange}
        title="New workspace"
        contentClassName={styles.content}
        contentTestId={ElementIds.NEW_WORKSPACE_MODAL}
        onKeyDownCapture={handleKeyDown}
        onEscapeKeyDown={handleEscapeKeyDown}
        onOpenAutoFocus={handleOpenAutoFocus}
      >
        <div className={styles.shell}>
          <Tooltip content="Close">
            <IconButton
              type="button"
              variant="ghost"
              size="1"
              color="gray"
              className={styles.closeButton}
              onClick={(): void => handleOpenChange(false)}
              disabled={isPending}
              aria-label="Close"
            >
              <X size={12} />
            </IconButton>
          </Tooltip>
          <div className={styles.context}>
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
                  <span className={styles.crumbName}>{crumbName ?? "Select repo"}</span>
                </span>
              }
            />
            {isModeSelectorVisible && (
              <Select.Root
                size="1"
                value={mode}
                onValueChange={(value) => handleModeChange(value as WorkspaceInitializationStrategy)}
              >
                <Select.Trigger variant="ghost" data-testid={ElementIds.MODE_SELECTOR} className={styles.toolbarPill}>
                  <Flex align="center" gap="1">
                    <BlocksIcon size={12} />
                    <Text size="1" color="gray">
                      mode
                    </Text>
                    <Text size="1" weight="medium" color="gray" highContrast>
                      {mode === WorkspaceInitializationStrategy.IN_PLACE
                        ? "In-place"
                        : mode === WorkspaceInitializationStrategy.WORKTREE
                          ? "Worktree"
                          : "Clone"}
                    </Text>
                  </Flex>
                </Select.Trigger>
                <Select.Content position="popper" side="bottom" sideOffset={5}>
                  <Select.Item
                    value={WorkspaceInitializationStrategy.WORKTREE}
                    data-testid={ElementIds.MODE_OPTION_WORKTREE}
                  >
                    Worktree
                  </Select.Item>
                  {isCloneEnabled && (
                    <Select.Item
                      value={WorkspaceInitializationStrategy.CLONE}
                      data-testid={ElementIds.MODE_OPTION_CLONE}
                    >
                      Clone
                    </Select.Item>
                  )}
                  {isInPlaceEnabled && (
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
            {repoInfo ? (
              mode === WorkspaceInitializationStrategy.IN_PLACE ? (
                <Tooltip content="In-place workspaces use the current branch in your repository">
                  <span style={{ display: "flex" }}>
                    <BranchSelector
                      fetchRepoInfo={fetchRepoInfo}
                      repoInfo={repoInfo}
                      setUserSelectedBranch={setUserSelectedBranch}
                      sourceBranch={sourceBranch}
                      disabled
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
            ) : selectedProjectId ? (
              <Flex align="center" gap="1" className={styles.pillsLoading}>
                <Spinner size="1" />
                <Text size="1" color="gray">
                  Loading branches…
                </Text>
              </Flex>
            ) : null}
            <BranchNameField
              mode={mode}
              value={effectiveBranchName}
              isManuallyEdited={isManuallyEditedBranch}
              isLoading={isBranchNamePreviewLoading}
              collision={branchNameCollision}
              onUserEdit={(value): void => setBranchNameOverride(value)}
              onReset={(): void => {
                setBranchNameOverride(null);
                shuffleBranchName();
              }}
              disabled={isPending}
              inputRef={branchInputRef}
              onKeyDown={handleBranchKeyDown}
              isError={isBranchNameRequired}
              validationError={branchNameValidationError}
            />
            {isBranchNameRequired ? <span className={styles.branchRequiredLabel}>required</span> : null}
          </div>
          {isLoadingProjects && projects.length === 0 ? (
            <div className={styles.spinnerOverlay}>
              <Spinner size="3" />
            </div>
          ) : (
            <>
              <div className={styles.body} data-testid={ElementIds.TASK_STARTER}>
                <input
                  ref={nameInputRef}
                  type="text"
                  value={workspaceName}
                  onChange={(e): void => setWorkspaceName(e.target.value)}
                  onKeyDown={handleTitleKeyDown}
                  placeholder="Untitled workspace"
                  className={styles.title}
                  data-testid={ElementIds.WORKSPACE_NAME_INPUT}
                />
                <textarea
                  ref={promptTextareaRef}
                  value={initialPrompt}
                  onChange={(e): void => setInitialPrompt(e.target.value)}
                  onKeyDown={handlePromptKeyDown}
                  placeholder="Start with a blank workspace or include a first prompt (optional)…"
                  className={styles.description}
                  data-testid={ElementIds.NEW_WORKSPACE_PROMPT_INPUT}
                  disabled={isPending}
                  rows={2}
                />
                <div
                  className={styles.agentSettings}
                  // Always rendered so the row reserves its vertical
                  // space — `visibility: hidden` keeps the slot
                  // occupied while hiding paint and disabling
                  // interaction, so typing the first character
                  // doesn't suddenly grow the modal by ~40px.
                  data-visible={!isPromptEmpty}
                  aria-hidden={isPromptEmpty}
                >
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
            </>
          )}
          <div className={styles.foot}>
            <div className={styles.footLeft}>
              <Tooltip content="Keep this dialog open after creating, so you can start another right away.">
                <label className={styles.createMore}>
                  <Switch size="1" checked={isCreateMore} onCheckedChange={setIsCreateMore} disabled={isPending} />
                  Keep open
                </label>
              </Tooltip>
            </div>
            <div className={styles.footRight}>
              {!isPending && !isSubmitDisabled ? (
                <span className={styles.shortcutHint}>
                  <KeyboardHint keys={`${getMetaKey()}↵`} label="to create" />
                </span>
              ) : null}
              <Tooltip content={submitTooltipContent ?? "Create workspace"}>
                <Button
                  onClick={(): void => {
                    void handleSubmit();
                  }}
                  disabled={isSubmitDisabled}
                  aria-label="Create Workspace"
                  data-testid={ElementIds.START_TASK_BUTTON}
                  size="2"
                  color="indigo"
                >
                  {isPending ? <Spinner size="1" /> : "Create workspace"}
                </Button>
              </Tooltip>
            </div>
          </div>
        </div>
      </PaletteDialog>
      {toastNode}
    </>
  );
};
