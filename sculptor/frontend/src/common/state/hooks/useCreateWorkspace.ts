import { useSetAtom } from "jotai";
import { posthog } from "posthog-js";
import { useCallback, useState } from "react";

import type { EffortLevel, LlmModel, TerminalAgentRegistration } from "~/api";
import { createWorkspaceAgent, createWorkspaceV2, WorkspaceInitializationStrategy } from "~/api";
import { HTTPException } from "~/common/Errors.ts";
import { useImbueNavigate } from "~/common/NavigateUtils.ts";
import {
  encodeRegisteredAgentType,
  resolveEffectiveAgentType,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { userConfigAtom } from "~/common/state/atoms/userConfig.ts";
import { lastWorkspaceCreationSettingsAtom } from "~/components/newWorkspace/newWorkspaceAtoms.ts";

/** Everything the create flow needs from its caller's form state. */
type CreateWorkspaceArgs = {
  projectId: string;
  /** Workspace title; falls back to "Untitled workspace" when blank. */
  workspaceName: string;
  /**
   * First-agent prompt; empty seeds an agent with no prompt. Only sent for
   * Claude agents — other agent types always start in the waiting state.
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

type CreateWorkspaceResult = { ok: true } | { ok: false; error: CreateWorkspaceError };

type UseCreateWorkspaceReturn = {
  /** True while a create is in flight. */
  isCreating: boolean;
  /**
   * Create the workspace + first agent (with the prompt), navigate to the new
   * agent, and record the MRU creation settings. Returns a discriminated result
   * so callers can surface their own toast/error UI without this hook owning it.
   */
  createWorkspace: (args: CreateWorkspaceArgs) => Promise<CreateWorkspaceResult>;
};

/**
 * The two-step create flow: create the workspace, then its first agent (with
 * the prompt). Owns only the API calls, navigation, and the MRU write, so the
 * new-workspace modal and the empty first-run page can share it.
 */
export const useCreateWorkspace = (): UseCreateWorkspaceReturn => {
  // State and hooks
  const { navigateToAgent } = useImbueNavigate();
  const setLastWorkspaceCreationSettings = useSetAtom(lastWorkspaceCreationSettingsAtom);
  const setUserConfig = useSetAtom(userConfigAtom);
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

        // Only Claude consumes a creation-time prompt, model, and the per-prompt
        // agent settings (effort / fast / plan): terminal/registered agents have
        // no model concept, and pi selects from its own catalog in-task, so it
        // starts on pi's defaults rather than Claude settings it would ignore.
        // The prompt gate mirrors the backend, which rejects a prompt for
        // terminal/registered agents and requires a model alongside any prompt —
        // sending one would fail the agent create after the workspace already
        // exists, orphaning an agentless workspace. Non-Claude agents start in
        // the waiting state instead.
        const isClaudeAgent = effectiveAgentType === "claude";
        const agentResponse = await createWorkspaceAgent({
          path: { workspace_id: workspaceId },
          body: {
            model: isClaudeAgent ? (args.defaultModel as LlmModel) : undefined,
            effort: isClaudeAgent ? args.effort : undefined,
            fastMode: isClaudeAgent ? args.fastMode : undefined,
            enterPlanMode: isClaudeAgent ? args.enterPlanMode : undefined,
            agentType: effectiveAgentType,
            registrationId: effectiveRegistrationId,
            prompt: isClaudeAgent ? args.prompt.trim() || undefined : undefined,
          },
        });

        if (!agentResponse.data) {
          throw new Error("Failed to create agent — no response data");
        }

        setLastWorkspaceCreationSettings({
          projectId: args.projectId,
          sourceBranch: args.mode === WorkspaceInitializationStrategy.IN_PLACE ? undefined : args.sourceBranch,
          agentType: effectiveAgentTypeValue,
          initStrategy: args.mode,
        });

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

        navigateToAgent(workspaceId, agentResponse.data.id);
        return { ok: true };
      } catch (error) {
        console.error("Failed to create workspace:", error);
        const kind: CreateWorkspaceErrorKind =
          error instanceof HTTPException && error.status === 409 ? "branch-collision" : "generic";
        return { ok: false, error: { kind, branchName: trimmedBranch, cause: error } };
      } finally {
        setIsCreating(false);
      }
    },
    [navigateToAgent, setLastWorkspaceCreationSettings, setUserConfig],
  );

  return { isCreating, createWorkspace };
};
