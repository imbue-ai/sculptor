import { useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useState } from "react";

import type { EffortLevel, LlmModel, ModelOption, TerminalAgentRegistration } from "~/api";
import { createWorkspaceAgent, createWorkspaceV2, WorkspaceInitializationStrategy } from "~/api";
import { HTTPException } from "~/common/Errors.ts";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import {
  encodeRegisteredAgentType,
  resolveEffectiveAgentType,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { createAgentErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { lastWorkspaceCreationSettingsAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";
import { ToastType } from "~/components/Toast.tsx";

/** Everything the create flow needs from its caller's form state. */
type CreateWorkspaceArgs = {
  projectId: string;
  /** Workspace title; falls back to "Untitled workspace" when blank. */
  workspaceName: string;
  /**
   * First-agent prompt; empty seeds an agent with no prompt. Sent for Claude and
   * pi (both take an initial prompt); terminal/registered agents ignore it and
   * always start in the waiting state.
   */
  prompt: string;
  mode: WorkspaceInitializationStrategy;
  /** Source branch to base the workspace on (ignored for in-place). */
  sourceBranch: string | undefined;
  /** The displayed branch name (override-or-preview); ignored for in-place. */
  branchName: string;
  /** Stored agent type for the first agent (e.g. "claude", "registered:<id>"). */
  agentTypeValue: StoredAgentType;
  /** Live registrations, used to fall back to Claude if one was deleted. */
  registrations: ReadonlyArray<TerminalAgentRegistration>;
  /** Creation-time model for Claude agents. */
  defaultModel: string;
  /**
   * The pi model selection (provider + model_id) for a pi agent created WITH a
   * prompt, sent as `backend_model`. A pi prompt requires it; a promptless pi
   * create omits it. Ignored for Claude/terminal/registered.
   */
  piBackendModel?: ModelOption;
  /** Per-prompt thinking effort for the first Claude agent (defaults apply when omitted). */
  effort?: EffortLevel;
  /** Whether the first Claude agent starts in fast mode. */
  fastMode?: boolean;
  /** Whether the first Claude agent starts in plan mode. */
  enterPlanMode?: boolean;
};

type CreateWorkspaceErrorKind = "branch-collision" | "generic";

export type CreateWorkspaceError = {
  kind: CreateWorkspaceErrorKind;
  branchName: string;
  cause: unknown;
};

type CreateWorkspaceResult = { ok: true; workspaceId: string } | { ok: false; error: CreateWorkspaceError };

type UseCreateWorkspaceReturn = {
  /** True while a create is in flight. */
  isCreating: boolean;
  /**
   * Create the workspace, navigate to it, and record the MRU creation
   * settings; the first agent (with the prompt) is created in the background
   * and focused once it exists. Returns a discriminated result so callers can
   * surface their own toast/error UI without this hook owning it.
   */
  createWorkspace: (args: CreateWorkspaceArgs) => Promise<CreateWorkspaceResult>;
};

/**
 * The two-step create flow: create the workspace, then its first agent (with
 * the prompt). The workspace's environment (worktree/clone) is prepared
 * asynchronously by the backend, so navigation happens as soon as the
 * workspace record exists — the workspace shell renders while setup runs and
 * the agent create is still in flight. Owns only the API calls, navigation,
 * and the MRU write, so every create surface can share it.
 */
export const useCreateWorkspace = (): UseCreateWorkspaceReturn => {
  // State and hooks
  const { navigateToAgent, navigateToWorkspace } = useImbueNavigate();
  const setLastWorkspaceCreationSettings = useSetAtom(lastWorkspaceCreationSettingsAtom);
  const setUserConfig = useSetAtom(userConfigAtom);
  const setCreateAgentErrorToast = useSetAtom(createAgentErrorToastAtom);
  const [isCreating, setIsCreating] = useState<boolean>(false);

  // Functions and callbacks
  const createWorkspace = useCallback(
    async (args: CreateWorkspaceArgs): Promise<CreateWorkspaceResult> => {
      const trimmedBranch = args.branchName.trim();
      const requestedBranchName =
        args.mode === WorkspaceInitializationStrategy.IN_PLACE
          ? undefined
          : args.mode === WorkspaceInitializationStrategy.WORKTREE
            ? trimmedBranch
            : trimmedBranch || undefined;

      setIsCreating(true);
      try {
        const workspaceResponse = await createWorkspaceV2({
          body: {
            projectId: args.projectId,
            initializationStrategy: args.mode,
            sourceBranch: args.mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : args.sourceBranch,
            description: args.workspaceName.trim() || "Untitled workspace",
            requestedBranchName,
          },
        });

        if (!workspaceResponse.data) {
          throw new Error("Failed to create workspace — no response data");
        }

        const workspaceId = workspaceResponse.data.objectId;

        // Resolve the agent type that will actually be created: a registered
        // agent whose registration is gone (deleted since it was picked) falls
        // back to Claude rather than leaving the just-created workspace with a
        // failed, agentless first-agent create.
        const { agentType: effectiveAgentType, registrationId: effectiveRegistrationId } = resolveEffectiveAgentType(
          args.agentTypeValue,
          args.registrations,
        );
        const effectiveAgentTypeValue: StoredAgentType =
          effectiveAgentType === "registered" && effectiveRegistrationId !== undefined
            ? encodeRegisteredAgentType(effectiveRegistrationId)
            : effectiveAgentType;

        setLastWorkspaceCreationSettings({
          projectId: args.projectId,
          sourceBranch: args.mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : args.sourceBranch,
          agentType: effectiveAgentTypeValue,
          initStrategy: args.mode,
        });

        // Land on the new workspace right away: its environment (worktree /
        // clone) is prepared asynchronously by the backend, so there is
        // nothing worth blocking on — the workspace shell renders while setup
        // runs and the first agent is created below.
        navigateToWorkspace(workspaceId);

        // Claude and pi both take an initial prompt; terminal/registered agents
        // do not — the backend rejects a prompt for them (400), which would fail
        // the agent create after the workspace already exists and orphan it.
        const isClaudeAgent = effectiveAgentType === "claude";
        const isPiAgent = effectiveAgentType === "pi";
        const initialPrompt = isClaudeAgent || isPiAgent ? args.prompt.trim() || undefined : undefined;
        // Each harness names its model on its own terms: Claude seeds `model` and
        // consumes the per-prompt settings (effort / fast / plan); pi seeds
        // `backend_model` (the chosen provider + model_id) and ignores the rest.
        // A pi prompt requires the selection; a promptless pi create sends
        // neither field, and the two are mutually exclusive on the backend.
        const backendModel = isPiAgent && initialPrompt !== undefined ? args.piBackendModel : undefined;

        // Create the first agent in the background — the caller's create flow
        // is done once the workspace exists. Failures surface via the global
        // create-agent toast; the user is already on the workspace, where the
        // empty center section offers the recovery path (New agent).
        void (async (): Promise<void> => {
          try {
            const agentResponse = await createWorkspaceAgent({
              path: { workspace_id: workspaceId },
              body: {
                model: isClaudeAgent ? (args.defaultModel as LlmModel) : undefined,
                backendModel,
                effort: isClaudeAgent ? args.effort : undefined,
                fastMode: isClaudeAgent ? args.fastMode : undefined,
                enterPlanMode: isClaudeAgent ? args.enterPlanMode : undefined,
                agentType: effectiveAgentType,
                registrationId: effectiveRegistrationId,
                prompt: initialPrompt,
              },
            });

            if (!agentResponse.data) {
              throw new Error("Failed to create agent — no response data");
            }

            // Optimistically record the chosen harness as the most-recently-used type so the
            // add-panel "New {recent} agent" row reflects it immediately. The backend persists
            // it on create too, but there is no live user-config push — without this the
            // surfaces lag until a reload. Mirrors the add-panel path (addPanelCore.createAgentInLocation).
            setUserConfig((prev) => (prev ? { ...prev, lastUsedAgentType: effectiveAgentTypeValue } : prev));

            posthog.capture("workspace.created", {
              workspace_id: workspaceId,
              agent_id: agentResponse.data.id,
              mode: args.mode,
              agent_type: effectiveAgentType,
              has_workspace_name: args.workspaceName.trim().length > 0,
              has_prompt: args.prompt.trim().length > 0,
              // Branch names are user-entered text (they can encode feature/ticket/
              // customer names), so record only whether one was chosen.
              has_source_branch: args.sourceBranch != null,
            });

            // Focus the new agent only if the user is still parked on this
            // workspace's root — a keep-open multi-create or a manual
            // navigation may have moved them elsewhere, and opening an agent
            // themselves (the empty center's New agent) puts them on an agent
            // sub-route; a late redirect would yank them out of either.
            if (window.location.hash === `#/ws/${workspaceId}`) {
              navigateToAgent(workspaceId, agentResponse.data.id);
            }
          } catch (error) {
            console.error("Failed to create the workspace's first agent:", error);
            setCreateAgentErrorToast({
              title: "Failed to create agent",
              description: "The agent could not be created. Use the workspace's New agent action to retry.",
              type: ToastType.ERROR,
              action: null,
            });
          }
        })();

        return { ok: true, workspaceId };
      } catch (error) {
        console.error("Failed to create workspace:", error);
        const kind: CreateWorkspaceErrorKind =
          error instanceof HTTPException && error.status === 409 ? "branch-collision" : "generic";
        return { ok: false, error: { kind, branchName: trimmedBranch, cause: error } };
      } finally {
        setIsCreating(false);
      }
    },
    [navigateToAgent, navigateToWorkspace, setCreateAgentErrorToast, setLastWorkspaceCreationSettings, setUserConfig],
  );

  return { isCreating, createWorkspace };
};
