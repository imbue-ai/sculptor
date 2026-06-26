import { ContextMenu, Flex, Text } from "@radix-ui/themes";
import { useAtom, useSetAtom } from "jotai";
import { Pencil, PlusIcon, X, XCircle } from "lucide-react";
import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { closeWorkspaceTerminal, ElementIds } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import {
  activeTerminalTabIdAtom,
  terminalNextIndexAtom,
  terminalTabStateAtom,
} from "~/common/state/atoms/terminalTabs";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { terminalPanelMountedAtom } from "~/components/panels/atoms.ts";
import { PulsingCircle } from "~/components/PulsingCircle.tsx";
import { TabBar } from "~/components/tabs/TabBar";
import type { TabDefinition } from "~/components/tabs/types";

import { getTabStatusIcon } from "./TerminalConnectionIndicator";
import { getNextTerminalLabel } from "./terminalLabelUtils";
import styles from "./TerminalPanel.module.scss";
import type { TerminalConnectionStatus } from "./useTerminal";
import { useTerminal } from "./useTerminal";

// TerminalInstance — one xterm.js + WebSocket per tab

type TerminalTab = {
  id: string;
  index: number;
  label: string;
};

type TerminalInstanceProps = {
  workspaceID: string;
  terminalIndex: number;
  isVisible: boolean;
  onOutput?: () => void;
  onConnectionStatusChange?: (status: TerminalConnectionStatus) => void;
};

const TerminalInstance = ({
  workspaceID,
  terminalIndex,
  isVisible,
  onOutput,
  onConnectionStatusChange,
}: TerminalInstanceProps): ReactElement => {
  const { terminalContainerRef } = useTerminal({
    terminalPath: `/api/v1/workspaces/${workspaceID}/terminal/${terminalIndex}/ws`,
    isVisible,
    onOutput,
    onConnectionStatusChange,
  });

  return (
    <div className={isVisible ? styles.terminalInstanceVisible : styles.terminalInstanceHidden}>
      <div ref={terminalContainerRef} className={styles.xtermWrapper} />
    </div>
  );
};

// useWorkspaceTerminalTabs — workspace-scoped access to persisted tab atoms

const DEFAULT_TAB: TerminalTab = { id: "terminal-0", index: 0, label: "Terminal 1" };
const DEFAULT_NEXT_INDEX = 1;

type WorkspaceTerminalTabsResult = {
  tabs: Array<TerminalTab>;
  activeTabId: string;
  nextIndex: number;
  setTabs: (updater: Array<TerminalTab> | ((prev: Array<TerminalTab>) => Array<TerminalTab>)) => void;
  setActiveTabId: (tabId: string) => void;
  setNextIndex: (updater: number | ((prev: number) => number)) => void;
};

const getWorkspaceTabs = (allTabs: Record<string, Array<TerminalTab>>, workspaceID: string): Array<TerminalTab> =>
  allTabs[workspaceID]?.length ? allTabs[workspaceID] : [DEFAULT_TAB];

const useWorkspaceTerminalTabs = (workspaceID: string): WorkspaceTerminalTabsResult => {
  const [allTabs, setAllTabs] = useAtom(terminalTabStateAtom);
  const [allNextIndex, setAllNextIndex] = useAtom(terminalNextIndexAtom);
  const [allActiveTabId, setAllActiveTabId] = useAtom(activeTerminalTabIdAtom);

  const tabs = getWorkspaceTabs(allTabs, workspaceID);
  const nextIndex = allNextIndex[workspaceID] ?? DEFAULT_NEXT_INDEX;

  // Derive active tab ID, ensuring it refers to an existing tab
  const activeTabId = ((): string => {
    const saved = allActiveTabId[workspaceID];
    if (saved && tabs.some((t) => t.id === saved)) return saved;
    return tabs[0].id;
  })();

  const setTabs = useCallback(
    (updater: Array<TerminalTab> | ((prev: Array<TerminalTab>) => Array<TerminalTab>)): void => {
      setAllTabs((prev) => ({
        ...prev,
        [workspaceID]: typeof updater === "function" ? updater(getWorkspaceTabs(prev, workspaceID)) : updater,
      }));
    },
    [workspaceID, setAllTabs],
  );

  const setActiveTabId = useCallback(
    (tabId: string): void => {
      setAllActiveTabId((prev) => ({ ...prev, [workspaceID]: tabId }));
    },
    [workspaceID, setAllActiveTabId],
  );

  const setNextIndex = useCallback(
    (updater: number | ((prev: number) => number)): void => {
      setAllNextIndex((prev) => ({
        ...prev,
        [workspaceID]: typeof updater === "function" ? updater(prev[workspaceID] ?? DEFAULT_NEXT_INDEX) : updater,
      }));
    },
    [workspaceID, setAllNextIndex],
  );

  return { tabs, activeTabId, nextIndex, setTabs, setActiveTabId, setNextIndex };
};

// TerminalPanelWrapper — manages terminal tabs

export const TerminalPanelWrapper = (): ReactElement | null => {
  const { workspaceID } = useWorkspacePageParams();

  if (!workspaceID) {
    return (
      <Text color="gray" data-testid={ElementIds.TERMINAL_STARTING_TEXT}>
        Starting terminal...
      </Text>
    );
  }

  return <TerminalPanelContent workspaceID={workspaceID} />;
};

const TerminalPanelContent = ({ workspaceID }: { workspaceID: string }): ReactElement => {
  const { tabs, activeTabId, nextIndex, setTabs, setActiveTabId, setNextIndex } = useWorkspaceTerminalTabs(workspaceID);

  // Reactive signal for "is the terminal panel rendered right now?" — the
  // command palette's `hasTerminalPanel` ctx field reads this so commands
  // like "Clear terminal" hide themselves when no terminal exists.
  const setTerminalPanelMounted = useSetAtom(terminalPanelMountedAtom);
  useEffect(() => {
    setTerminalPanelMounted(true);
    return (): void => {
      setTerminalPanelMounted(false);
    };
  }, [setTerminalPanelMounted]);

  const [unreadTabIds, setUnreadTabIds] = useState<Set<string>>(new Set());
  // Mirror activeTabId into a ref so the terminal-output callback stays stable.
  // The ref is read only inside that callback, never during render, so syncing
  // it in an effect keeps render pure without changing behavior.
  const activeTabIdRef = useRef(activeTabId);
  useEffect(() => {
    activeTabIdRef.current = activeTabId;
  });

  const handleTerminalOutput = useCallback((tabId: string) => {
    setUnreadTabIds((prev) => {
      if (tabId === activeTabIdRef.current) return prev;
      if (prev.has(tabId)) return prev;
      const next = new Set(prev);
      next.add(tabId);
      return next;
    });
  }, []);

  // Per-tab WebSocket connection state, so the tab bar can flag a terminal whose
  // connection dropped or won't recover. Keyed by tab id. Only unhealthy states
  // are stored — a connected/connecting terminal needs no indicator — so the map
  // stays bounded and never holds stale entries for recovered or closed tabs.
  const [connectionStatuses, setConnectionStatuses] = useState<Record<string, TerminalConnectionStatus>>({});

  const handleConnectionStatusChange = useCallback((tabId: string, status: TerminalConnectionStatus): void => {
    setConnectionStatuses((prev) => {
      const isHealthy = status === "connected" || status === "connecting";
      if (isHealthy) {
        if (!(tabId in prev)) return prev;
        const next = { ...prev };
        delete next[tabId];
        return next;
      }
      if (prev[tabId] === status) return prev;
      return { ...prev, [tabId]: status };
    });
  }, []);

  const forgetConnectionStatus = useCallback((tabId: string): void => {
    setConnectionStatuses((prev) => {
      if (!(tabId in prev)) return prev;
      const next = { ...prev };
      delete next[tabId];
      return next;
    });
  }, []);

  const handleActivate = useCallback(
    (tabId: string) => {
      setActiveTabId(tabId);
      setUnreadTabIds((prev) => {
        if (!prev.has(tabId)) return prev;
        const next = new Set(prev);
        next.delete(tabId);
        return next;
      });
    },
    [setActiveTabId],
  );

  const handleAddTerminal = useCallback((): void => {
    setNextIndex((prev) => {
      const newTab: TerminalTab = {
        id: `terminal-${prev}`,
        index: prev,
        label: getNextTerminalLabel(tabs),
      };
      setTabs((prevTabs) => [...prevTabs, newTab]);
      setActiveTabId(newTab.id);
      return prev + 1;
    });
  }, [setNextIndex, setTabs, setActiveTabId, tabs]);

  const createFreshTab = useCallback(
    (currentTabs: ReadonlyArray<TerminalTab>): TerminalTab => {
      const newIndex = nextIndex;
      const newTab: TerminalTab = {
        id: `terminal-${newIndex}`,
        index: newIndex,
        label: getNextTerminalLabel(currentTabs),
      };
      setNextIndex(newIndex + 1);
      return newTab;
    },
    [nextIndex, setNextIndex],
  );

  const handleCloseTerminal = useCallback(
    (tabId: string): void => {
      forgetConnectionStatus(tabId);
      setTabs((prev) => {
        const closed = prev.find((t) => t.id === tabId);
        const remaining = prev.filter((t) => t.id !== tabId);

        // Fire-and-forget: ask the backend to stop the pty + shell. A 404
        // (terminal never started, or already closed) is harmless. Errors
        // are surfaced via the toplevel API client's default handler.
        if (closed) {
          void closeWorkspaceTerminal({
            path: { workspace_id: workspaceID, index: closed.index },
            throwOnError: false,
          });
        }

        if (remaining.length === 0) {
          // Last tab closed -- create a fresh replacement
          const newTab = createFreshTab(remaining);
          setActiveTabId(newTab.id);
          return [newTab];
        }

        // If closing the active tab, switch to the nearest neighbor
        if (tabId === activeTabId) {
          const closedIdx = prev.findIndex((t) => t.id === tabId);
          const newActive = remaining[Math.min(closedIdx, remaining.length - 1)];
          setActiveTabId(newActive.id);
        }

        return remaining;
      });
    },
    [activeTabId, createFreshTab, forgetConnectionStatus, setTabs, setActiveTabId, workspaceID],
  );

  const handleCloseOthers = useCallback(
    (tabId: string): void => {
      setTabs((prev) => prev.filter((t) => t.id === tabId));
      setActiveTabId(tabId);
    },
    [setTabs, setActiveTabId],
  );

  const [renamingTabId, setRenamingTabId] = useState<string | null>(null);

  const handleRenameCommit = useCallback(
    (tabId: string, newName: string): void => {
      setRenamingTabId(null);
      setTabs((prev) => prev.map((t) => (t.id === tabId ? { ...t, label: newName } : t)));
    },
    [setTabs],
  );

  const handleDoubleClick = useCallback((tabId: string): void => {
    setRenamingTabId(tabId);
  }, []);

  const handleReorder = useCallback(
    (newOrder: Array<string>): void => {
      setTabs((prev) => {
        const tabMap = new Map(prev.map((t) => [t.id, t]));
        return newOrder.flatMap((id) => {
          const tab = tabMap.get(id);
          return tab ? [tab] : [];
        });
      });
    },
    [setTabs],
  );

  const contextMenuContent = useCallback(
    (tabId: string): ReactNode => {
      return (
        <ContextMenu.Content size="1" onCloseAutoFocus={(e) => e.preventDefault()}>
          <ContextMenu.Item data-testid={ElementIds.TAB_CONTEXT_MENU_RENAME} onSelect={() => setRenamingTabId(tabId)}>
            <Pencil size={14} /> Rename
          </ContextMenu.Item>
          <ContextMenu.Separator />
          <ContextMenu.Item data-testid={ElementIds.TAB_CONTEXT_MENU_CLOSE} onSelect={() => handleCloseTerminal(tabId)}>
            <X size={14} /> Close
          </ContextMenu.Item>
          <ContextMenu.Item
            data-testid={ElementIds.TAB_CONTEXT_MENU_CLOSE_OTHERS}
            onSelect={() => handleCloseOthers(tabId)}
            disabled={tabs.length <= 1}
          >
            <XCircle size={14} /> Close others
          </ContextMenu.Item>
        </ContextMenu.Content>
      );
    },
    [tabs.length, handleCloseTerminal, handleCloseOthers],
  );

  const openTabIds = useMemo(() => tabs.map((t) => t.id), [tabs]);

  const tabDefinitions = useMemo(
    (): Array<TabDefinition> =>
      tabs.map((t) => ({
        id: t.id,
        label: t.label,
        dataTestId: ElementIds.TERMINAL_TAB,
        // A connection issue takes precedence over the unread-output dot: a
        // frozen/dropped terminal is more important to surface than new output.
        icon:
          getTabStatusIcon(connectionStatuses[t.id]) ??
          (unreadTabIds.has(t.id) ? (
            <span className={styles.unreadDot}>
              <PulsingCircle size={7} />
            </span>
          ) : undefined),
        labelContent:
          renamingTabId === t.id ? (
            <InlineRenameInput
              value={t.label}
              onCommit={(newName) => handleRenameCommit(t.id, newName)}
              onCancel={() => setRenamingTabId(null)}
              isEditing={true}
            />
          ) : undefined,
      })),
    [tabs, renamingTabId, unreadTabIds, connectionStatuses, handleRenameCommit],
  );

  return (
    <Flex direction="column" height="100%" overflow="hidden" className={styles.terminalPanel}>
      <TabBar
        tabs={tabDefinitions}
        openTabIds={openTabIds}
        activeTabId={activeTabId}
        onActivate={handleActivate}
        onClose={handleCloseTerminal}
        onReorder={handleReorder}
        onDoubleClick={handleDoubleClick}
        tabBarClassName={styles.terminalTabBar}
        alwaysCloseable
        variant="compact"
        contextMenuContent={contextMenuContent}
      >
        <button
          type="button"
          className={styles.addTerminalButton}
          onClick={handleAddTerminal}
          aria-label="Add terminal"
          data-testid={ElementIds.ADD_TERMINAL_BUTTON}
        >
          <PlusIcon size={14} />
        </button>
      </TabBar>
      <div className={styles.terminalContainer}>
        {tabs.map((tab) => (
          <TerminalInstance
            key={`${workspaceID}-${tab.id}`}
            workspaceID={workspaceID}
            terminalIndex={tab.index}
            isVisible={tab.id === activeTabId}
            onOutput={() => handleTerminalOutput(tab.id)}
            onConnectionStatusChange={(status) => handleConnectionStatusChange(tab.id, status)}
          />
        ))}
      </div>
    </Flex>
  );
};
