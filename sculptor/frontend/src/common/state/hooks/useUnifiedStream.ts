import { useSetAtom, useStore } from "jotai";
import { useCallback } from "react";

import { type PluginCommandResult, type PluginCommandUiAction, postPluginCommandResult } from "~/api";
import { openFileFromUiEventAtom } from "~/pages/workspace/components/diffPanel/atoms.ts";
import { agentWebviewStateAtomFamily } from "~/pages/workspace/panels/browser/atoms.ts";
import { pluginManager } from "~/plugins/pluginManager.tsx";
import { getRendererIdentity } from "~/plugins/rendererIdentity.ts";

import type { StreamingUpdate } from "../../../api";
import { syncTasksToQueryCache } from "../../queryClient.ts";
import { handleBtwUpdateAtom } from "../atoms/btwPopup";
import { dependenciesStatusAtom } from "../atoms/dependenciesStatus";
import { notificationsAtom } from "../atoms/notifications";
import { updateProjectsAtom } from "../atoms/projects";
import { updatePrStatusAtom } from "../atoms/prStatus";
import { sculptorSettingsAtom } from "../atoms/sculptorSettings";
import { getEmptyTaskDetailState, updateTaskDetailAtom, updateTaskUpdatedArtifactsAtom } from "../atoms/taskDetails";
import { isAgentPluginLoadingAllowedAtom, isFrontendPluginsEnabledAtom } from "../atoms/userConfig";
import { updateWorkspaceBranchAtom } from "../atoms/workspaceBranch";
import { updateWorkspacesAtom } from "../atoms/workspaces";
import { appendSetupOutputChunkAtom } from "../atoms/workspaceSetupOutput";
import { updateWorkspaceSetupStatusAtom } from "../atoms/workspaceSetupStatus";
import { updateWorkspaceTargetBranchesAtom } from "../atoms/workspaceTargetBranches";
import { acknowledgeRequests, updateActiveWebsockets } from "../requestTracking";
import { chatMessagesReducer } from "../taskDetailReducers.ts";
import { useTaskQueryMirror } from "./useTaskQueryMirror.ts";
import { useWebsocket } from "./useWebsocket";

const API_BASE_URL = "/api/v1";

/**
 * Run one agent-issued plugin command against this renderer and POST the result
 * so the originating `sculpt plugin` CLI can report a per-renderer outcome.
 *
 * Fire-and-forget: the caller does not await it, so the stream handler stays
 * cheap. Whatever happens — the command throwing, the plugin runtime being
 * disabled, even the POST itself failing — we always *try* to send a reply
 * (with `ok: false` on failure), because the CLI blocks waiting on a reply from
 * every connected renderer; a silent renderer would hang it until timeout.
 *
 * Two flags gate execution. `enableFrontendPlugins` is whether this renderer's
 * plugin runtime bootstrapped at all; `allowAgentPluginLoading` is whether the
 * user lets *agents* drive it. If either is off we reply with an explicit
 * `ok: false` error (naming which one) rather than staying silent — the agent
 * gets a clear signal instead of an opaque timeout.
 */
const respondToPluginCommand = (
  store: ReturnType<typeof useStore>,
  action: PluginCommandUiAction,
  isPluginsEnabled: boolean,
  isAgentLoadingAllowed: boolean,
): void => {
  void (async (): Promise<void> => {
    const reject = (error: string): PluginCommandResult => ({
      correlationId: action.correlationId,
      renderer: getRendererIdentity(),
      op: action.op,
      ok: false,
      error,
      plugins: [],
    });
    // Write ops (load/reload/unload) require the agent-loading switch; read-only
    // inspect/list stay ungated so an agent can always check state, matching the
    // backend (which only gates write ops before broadcasting). The write gate
    // here is defense-in-depth — the backend normally rejects those before they
    // ever reach a renderer.
    const isWriteOp = action.op === "load" || action.op === "reload" || action.op === "unload";
    const result = !isPluginsEnabled
      ? reject("frontend plugins are disabled in this renderer")
      : isWriteOp && !isAgentLoadingAllowed
        ? reject("agent plugin loading is not allowed in this renderer")
        : await pluginManager.handlePluginCommand(store, action);
    try {
      await postPluginCommandResult({
        path: { correlation_id: action.correlationId },
        body: result,
        meta: { skipWsAck: true },
      });
    } catch (e) {
      console.error("[plugins] failed to POST plugin command result", e);
    }
  })();
};

/**
 * This hook:
 * 1. Connects to the unified WebSocket stream
 * 2. Processes task view updates (for sidebar/task list)
 * 3. Processes task detail updates for ALL tasks (even background ones)
 * 4. Processes user updates (projects, settings, repo info)
 * 5. Handles request tracking acknowledgments
 *
 * Task details are accumulated in global atoms so switching between tasks
 * doesn't lose state.
 */
export const useUnifiedStream = (): void => {
  // Whoever owns the stream owns the projection of its task frames into the
  // legacy Jotai atoms (AppShell normally; EmptyFirstRunPage during first
  // run). Mounted first so the mirror subscribes before a frame can arrive.
  useTaskQueryMirror();
  const updateProjects = useSetAtom(updateProjectsAtom);
  const updateWorkspaces = useSetAtom(updateWorkspacesAtom);
  const setNotifications = useSetAtom(notificationsAtom);
  const setSculptorSettings = useSetAtom(sculptorSettingsAtom);
  const updateTaskDetail = useSetAtom(updateTaskDetailAtom);
  const updateTaskUpdatedArtifacts = useSetAtom(updateTaskUpdatedArtifactsAtom);
  const updatePrStatus = useSetAtom(updatePrStatusAtom);
  const updateWorkspaceBranch = useSetAtom(updateWorkspaceBranchAtom);
  const updateWorkspaceTargetBranches = useSetAtom(updateWorkspaceTargetBranchesAtom);
  const updateWorkspaceSetupStatus = useSetAtom(updateWorkspaceSetupStatusAtom);
  const appendSetupOutputChunk = useSetAtom(appendSetupOutputChunkAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  const handleBtwUpdate = useSetAtom(handleBtwUpdateAtom);
  const openFileFromUiEvent = useSetAtom(openFileFromUiEventAtom);
  const store = useStore();

  const onOpen = useCallback(() => {
    updateActiveWebsockets(true);
  }, []);

  const onClose = useCallback(() => {
    updateActiveWebsockets(false);
  }, []);

  const onMessage = useCallback(
    (data: StreamingUpdate): void => {
      // Handle task views (for task list/sidebar).
      // Single-writer: the frame goes into the TanStack Query cache only;
      // useTaskQueryMirror projects it into the legacy Jotai task atoms.
      if (data.taskViewsByTaskId) {
        syncTasksToQueryCache(data.taskViewsByTaskId);
      }

      // Handle task details (for chat pages)
      //    Process ALL tasks, even if not currently viewing them
      // NOTE: This is O(activeTasks) because we only get a task update if something happens
      if (data.taskUpdateByTaskId && Object.keys(data.taskUpdateByTaskId).length > 0) {
        Object.entries(data.taskUpdateByTaskId).forEach(([taskId, taskUpdate]) => {
          updateTaskDetail({
            taskId,
            updater: (currentState) => {
              const state = currentState ?? getEmptyTaskDetailState();

              // Process incremental updates using pure reducers
              const newChatState = chatMessagesReducer(
                {
                  completedChatMessages: state.completedChatMessages,
                  inProgressChatMessage: state.inProgressChatMessage,
                  queuedChatMessages: state.queuedChatMessages,
                  workingUserMessageId: state.workingUserMessageId,
                  pendingUserQuestion: state.pendingUserQuestion,
                  submittedQuestionAnswers: state.submittedQuestionAnswers,
                  isInPlanMode: state.isInPlanMode,
                  pendingBackgroundTaskIds: state.pendingBackgroundTaskIds,
                  workflowTaskStates: state.workflowTaskStates,
                },
                taskUpdate,
              );

              return {
                ...state,
                ...newChatState,
              };
            },
          });

          // Track which artifacts need fetching
          if (taskUpdate.updatedArtifacts && taskUpdate.updatedArtifacts.length > 0) {
            updateTaskUpdatedArtifacts({
              taskId,
              artifactTypes: taskUpdate.updatedArtifacts,
            });
          }
        });
      }

      // Handle user update
      if (data.userUpdate) {
        const userUpdate = data.userUpdate;

        if (userUpdate.notifications && userUpdate.notifications.length > 0) {
          setNotifications(userUpdate.notifications);
        }

        if (userUpdate.projects && userUpdate.projects.length > 0) {
          const activeProjects = userUpdate.projects.filter((p) => !p.isDeleted);
          updateProjects(activeProjects);
        }

        if (userUpdate.workspaces) {
          updateWorkspaces(userUpdate.workspaces);
        }

        if (userUpdate.settings) {
          setSculptorSettings(userUpdate.settings);
        }
      }

      // Handle workspace branch updates
      if (data.workspaceBranchByWorkspaceId && Object.keys(data.workspaceBranchByWorkspaceId).length > 0) {
        Object.entries(data.workspaceBranchByWorkspaceId).forEach(([workspaceId, branchInfo]) => {
          updateWorkspaceBranch({ workspaceId, branchInfo: branchInfo ?? null });
        });
      }

      // Handle workspace target-branches updates
      if (
        data.workspaceTargetBranchesByWorkspaceId &&
        Object.keys(data.workspaceTargetBranchesByWorkspaceId).length > 0
      ) {
        Object.entries(data.workspaceTargetBranchesByWorkspaceId).forEach(([workspaceId, targetBranchesInfo]) => {
          updateWorkspaceTargetBranches({ workspaceId, targetBranchesInfo: targetBranchesInfo ?? null });
        });
      }

      // Handle workspace setup status updates
      if (data.workspaceSetupStatusByWorkspaceId && Object.keys(data.workspaceSetupStatusByWorkspaceId).length > 0) {
        Object.entries(data.workspaceSetupStatusByWorkspaceId).forEach(([workspaceId, setupStatus]) => {
          updateWorkspaceSetupStatus({ workspaceId, status: setupStatus ?? null });
        });
      }

      // Handle workspace setup live output chunks
      if (data.workspaceSetupOutputByWorkspaceId && Object.keys(data.workspaceSetupOutputByWorkspaceId).length > 0) {
        Object.entries(data.workspaceSetupOutputByWorkspaceId).forEach(([workspaceId, chunks]) => {
          chunks.forEach((chunk) => {
            appendSetupOutputChunk({ workspaceId, chunk });
          });
        });
      }

      // Handle dependencies status updates
      if (data.dependenciesStatus) {
        setDependenciesStatus(data.dependenciesStatus);
      }

      // Handle PR status updates
      if (data.prStatusByWorkspaceId && Object.keys(data.prStatusByWorkspaceId).length > 0) {
        Object.entries(data.prStatusByWorkspaceId).forEach(([workspaceId, prStatus]) => {
          updatePrStatus({ workspaceId, prStatus: prStatus ?? null });
        });
      }

      // Handle finished request IDs
      if (data.finishedRequestIds && data.finishedRequestIds.length > 0) {
        acknowledgeRequests(data.finishedRequestIds);
      }

      // Handle /btw side-chat streaming updates
      if (data.btwUpdate) {
        handleBtwUpdate({
          requestId: data.btwUpdate.requestId,
          state: data.btwUpdate.state,
          answer: data.btwUpdate.answer,
          errorMessage: data.btwUpdate.errorMessage ?? null,
        });
      }

      // Handle ui open-file events (sculpt ui open-file)
      if (data.uiOpenFileByWorkspaceId && Object.keys(data.uiOpenFileByWorkspaceId).length > 0) {
        Object.entries(data.uiOpenFileByWorkspaceId).forEach(([workspaceId, action]) => {
          openFileFromUiEvent({
            workspaceId,
            filePath: action.filePath,
            mode: action.mode,
          });
        });
      }

      // Handle agent webview commands (sculpt ui webview-navigate / webview-refresh)
      if (data.uiWebviewCommandByWorkspaceId && Object.keys(data.uiWebviewCommandByWorkspaceId).length > 0) {
        Object.entries(data.uiWebviewCommandByWorkspaceId).forEach(([workspaceId, action]) => {
          store.set(agentWebviewStateAtomFamily(workspaceId), (prev) => ({ ...prev, command: action }));
        });
      }

      // Handle agent plugin commands (sculpt plugin load/reload/unload/inspect/list).
      // Each renderer runs the op against its own plugin system and POSTs a
      // result back so the CLI can report a per-renderer outcome. The work is
      // fired off without awaiting so the stream handler stays cheap.
      if (data.uiPluginCommandByWorkspaceId && Object.keys(data.uiPluginCommandByWorkspaceId).length > 0) {
        const isPluginsEnabled = store.get(isFrontendPluginsEnabledAtom);
        const isAgentLoadingAllowed = store.get(isAgentPluginLoadingAllowedAtom);
        Object.values(data.uiPluginCommandByWorkspaceId).forEach((action) => {
          respondToPluginCommand(store, action, isPluginsEnabled, isAgentLoadingAllowed);
        });
      }
    },
    [
      updateProjects,
      updateWorkspaces,
      setNotifications,
      setSculptorSettings,
      updateTaskDetail,
      updateTaskUpdatedArtifacts,
      updatePrStatus,
      updateWorkspaceBranch,
      updateWorkspaceTargetBranches,
      updateWorkspaceSetupStatus,
      appendSetupOutputChunk,
      setDependenciesStatus,
      handleBtwUpdate,
      openFileFromUiEvent,
      store,
    ],
  );

  useWebsocket<StreamingUpdate>({
    url: `${API_BASE_URL}/stream/ws`,
    onOpen,
    onClose,
    onMessage,
  });
};
