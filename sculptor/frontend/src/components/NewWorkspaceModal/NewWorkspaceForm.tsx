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
  getMostRecentlyUsedProject,
  type LlmModel,
  sendWorkspaceAgentMessages,
  WorkspaceInitializationStrategy,
} from "../../api";
import { HTTPException } from "../../common/Errors.ts";
import { useImbueNavigate } from "../../common/NavigateUtils.ts";
import {
  defaultEffortLevelAtom,
  defaultModelAtom,
  isCloneWorkspacesEnabledAtom,
  isDefaultFastModeAtom,
  isInPlaceWorkspacesEnabledAtom,
} from "../../common/state/atoms/userConfig.ts";
import { useProjects } from "../../common/state/hooks/useProjects.ts";
import { useRepoInfo } from "../../common/state/hooks/useRepoInfo.ts";
import { getMetaKey, isModifierPressed } from "../../electron/utils.ts";
import { AgentSettingsControls } from "../AgentSettingsControls.tsx";
import { BranchSelector } from "../BranchSelector.tsx";
import { KeyboardHint } from "../KeyboardHint.tsx";
import { RepoSelector } from "../RepoSelector.tsx";
import { ToastType } from "../Toast.tsx";
import {
  draftBranchNameOverrideAtom,
  draftInitializationModeAtom,
  draftInitialPromptAtom,
  draftSelectedProjectIdAtom,
  draftUserSelectedBranchAtom,
  draftWorkspaceNameAtom,
  newWorkspaceModalEntrySourceAtom,
  newWorkspaceSubmittingAtom,
  newWorkspaceToastAtom,
  resetDraftAtom,
} from "./atoms.ts";
import { BranchNameField } from "./BranchNameField.tsx";
import { validateBranchName } from "./branchNameValidation.ts";
import { useNewWorkspaceModal } from "./hooks.ts";
import styles from "./NewWorkspaceModal.module.scss";
import { useBranchNamePreview } from "./useBranchNamePreview.ts";

/**
 * The new-workspace form. Mounts only while the modal is open (it is rendered
 * as a child of the dialog content, which Radix mounts on open and unmounts on
 * close). Mounting on open is deliberate:
 *
 *  - The field effects (project default seeding, "auto-select newly added
 *    project", branch-name preview, repo-info refresh) never run while the
 *    modal is closed — so the boot-time WebSocket projects push can't be
 *    misread as "new projects" and clobber the MRU repo default.
 *  - Agent-settings overrides are seeded from the current user defaults via
 *    `useState` initializers on each mount, so they reset per-open without a
 *    reset effect, and a mid-session config push never clobbers an override.
 *
 * Draft field values live in atoms (see ./atoms.ts), so they survive the
 * unmount on close and restore on the next open.
 */
export const NewWorkspaceForm = (): ReactElement => {
  const { close, returnToPalette } = useNewWorkspaceModal();
  const entrySource = useAtomValue(newWorkspaceModalEntrySourceAtom);
  const { navigateToAgent } = useImbueNavigate();

  const isInPlaceEnabled = useAtomValue(isInPlaceWorkspacesEnabledAtom);
  const isCloneEnabled = useAtomValue(isCloneWorkspacesEnabledAtom);
  // Worktree is the always-available default mode; the selector only matters
  // when an alternative (clone or in-place) is opted into.
  const isModeSelectorVisible = isInPlaceEnabled || isCloneEnabled;

  // Per-prompt agent-settings overrides — model / effort / fast mode / plan
  // mode. Seeded from the user's defaults at mount; only surfaced in the UI
  // once the user has typed an initial prompt (no prompt → the defaults apply
  // silently). Because the form remounts on each open, these initializers
  // re-seed from the current defaults every time, so overrides are per-task
  // (not sticky across opens) and Settings changes flow through without a
  // reload — no reset effect required.
  const defaultModelPreference = useAtomValue(defaultModelAtom);
  const defaultEffortLevel = useAtomValue(defaultEffortLevelAtom);
  const isDefaultFastMode = useAtomValue(isDefaultFastModeAtom);
  const [agentModel, setAgentModel] = useState<LlmModel>(defaultModelPreference as LlmModel);
  const [agentEffort, setAgentEffort] = useState<EffortLevel>((defaultEffortLevel as EffortLevel) ?? EffortLevel.XHIGH);
  const [isAgentFastMode, setIsAgentFastMode] = useState<boolean>(isDefaultFastMode);
  const [isAgentPlanMode, setIsAgentPlanMode] = useState<boolean>(false);

  // Projects arrive over the unified WebSocket stream; read them from the
  // shared atom rather than re-fetching.
  const projects = useProjects();
  const resetDraft = useSetAtom(resetDraftAtom);
  const setToast = useSetAtom(newWorkspaceToastAtom);
  const [isSubmitting, setIsSubmitting] = useAtom(newWorkspaceSubmittingAtom);

  const [workspaceName, setWorkspaceName] = useAtom(draftWorkspaceNameAtom);
  const [selectedProjectId, setSelectedProjectId] = useAtom(draftSelectedProjectIdAtom);
  const [userSelectedBranch, setUserSelectedBranch] = useAtom(draftUserSelectedBranchAtom);
  const [mode, setMode] = useAtom(draftInitializationModeAtom);
  const [branchNameOverride, setBranchNameOverride] = useAtom(draftBranchNameOverrideAtom);
  const [initialPrompt, setInitialPrompt] = useAtom(draftInitialPromptAtom);

  // The MRU project id (not WebSocket-pushed, so it's a one-shot HTTP read)
  // and whether that read is still in flight. Used only to seed the default
  // repo on first open; the persisted `draftSelectedProjectIdAtom` takes over
  // afterward.
  const [mruProjectId, setMruProjectId] = useState<string | null>(null);
  const [isResolvingDefault, setIsResolvingDefault] = useState<boolean>(true);

  // "Create more" keeps the modal open after a successful create so the user
  // can fire off several workspaces back-to-back. Off by default. Local state
  // (not an atom) so each new modal session starts fresh.
  const [isCreateMore, setIsCreateMore] = useState(false);
  const nameInputRef = useRef<HTMLInputElement>(null);
  const promptTextareaRef = useRef<HTMLTextAreaElement>(null);
  const branchInputRef = useRef<HTMLInputElement>(null);

  const isManuallyEditedBranch = branchNameOverride !== null;

  // Land focus on the title input when the form mounts (i.e. when the modal
  // opens). The shell's onOpenAutoFocus prevents Radix's default
  // first-focusable autofocus, leaving the field clear for us.
  useEffect(() => {
    nameInputRef.current?.focus();
  }, []);

  // Fetch the MRU project once, to seed the default repo. Genuinely HTTP-only
  // (the MRU isn't streamed), so a request-id-free one-shot with a cancel flag
  // is enough.
  useEffect(() => {
    let isCancelled = false;
    void (async (): Promise<void> => {
      try {
        const mruResponse = await getMostRecentlyUsedProject({ meta: { skipWsAck: true } });
        if (!isCancelled) {
          setMruProjectId(mruResponse.data ?? null);
        }
      } catch (error) {
        console.error("Failed to load most-recently-used project:", error);
      } finally {
        if (!isCancelled) {
          setIsResolvingDefault(false);
        }
      }
    })();

    return (): void => {
      isCancelled = true;
    };
  }, []);

  // Seed the default repo once the MRU read has settled: MRU if it's still a
  // known project, otherwise the first project. Only seeds when the user has
  // no choice yet — the draft atom persists across opens, so a returning user
  // keeps their last repo. Gating on `!isResolvingDefault` lets the MRU win
  // over "just pick the first project".
  useEffect(() => {
    if (isResolvingDefault) return;
    if (selectedProjectId !== null) return;
    if (projects.length === 0) return;
    const seededId =
      mruProjectId !== null && projects.some((p) => p.objectId === mruProjectId) ? mruProjectId : projects[0].objectId;
    setSelectedProjectId(seededId);
  }, [isResolvingDefault, selectedProjectId, projects, mruProjectId, setSelectedProjectId]);

  // Auto-select a newly added project (e.g. one added via the RepoSelector's
  // "Open New Repo" dialog while the modal is open). The ref is seeded from
  // the projects present at open, so the boot-time stream push — which lands
  // while this form is unmounted — never triggers a selection.
  const prevProjectIdsRef = useRef(new Set(projects.map((p) => p.objectId)));
  useEffect(() => {
    const prevProjectIds = prevProjectIdsRef.current;
    const newProjects = projects.filter((p) => !prevProjectIds.has(p.objectId));
    prevProjectIdsRef.current = new Set(projects.map((p) => p.objectId));
    // Skip the *initial* population: if the form mounted before the stream
    // delivered any projects (e.g. the first-load auto-open racing the boot
    // push), `prevProjectIds` is empty and the whole list would look "new" —
    // selecting the last of them would clobber the MRU default that the seed
    // effect above owns. Only a project that appears *after* we already had a
    // list is a genuine user-added repo worth auto-selecting.
    if (prevProjectIds.size > 0 && newProjects.length > 0) {
      setSelectedProjectId(newProjects[newProjects.length - 1].objectId);
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

  // Refresh branch info when the project changes (or on first mount/open) — the
  // source repo's current branch can change underneath us between opens (a user
  // switching branches in their terminal, or a test running `git checkout`), and
  // a stale `repoInfo.currentBranch` would silently feed the wrong source to
  // createWorkspaceV2.
  useEffect(() => {
    if (!selectedProjectId) return;
    fetchCurrentBranch();
    fetchRepoInfo();
  }, [selectedProjectId, fetchCurrentBranch, fetchRepoInfo]);

  // Recovery shortcuts that fire even when focus is on document.body (Radix's
  // focus trap doesn't keep focus pinned — clicking the overlay or tabbing past
  // the last focusable element can leave body active). The per-input arrow
  // handlers below only fire when an input is focused, so without this listener
  // the modal becomes keyboard-dead after a stray blur. Cmd+I mirrors the
  // global `focus_input` keybinding (suppressed while a dismissible overlay is
  // open — see usePageLayoutKeyboardShortcuts).
  useEffect(() => {
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
  }, []);

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
    if (isSubmitting || !selectedProjectId) return;

    const trimmedBranch = effectiveBranchName.trim();

    // Silently bail when worktree mode requires a branch name we don't have
    // yet. The disabled submit button + the red-border / "required" caption
    // already explain why; a toast on top of that is noise.
    if (mode === WorkspaceInitializationStrategy.WORKTREE && trimmedBranch === "") {
      return;
    }

    // Same silent bail when the branch name violates git's ref-format rules —
    // submit is already disabled for click; this guards the Cmd+Enter path so
    // an invalid name never reaches the API.
    if (mode !== WorkspaceInitializationStrategy.IN_PLACE && validateBranchName(trimmedBranch) !== null) {
      return;
    }

    const requestedBranchName =
      mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : trimmedBranch === "" ? undefined : trimmedBranch;

    setIsSubmitting(true);
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

      // If the user typed an initial prompt, send it as the first message to
      // the new agent before navigating. The agent is ready to receive messages
      // on `createWorkspaceAgent` resolve; sending here (rather than queuing in
      // an atom for the agent UI) keeps the path simple and matches
      // `useChatData.sendMessage`. Per-agent settings (effort / fastMode /
      // planMode) ride along on the same request so the initial message starts
      // with the user's chosen settings instead of snapping to defaults.
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
          // Workspace + agent already exist — surface the prompt failure but
          // still navigate so the user can retry from the agent UI without
          // losing the workspace they created.
          console.error("Failed to send initial prompt:", sendError);
          setToast({
            title: "Workspace created, but the initial message failed to send",
            type: ToastType.ERROR,
          });
        }
      }

      resetDraft();
      if (isCreateMore) {
        // "Create more" mode: stay in the modal, refocus the title so the user
        // can immediately start typing the next one, and surface a toast as the
        // only confirmation that the previous create succeeded.
        setToast({
          title: `Workspace "${workspaceName.trim() || "Untitled workspace"}" created`,
          type: ToastType.SUCCESS,
        });
        nameInputRef.current?.focus();
      } else {
        close();
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
      setIsSubmitting(false);
    }
  }, [
    isSubmitting,
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
    setToast,
    setIsSubmitting,
    close,
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

  // ── Arrow-key navigation between the three primary inputs ──────────────
  //
  // Branch ⇅ Title ⇅ Prompt — matches the visual stack. The textarea preserves
  // multi-line cursor movement: ArrowUp only escapes when the caret is on the
  // first line. The single-line inputs hijack the keys unconditionally.
  //
  // When entered from Cmd+K, ArrowLeft with the caret at position 0 (and no
  // selection) returns to the palette — matches the palette's own back
  // affordance, which uses the same `selectionEnd === 0` test. Comparing the
  // caret position (rather than `value === ""`) preserves ordinary mid-input
  // caret movement once the user has typed. Modifier keys mean it's a text-edit
  // gesture (extend selection, jump to line edge) — don't hijack those.
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

      // Plain Enter advances to the title; Cmd+Enter is handled at the form
      // level (submit) and falls through here unmodified.
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

      // Plain Enter advances to the prompt; Cmd+Enter still submits via the
      // form-level handler.
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

  const hasNoBranches = repoInfo?.recentBranches?.length === 0;
  // Worktree mode needs a branch name before it can submit. This drives the
  // submit gate (below) and must NOT be suppressed while the preview loads:
  // `handleSubmit` silently bails on an empty worktree branch, so if the button
  // were enabled during the loading window a click would be swallowed and the
  // workspace never created.
  const isBranchNameMissing = mode === WorkspaceInitializationStrategy.WORKTREE && effectiveBranchName.trim() === "";
  // Visual-only: suppress the required-error border/caption while the auto-fill
  // preview is still loading — `effectiveBranchName` is `""` during that window
  // and we don't want a red flash before the suggested name lands.
  const isBranchNameRequired = isBranchNameMissing && !isBranchNamePreviewLoading;
  // Branch-name validation per git's ref-format rules. Drives both the inline
  // error message in the field and the disabled submit — without this, an
  // invalid name (e.g. trailing `/`) silently makes it to the API and fails
  // workspace creation after the click.
  const branchNameValidationError =
    mode === WorkspaceInitializationStrategy.IN_PLACE ? null : validateBranchName(effectiveBranchName.trim());
  const isSubmitDisabled =
    !selectedProjectId ||
    hasNoBranches ||
    isSubmitting ||
    isBranchNameMissing ||
    // Keep submit disabled until the auto-fill preview settles, so the button
    // never flips enabled while the branch name is still `""` (or stale from a
    // prior workspace name) — clicking in that window would hit `handleSubmit`'s
    // silent empty-branch bail.
    isBranchNamePreviewLoading ||
    branchNameValidationError !== null;
  const submitTooltipContent = !selectedProjectId
    ? "Select a repository first"
    : hasNoBranches
      ? "No branches available in this repository"
      : isBranchNameRequired
        ? "Branch name is required"
        : branchNameValidationError !== null
          ? branchNameValidationError
          : isSubmitting
            ? "Creating workspace..."
            : null;

  const selectedProject = projects.find((p) => p.objectId === selectedProjectId);
  const crumbName = selectedProject?.name ?? null;
  const crumbInitial = crumbName != null && crumbName.length > 0 ? crumbName.charAt(0).toUpperCase() : "·";
  const isPromptEmpty = initialPrompt.trim() === "";

  return (
    <div className={styles.shell} onKeyDownCapture={handleKeyDown}>
      <Tooltip content="Close">
        <IconButton
          type="button"
          variant="ghost"
          size="1"
          color="gray"
          className={styles.closeButton}
          onClick={(): void => close()}
          disabled={isSubmitting}
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
                <Select.Item value={WorkspaceInitializationStrategy.CLONE} data-testid={ElementIds.MODE_OPTION_CLONE}>
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
          disabled={isSubmitting}
          inputRef={branchInputRef}
          onKeyDown={handleBranchKeyDown}
          isError={isBranchNameRequired}
          validationError={branchNameValidationError}
        />
        {isBranchNameRequired ? <span className={styles.branchRequiredLabel}>required</span> : null}
      </div>
      {isResolvingDefault && projects.length === 0 ? (
        <div className={styles.spinnerOverlay}>
          <Spinner size="3" />
        </div>
      ) : (
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
            disabled={isSubmitting}
            rows={2}
          />
          <div
            className={styles.agentSettings}
            // Always rendered so the row reserves its vertical space —
            // `visibility: hidden` keeps the slot occupied while hiding paint
            // and disabling interaction, so typing the first character doesn't
            // suddenly grow the modal by ~40px.
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
      )}
      <div className={styles.foot}>
        <div className={styles.footLeft}>
          <Tooltip content="Keep this dialog open after creating, so you can start another right away.">
            <label className={styles.createMore}>
              <Switch size="1" checked={isCreateMore} onCheckedChange={setIsCreateMore} disabled={isSubmitting} />
              Keep open
            </label>
          </Tooltip>
        </div>
        <div className={styles.footRight}>
          {!isSubmitting && !isSubmitDisabled ? (
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
              {isSubmitting ? <Spinner size="1" /> : "Create workspace"}
            </Button>
          </Tooltip>
        </div>
      </div>
    </div>
  );
};
