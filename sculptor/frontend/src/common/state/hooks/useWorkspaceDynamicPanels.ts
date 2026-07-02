// Keeps the panel registry in sync with the active workspace's agents AND terminals.
// It derives one agent:<taskId> panel per task and one terminal:<wsId>:<index> panel
// per persisted terminal tab in the workspace, then writes the registry (static +
// dynamic). Each terminal carries an onRequestClose that opens the close-confirmation
// dialog via terminalCloseTargetAtom; each agent carries an onRequestClose
// that opens the agent delete-confirmation dialog via agentDeleteTargetAtom
// plus diagnostics for its tab context-menu copy actions. Both confirmation
// dialogs are rendered by the shell (TerminalCloseConfirmation / AgentDeleteConfirmation).

import { useAtomValue, useSetAtom, useStore } from "jotai";
import { useLayoutEffect, useMemo, useRef } from "react";

import { renameWorkspaceAgent } from "~/api";
import { taskAtomFamily, tasksArrayAtom, updateTasksAtom } from "~/common/state/atoms/tasks.ts";
import { terminalTabStateAtom } from "~/common/state/atoms/terminalTabs.ts";
import { markAgentUnreadAtom } from "~/common/state/atoms/unreadOverrides.ts";
import { agentDeleteTargetAtom, terminalCloseTargetAtom } from "~/components/CommandPalette/contextActions/atoms.ts";
import type { DynamicAgentInput, DynamicTerminalInput } from "~/components/sections/registry/dynamicPanels.tsx";
import { deriveDynamicPanels, makeTerminalPanelId } from "~/components/sections/registry/dynamicPanels.tsx";
import {
  buildPluginPanelDefinitions,
  buildStaticPanelDefinitions,
  panelRegistriesEqual,
  panelRegistryAtom,
} from "~/components/sections/registry/panelRegistry.ts";
import { pluginPanelsAtom } from "~/plugins/pluginRegistry.ts";

import type { AgentDiagnosticsByTaskId } from "./useWorkspaceAgentDiagnostics.ts";
import { useWorkspaceAgentDiagnostics } from "./useWorkspaceAgentDiagnostics.ts";

// True when two diagnostics maps carry the same data. Diagnostics feed the tab
// context-menu copy actions — closures that panelRegistriesEqual deliberately ignores —
// so the registry write guard compares them separately: a diagnostics change must force
// a write even when every render-relevant field is unchanged, or the registry would
// keep serving copy actions built from the old diagnostics.
const agentDiagnosticsEqual = (a: AgentDiagnosticsByTaskId, b: AgentDiagnosticsByTaskId): boolean => {
  const aTaskIds = Object.keys(a);
  if (aTaskIds.length !== Object.keys(b).length) {
    return false;
  }
  return aTaskIds.every((taskId) => {
    const left = a[taskId];
    const right = b[taskId];
    return (
      right !== undefined &&
      left.sessionId === right.sessionId &&
      left.claudeTranscriptPath === right.claudeTranscriptPath &&
      left.sculptorTranscriptPath === right.sculptorTranscriptPath
    );
  });
};

export const useWorkspaceDynamicPanels = (workspaceId: string): void => {
  const tasks = useAtomValue(tasksArrayAtom);
  const allTerminalTabs = useAtomValue(terminalTabStateAtom);
  const pluginPanels = useAtomValue(pluginPanelsAtom);
  const setPanelRegistry = useSetAtom(panelRegistryAtom);
  const setTerminalTabs = useSetAtom(terminalTabStateAtom);
  const setTerminalCloseTarget = useSetAtom(terminalCloseTargetAtom);
  const setAgentDeleteTarget = useSetAtom(agentDeleteTargetAtom);
  const updateTasks = useSetAtom(updateTasksAtom);
  const store = useStore();

  // This workspace's tasks, narrowed to the identity/title/status/read fields the
  // registry derives panels from (so the memo below only refires when one changes).
  const workspaceTasks = useMemo(() => {
    return (tasks ?? []).filter((task) => task.workspaceId === workspaceId);
  }, [tasks, workspaceId]);

  // Lazily-fetched per-agent diagnostics (session id + transcript paths) powering the
  // tab context-menu copy actions; refetched as an agent's status changes
  // so a session that appears after a prompt enables the copy items.
  const diagnosticsTargets = useMemo(
    () => workspaceTasks.map((task) => ({ taskId: task.id, status: task.status })),
    [workspaceTasks],
  );
  const diagnosticsByTaskId = useWorkspaceAgentDiagnostics(workspaceId, diagnosticsTargets);

  // Map this workspace's tasks to the agent inputs the registry derives panels from.
  const agents = useMemo<ReadonlyArray<DynamicAgentInput>>(() => {
    return workspaceTasks.map((task) => ({
      taskId: task.id,
      displayName: task.title ?? task.titleOrSomethingLikeIt,
      status: task.status,
      lastReadAt: task.lastReadAt,
      updatedAt: task.updatedAt,
      diagnostics: diagnosticsByTaskId[task.id],
      // Closing an agent tab deletes the agent with confirmation; confirming
      // runs the optimistic delete + rollback + Retry flow. Closing the last
      // agent leaves the center empty — no auto-create.
      onRequestClose: (): void => setAgentDeleteTarget({ id: task.id, name: task.title ?? "" }),
      // Committing an inline tab rename persists the new title. Update the task
      // optimistically so the tab text changes immediately, then PATCH the backend; the
      // canonical value arrives back via WebSocket (mirrors markUnread's fire-and-forget).
      onRename: (newName: string): void => {
        // Read the live task at call time so we only rewrite `title` and don't
        // clobber fields that changed (via WebSocket) since this closure captured
        // `task` — mirrors useMarkRead's read-latest-then-merge.
        const current = store.get(taskAtomFamily(task.id));
        if (current) {
          updateTasks({ [task.id]: { ...current, title: newName } });
        }
        renameWorkspaceAgent({
          path: { workspace_id: workspaceId, agent_id: task.id },
          body: { title: newName },
        }).catch(() => {
          // Fire-and-forget: server value will arrive via WebSocket.
        });
      },
      // "Mark as unread" on the tab context menu: record the unread override, flip
      // lastReadAt optimistically, and persist — all owned by markAgentUnreadAtom.
      onMarkUnread: (): void => store.set(markAgentUnreadAtom, { workspaceId, taskId: task.id }),
    }));
  }, [workspaceTasks, diagnosticsByTaskId, setAgentDeleteTarget, updateTasks, store, workspaceId]);

  // Map this workspace's persisted terminal tabs to terminal inputs. Each tab's label
  // already reflects the lowest-available-number reuse the old panel applied
  // when creating it, so numbering stays in one place. onRequestClose opens the close
  // confirmation rather than tearing the terminal down directly.
  const terminals = useMemo<ReadonlyArray<DynamicTerminalInput>>(() => {
    const workspaceTabs = allTerminalTabs[workspaceId] ?? [];
    return workspaceTabs.map((tab) => ({
      workspaceId,
      index: tab.index,
      displayName: tab.label,
      onRequestClose: (): void =>
        setTerminalCloseTarget({
          panelId: makeTerminalPanelId(workspaceId, tab.index),
          workspaceId,
          index: tab.index,
          tabId: tab.id,
          name: tab.label,
        }),
      // Committing an inline tab rename rewrites this terminal tab's persisted label.
      // Terminal tabs live entirely in client state, so there is no backend
      // round-trip — just update the persisted label by tab id.
      onRename: (newName: string): void =>
        setTerminalTabs((prev) => {
          const workspaceTabs = prev[workspaceId];
          if (workspaceTabs === undefined) {
            return prev;
          }
          return {
            ...prev,
            [workspaceId]: workspaceTabs.map((t) => (t.id === tab.id ? { ...t, label: newName } : t)),
          };
        }),
    }));
  }, [allTerminalTabs, workspaceId, setTerminalCloseTarget, setTerminalTabs]);

  // The diagnostics the previous registry rebuild saw, so the write guard below can
  // tell a callbacks-only change (diagnostics arriving) from a no-op rebuild.
  const previousDiagnosticsRef = useRef<AgentDiagnosticsByTaskId | undefined>(undefined);

  // A layout effect so the registry commits in the same pre-paint flush as the
  // workspace-scope flip and agent placement (useWorkspaceShellBootstrap) — with a
  // passive effect the first committed frame after a workspace switch would still show
  // the previous workspace's dynamic panels.
  useLayoutEffect(() => {
    const staticDefinitions = buildStaticPanelDefinitions();
    const dynamicDefinitions = deriveDynamicPanels(agents, terminals);
    // Merge plugin-contributed panels (PANEL-/plugin spec) into the rebuilt registry so
    // they survive every task-tick rebuild. A plugin panel whose id collides with a
    // static or dynamic panel loses (the host panel wins) so a plugin can't shadow a
    // built-in surface.
    const reservedIds = new Set([...staticDefinitions.map((p) => p.id), ...dynamicDefinitions.map((p) => p.id)]);
    const pluginDefinitions = buildPluginPanelDefinitions(pluginPanels.filter((panel) => !reservedIds.has(panel.id)));
    const next = [...staticDefinitions, ...pluginDefinitions, ...dynamicDefinitions];
    // Skip the write when this rebuild changed nothing: task ticks re-derive the
    // registry several times per second during streaming, and an unguarded write (a
    // brand-new array every time) re-renders every whole-registry subscriber.
    // panelRegistriesEqual ignores the callback fields, so diagnostics — the one
    // callback input not mirrored in a compared field — are checked separately: without
    // that, SectionHeader's open-time action resolution would read a registry whose
    // copy actions still capture the old diagnostics.
    const areDiagnosticsUnchanged =
      previousDiagnosticsRef.current !== undefined &&
      agentDiagnosticsEqual(previousDiagnosticsRef.current, diagnosticsByTaskId);
    previousDiagnosticsRef.current = diagnosticsByTaskId;
    setPanelRegistry((previous) => (areDiagnosticsUnchanged && panelRegistriesEqual(previous, next) ? previous : next));
  }, [agents, terminals, pluginPanels, diagnosticsByTaskId, setPanelRegistry]);
};
