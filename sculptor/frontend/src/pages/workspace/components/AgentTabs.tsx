import { ContextMenu, DropdownMenu, Flex, IconButton } from "@radix-ui/themes";
import { useAtom, useAtomValue, useSetAtom } from "jotai";
import { ChevronDownIcon, PlusIcon } from "lucide-react";
import { posthog } from "posthog-js";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  type AgentTypeName,
  createWorkspaceAgent,
  ElementIds,
  getWorkspaceAgentDiagnostics,
  type LlmModel,
  markWorkspaceAgentUnread,
  renameWorkspaceAgent,
} from "~/api";
import { useKeybindingHandler } from "~/common/keybindings";
import { keybindingsMapAtom } from "~/common/keybindings/atoms.ts";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { isDismissibleOverlayOpen } from "~/common/overlayUtils.ts";
import { shouldHandleKeybinding } from "~/common/ShortcutUtils.ts";
import {
  AGENT_TYPE_LABELS,
  agentTabOrderAtom,
  encodeRegisteredAgentType,
  lastUsedAgentTypeAtom,
  parseStoredAgentType,
  REGISTERED_AGENT_TYPE_PREFIX,
  type StoredAgentType,
} from "~/common/state/atoms/agentTabs.ts";
import { debugViewAtomFamily } from "~/common/state/atoms/alphaScroll.ts";
import { pendingAgentTitlesAtom, tasksArrayAtom, updateTasksAtom } from "~/common/state/atoms/tasks.ts";
import { isPiAgentEnabledAtom } from "~/common/state/atoms/userConfig.ts";
import { useOptimisticTaskDelete } from "~/common/state/hooks/useOptimisticTaskDelete.ts";
import { useTerminalAgentRegistrations } from "~/common/state/hooks/useTerminalAgentRegistrations.ts";
import { useRegisterCommandAction } from "~/components/CommandPalette/commandActions.ts";
import { buildAgentActions } from "~/components/CommandPalette/contextActions/agentActions.ts";
import { agentDeleteTargetAtom, renamingAgentIdAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import { AgentContextMenuContent } from "~/components/CommandPalette/contextActions/menu.tsx";
import type { AgentActionRuntime } from "~/components/CommandPalette/contextActions/types.ts";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { zenModeActiveAtom } from "~/components/panels/atoms.ts";
import { AgentStatusDot, getAgentDotStatus } from "~/components/statusDot";
import { TabBar } from "~/components/tabs/TabBar";
import type { TabDefinition } from "~/components/tabs/types";

import styles from "./AgentTabs.module.scss";

const NO_SESSION_TOOLTIP = "No active session — send a prompt first";

/**
 * Fetches diagnostics on mount (when the sub-menu opens) and disables
 * copy items when there is nothing to copy.
 */
const DiagnosticsSubMenu = ({ workspaceID, agentId }: { workspaceID: string; agentId: string }): ReactElement => {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [transcriptPath, setTranscriptPath] = useState<string | null>(null);
  const [sculptorTranscriptPath, setSculptorTranscriptPath] = useState<string | null>(null);
  const [isLoaded, setIsLoaded] = useState(false);
  const [isDebugView, setIsDebugView] = useAtom(debugViewAtomFamily(agentId));

  useEffect(() => {
    let isCancelled = false;
    void getWorkspaceAgentDiagnostics({
      path: { workspace_id: workspaceID, agent_id: agentId },
    }).then(({ data }) => {
      if (isCancelled) return;
      setSessionId(data.sessionId ?? null);
      setTranscriptPath(data.transcriptFilePath ?? null);
      setSculptorTranscriptPath(data.sculptorTranscriptFilePath ?? null);
      setIsLoaded(true);
    });
    return (): void => {
      isCancelled = true;
    };
  }, [workspaceID, agentId]);

  return (
    <ContextMenu.SubContent>
      <ContextMenu.CheckboxItem
        data-testid={ElementIds.TAB_CONTEXT_MENU_DEBUG_VIEW}
        checked={isDebugView}
        onCheckedChange={(checked) => setIsDebugView(checked === true)}
      >
        Debug View
      </ContextMenu.CheckboxItem>
      <ContextMenu.Separator />
      <ContextMenu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_SESSION_ID}
        disabled={!sessionId}
        title={!isLoaded || !sessionId ? NO_SESSION_TOOLTIP : undefined}
        onSelect={async () => {
          if (sessionId) {
            await navigator.clipboard.writeText(sessionId);
          }
        }}
      >
        Copy claude session id
      </ContextMenu.Item>
      <ContextMenu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_TRANSCRIPT_PATH}
        disabled={!transcriptPath}
        title={!isLoaded || !transcriptPath ? NO_SESSION_TOOLTIP : undefined}
        onSelect={async () => {
          if (transcriptPath) {
            await navigator.clipboard.writeText(transcriptPath);
          }
        }}
      >
        Copy claude transcript file path
      </ContextMenu.Item>
      <ContextMenu.Item
        data-testid={ElementIds.TAB_CONTEXT_MENU_COPY_SCULPTOR_TRANSCRIPT_PATH}
        disabled={!sculptorTranscriptPath}
        title={!isLoaded || !sculptorTranscriptPath ? "No transcript file available" : undefined}
        onSelect={async () => {
          if (sculptorTranscriptPath) {
            await navigator.clipboard.writeText(sculptorTranscriptPath);
          }
        }}
      >
        Copy Sculptor transcript file path
      </ContextMenu.Item>
    </ContextMenu.SubContent>
  );
};

export const AgentTabs = (): ReactElement | null => {
  const isZenModeActive = useAtomValue(zenModeActiveAtom);
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const tasks = useAtomValue(tasksArrayAtom);

  // Atoms (not local state) for `renamingAgentId` and `deleteTarget` so the
  // command palette's agent-actions provider can trigger rename/delete from
  // outside this component.
  const [renamingAgentId, setRenamingAgentId] = useAtom(renamingAgentIdAtom);
  const [deleteTarget, setDeleteTarget] = useAtom(agentDeleteTargetAtom);
  const pendingTitles = useAtomValue(pendingAgentTitlesAtom);
  const setPendingTitles = useSetAtom(pendingAgentTitlesAtom);
  const pendingTitleTimers = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());
  const updateTasks = useSetAtom(updateTasksAtom);
  const [isCreating, setIsCreating] = useState(false);
  const [allOrders, setAllOrders] = useAtom(agentTabOrderAtom);
  const customOrder = allOrders[workspaceID] ?? null;

  const workspaceAgents = useMemo(() => {
    const agents = (tasks ?? []).filter((task) => task.workspaceId === workspaceID);
    return agents.sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime());
  }, [tasks, workspaceID]);

  const openTabIds = useMemo((): Array<string> => {
    if (customOrder === null) {
      return workspaceAgents.map((a) => a.id);
    }
    // Reconcile custom order with actual agents: keep custom order for existing agents,
    // append any new agents at the end, and remove agents that no longer exist.
    const agentIdSet = new Set(workspaceAgents.map((a) => a.id));
    const ordered = customOrder.filter((id) => agentIdSet.has(id));
    const orderedSet = new Set(ordered);
    const newAgents = workspaceAgents.filter((a) => !orderedSet.has(a.id)).map((a) => a.id);
    return [...ordered, ...newAgents];
  }, [customOrder, workspaceAgents]);

  // Clear any in-flight pending-title timers on unmount.
  useEffect(() => {
    const timers = pendingTitleTimers.current;
    return (): void => {
      timers.forEach((timer) => clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const clearPendingTitle = useCallback(
    (taskId: string): void => {
      const timer = pendingTitleTimers.current.get(taskId);
      if (timer !== undefined) {
        clearTimeout(timer);
        pendingTitleTimers.current.delete(taskId);
      }
      setPendingTitles((prev) => {
        if (!(taskId in prev)) return prev;
        const next = { ...prev };
        delete next[taskId];
        return next;
      });
    },
    [setPendingTitles],
  );

  const handleRenameCommit = useCallback(
    async (taskId: string, newName: string): Promise<void> => {
      setRenamingAgentId(null);

      // The mark-read debounce can fire concurrently with a rename, causing the backend to publish
      // a WebSocket with the pre-rename title that overwrites taskAtomFamily. Hold the new title in
      // pendingAgentTitlesAtom for 2 s so the tab label and chat intro stay correct through any
      // such stale WebSocket window.
      setPendingTitles((prev) => ({ ...prev, [taskId]: newName }));
      const existingTimer = pendingTitleTimers.current.get(taskId);
      if (existingTimer !== undefined) clearTimeout(existingTimer);
      pendingTitleTimers.current.set(
        taskId,
        setTimeout(() => clearPendingTitle(taskId), 2000),
      );

      try {
        const response = await renameWorkspaceAgent({
          path: { workspace_id: workspaceID, agent_id: taskId },
          body: { title: newName },
        });
        if (response.data) {
          updateTasks({ [taskId]: response.data });
        }
      } catch (error) {
        console.error("Failed to rename agent:", error);
        clearPendingTitle(taskId);
      }
    },
    [workspaceID, updateTasks, setRenamingAgentId, setPendingTitles, clearPendingTitle],
  );

  const [lastUsedAgentType, setLastUsedAgentType] = useAtom(lastUsedAgentTypeAtom);
  const isPiAgentEnabled = useAtomValue(isPiAgentEnabledAtom);
  const { registrations, refetch: refreshRegistrations } = useTerminalAgentRegistrations();
  // A stored "pi" is unusable once pi-agent is turned off — fall back to Claude.
  const defaultAgentType: StoredAgentType =
    lastUsedAgentType === "pi" && !isPiAgentEnabled ? "claude" : lastUsedAgentType;

  const handleCreateAgent = useCallback(
    async (requestedType?: AgentTypeName, requestedRegistrationId?: string): Promise<void> => {
      if (isCreating) return;
      setIsCreating(true);
      try {
        // Explicit menu choice wins (and becomes the new default); a plain
        // click / keybinding / Cmd+K creates the last-used type. Registered
        // agents are remembered as `registered:<id>`.
        let agentType: AgentTypeName;
        let registrationId: string | undefined;
        if (requestedType !== undefined) {
          agentType = requestedType;
          registrationId = requestedRegistrationId;
          setLastUsedAgentType(
            requestedType === "registered" && requestedRegistrationId !== undefined
              ? encodeRegisteredAgentType(requestedRegistrationId)
              : requestedType,
          );
        } else {
          ({ agentType, registrationId } = parseStoredAgentType(defaultAgentType));
        }
        // Inherit the model from the currently viewed agent so the new agent
        // starts with the same model selection. Terminal agents never read it.
        const currentAgent = agentID ? workspaceAgents.find((a) => a.id === agentID) : undefined;
        const model = currentAgent?.model as LlmModel | undefined;
        let response;
        try {
          response = await createWorkspaceAgent({
            path: { workspace_id: workspaceID },
            body: { model, agentType, registrationId },
          });
        } catch (error) {
          // A remembered registered agent's registration can be deleted out
          // from under the stored default — only that case retries as Claude.
          // Other failures (e.g. a transient error creating a plain terminal
          // or pi agent) propagate rather than silently substituting a
          // different agent type than the user's default.
          if (requestedType === undefined && agentType === "registered") {
            setLastUsedAgentType("claude");
            response = await createWorkspaceAgent({
              path: { workspace_id: workspaceID },
              body: { model, agentType: "claude" },
            });
          } else {
            throw error;
          }
        }

        if (response.data) {
          posthog.capture("agent.added", {
            workspace_id: workspaceID,
            agent_id: response.data.id,
            model: model ?? null,
            agent_type: agentType,
          });
          navigateToAgent(workspaceID, response.data.id);
        }
      } catch (error) {
        console.error("Failed to create agent:", error);
      } finally {
        setIsCreating(false);
      }
    },
    [workspaceID, isCreating, navigateToAgent, agentID, workspaceAgents, defaultAgentType, setLastUsedAgentType],
  );

  useKeybindingHandler("new_agent", () => {
    void handleCreateAgent();
  });

  const handleNavigateAfterDelete = useCallback(
    (taskId: string): void => {
      if (taskId !== agentID) {
        return;
      }
      // Navigate to next available agent, or create a new one if this was the last
      const remainingAgents = workspaceAgents.filter((a) => a.id !== taskId);
      if (remainingAgents.length > 0) {
        const deletedIndex = workspaceAgents.findIndex((a) => a.id === taskId);
        const nextAgent = remainingAgents[Math.min(deletedIndex, remainingAgents.length - 1)];
        navigateToAgent(workspaceID, nextAgent.id);
      } else {
        void handleCreateAgent();
      }
    },
    [agentID, workspaceAgents, workspaceID, navigateToAgent, handleCreateAgent],
  );

  const { execute: executeDelete } = useOptimisticTaskDelete({
    workspaceId: workspaceID,
    onNavigateAfterDelete: handleNavigateAfterDelete,
  });

  const handleDeleteConfirm = useCallback((): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
  }, [deleteTarget, executeDelete, setDeleteTarget]);

  // Build TabDefinition array from agents
  const tabs = useMemo((): Array<TabDefinition> => {
    return workspaceAgents.map((agent) => {
      const dotStatus = getAgentDotStatus(agent.status, agent.lastReadAt, agent.updatedAt);
      const isRenaming = renamingAgentId === agent.id;
      const label = pendingTitles[agent.id] ?? agent.title ?? "Untitled";

      return {
        id: agent.id,
        label,
        icon: <AgentStatusDot status={dotStatus} />,
        dataTestId: ElementIds.AGENT_TAB,
        dataAttributes: { "dot-status": dotStatus, status: agent.status },
        labelContent: isRenaming ? (
          <InlineRenameInput
            value={agent.title ?? ""}
            onCommit={(newName) => void handleRenameCommit(agent.id, newName)}
            onCancel={() => setRenamingAgentId(null)}
            isEditing={true}
          />
        ) : undefined,
      };
    });
  }, [workspaceAgents, renamingAgentId, handleRenameCommit, pendingTitles, setRenamingAgentId]);

  const handleActivate = useCallback(
    (tabId: string): void => {
      navigateToAgent(workspaceID, tabId);
    },
    [workspaceID, navigateToAgent],
  );

  const handleClose = useCallback(
    (tabId: string): void => {
      const agent = workspaceAgents.find((a) => a.id === tabId);
      if (agent) {
        setDeleteTarget({ id: agent.id, name: agent.title ?? "" });
      }
    },
    [workspaceAgents, setDeleteTarget],
  );

  const handleDoubleClick = useCallback(
    (tabId: string): void => {
      setRenamingAgentId(tabId);
    },
    [setRenamingAgentId],
  );

  const handleReorder = useCallback(
    (newOrder: Array<string>): void => {
      setAllOrders((prev) => ({ ...prev, [workspaceID]: newOrder }));
    },
    [workspaceID, setAllOrders],
  );

  // Next/Previous agent: cycle through agents within this workspace
  const keybindingsMap = useAtomValue(keybindingsMapAtom);

  // Imperative cycle action — invoked both by the keybinding listener
  // below and by the Cmd+K commands (via `useRegisterCommandAction`).
  const cycleAgent = useCallback(
    (direction: 1 | -1): void => {
      if (openTabIds.length === 0) return;
      const currentIndex = agentID ? openTabIds.indexOf(agentID) : -1;
      const nextIndex = (currentIndex + direction + openTabIds.length) % openTabIds.length;
      const nextAgentId = openTabIds[nextIndex];
      navigateToAgent(workspaceID, nextAgentId);
    },
    [agentID, openTabIds, workspaceID, navigateToAgent],
  );

  const goToNextAgent = useCallback((): void => cycleAgent(1), [cycleAgent]);
  const goToPreviousAgent = useCallback((): void => cycleAgent(-1), [cycleAgent]);

  useRegisterCommandAction("agent.next", goToNextAgent);
  useRegisterCommandAction("agent.previous", goToPreviousAgent);
  // Cmd+K "New agent" routes here, sharing the `+` button / `new_agent`
  // keybinding handler so all three converge on a single create path.
  useRegisterCommandAction("agent.create", () => void handleCreateAgent());

  useEffect(() => {
    const handleAgentCycle = (e: KeyboardEvent): void => {
      if (isDismissibleOverlayOpen()) return;

      const nextBinding = keybindingsMap.next_agent.binding;
      const prevBinding = keybindingsMap.previous_agent.binding;

      let direction: 1 | -1 | null = null;
      if (nextBinding != null && shouldHandleKeybinding(e, nextBinding)) {
        direction = 1;
      } else if (prevBinding != null && shouldHandleKeybinding(e, prevBinding)) {
        direction = -1;
      }

      if (direction == null) return;

      e.preventDefault();
      cycleAgent(direction);
    };

    window.addEventListener("keydown", handleAgentCycle);
    return (): void => window.removeEventListener("keydown", handleAgentCycle);
  }, [keybindingsMap, cycleAgent]);

  // Agent context-menu items come from the shared registry. The
  // Diagnostics submenu is appended as a "trailing" element because its
  // contents fetch async data on submenu open and don't fit the
  // declarative descriptor shape — it stays inline here, but it is the
  // only exception.
  const agentActionRuntime = useMemo<AgentActionRuntime>(
    () => ({
      beginRename: (agent): void => setRenamingAgentId(agent.id),
      markUnread: (agent): void => {
        updateTasks({ [agent.id]: { ...agent, lastReadAt: null } });
        markWorkspaceAgentUnread({
          path: { workspace_id: workspaceID, agent_id: agent.id },
        }).catch(() => {
          // Fire-and-forget: server value will arrive via WebSocket.
        });
      },
      beginDelete: (agent): void => setDeleteTarget({ id: agent.id, name: agent.title ?? "" }),
    }),
    [setRenamingAgentId, updateTasks, workspaceID, setDeleteTarget],
  );
  const agentActions = useMemo(() => buildAgentActions(agentActionRuntime), [agentActionRuntime]);

  const contextMenuContent = useCallback(
    (tabId: string): ReactNode => {
      const agent = workspaceAgents.find((a) => a.id === tabId);
      if (agent == null) return undefined;
      return (
        <AgentContextMenuContent
          actions={agentActions}
          agent={agent}
          trailing={
            <ContextMenu.Sub>
              <ContextMenu.SubTrigger data-testid={ElementIds.TAB_CONTEXT_MENU_DIAGNOSTICS}>
                Diagnostics
              </ContextMenu.SubTrigger>
              <DiagnosticsSubMenu workspaceID={workspaceID} agentId={tabId} />
            </ContextMenu.Sub>
          }
        />
      );
    },
    [workspaceAgents, workspaceID, agentActions],
  );

  if (isZenModeActive) return null;

  return (
    <>
      <TabBar
        tabs={tabs}
        openTabIds={openTabIds}
        activeTabId={agentID ?? ""}
        onActivate={handleActivate}
        onClose={handleClose}
        onReorder={handleReorder}
        onDoubleClick={handleDoubleClick}
        tabBarClassName={styles.tabBar}
        alwaysCloseable
        contextMenuContent={contextMenuContent}
      >
        {/* gap="0" + neutralized ghost margins (see the SCSS): the two
            segments must sit flush to read as one split button. */}
        <Flex gap="0" align="center" className={styles.addButtonGroup}>
          <IconButton
            variant="ghost"
            size="1"
            color="gray"
            className={styles.addButton}
            onClick={() => void handleCreateAgent()}
            disabled={isCreating}
            aria-label="Add agent"
            title={
              defaultAgentType.startsWith(REGISTERED_AGENT_TYPE_PREFIX)
                ? "New agent"
                : `New ${AGENT_TYPE_LABELS[defaultAgentType as Exclude<AgentTypeName, "registered">]} agent`
            }
            data-testid={ElementIds.ADD_AGENT_BUTTON}
          >
            <PlusIcon size={14} />
          </IconButton>
          <DropdownMenu.Root
            onOpenChange={(open) => {
              // Re-read the registrations directory on every open so the
              // menu tracks the filesystem without a restart.
              if (open) refreshRegistrations();
            }}
          >
            <DropdownMenu.Trigger>
              <IconButton
                variant="ghost"
                size="1"
                color="gray"
                className={styles.addButtonChevron}
                disabled={isCreating}
                aria-label="Choose agent type"
                data-testid={ElementIds.ADD_AGENT_CHEVRON_BUTTON}
              >
                <ChevronDownIcon size={12} />
              </IconButton>
            </DropdownMenu.Trigger>
            {/* CheckboxItems mark the last-used type — the one a plain +
                click creates. Selecting an item still creates an agent (the
                check is an indicator, not a toggle). */}
            <DropdownMenu.Content data-testid={ElementIds.AGENT_TYPE_MENU}>
              <DropdownMenu.CheckboxItem
                checked={defaultAgentType === "claude"}
                data-testid={ElementIds.AGENT_TYPE_MENU_ITEM_CLAUDE}
                onSelect={() => void handleCreateAgent("claude")}
              >
                {AGENT_TYPE_LABELS.claude}
              </DropdownMenu.CheckboxItem>
              {isPiAgentEnabled && (
                <DropdownMenu.CheckboxItem
                  checked={defaultAgentType === "pi"}
                  data-testid={ElementIds.AGENT_TYPE_MENU_ITEM_PI}
                  onSelect={() => void handleCreateAgent("pi")}
                >
                  {AGENT_TYPE_LABELS.pi}
                </DropdownMenu.CheckboxItem>
              )}
              <DropdownMenu.CheckboxItem
                checked={defaultAgentType === "terminal"}
                data-testid={ElementIds.AGENT_TYPE_MENU_ITEM_TERMINAL}
                onSelect={() => void handleCreateAgent("terminal")}
              >
                {AGENT_TYPE_LABELS.terminal}
              </DropdownMenu.CheckboxItem>
              {registrations.map((registration) => (
                <DropdownMenu.CheckboxItem
                  key={registration.registrationId}
                  checked={defaultAgentType === encodeRegisteredAgentType(registration.registrationId)}
                  data-testid={ElementIds.AGENT_TYPE_MENU_ITEM_REGISTERED}
                  data-registration-id={registration.registrationId}
                  onSelect={() => void handleCreateAgent("registered", registration.registrationId)}
                >
                  {registration.displayName}
                </DropdownMenu.CheckboxItem>
              ))}
            </DropdownMenu.Content>
          </DropdownMenu.Root>
        </Flex>
      </TabBar>
      <DeleteConfirmationDialog
        isOpen={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        entityType="agent"
        entityName={deleteTarget?.name ?? ""}
        onConfirm={handleDeleteConfirm}
      />
    </>
  );
};
