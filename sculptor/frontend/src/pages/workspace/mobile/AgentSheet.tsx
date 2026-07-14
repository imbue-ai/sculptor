import { DropdownMenu } from "@radix-ui/themes";
import { useAtomValue } from "jotai";
import { Check, Pencil, Plus, Trash2 } from "lucide-react";
import type { ReactElement } from "react";
import { useMemo, useState } from "react";

import { type CodingAgentTaskView, ElementIds } from "~/api";
import { formatRelativeTime } from "~/common/formatRelativeTime.ts";
import { useImbueNavigate, useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { tasksArrayAtom } from "~/common/state/atoms/tasks.ts";
import { useOptimisticTaskDelete } from "~/common/state/hooks/useOptimisticTaskDelete.ts";
import { useWorkspace } from "~/common/state/hooks/useWorkspace.ts";
import { useTaskRenameMutation } from "~/common/state/mutations";
import { DeleteConfirmationDialog } from "~/components/DeleteConfirmationDialog.tsx";
import { InlineRenameInput } from "~/components/InlineRenameInput.tsx";
import { AgentStatusDot } from "~/components/statusDot/StatusDot.tsx";
import { type AgentDotStatus, getAgentDotStatus } from "~/components/statusDot/statusUtils.ts";

import styles from "./AgentSheet.module.scss";
import { useCreateAgent } from "./useCreateAgent.ts";
import { useLongPress } from "./useLongPress.ts";

type AgentSheetProps = {
  isOpen: boolean;
  onClose: () => void;
};

/** Secondary line under an agent's name: the live state when notable, else "last active". */
const subLabel = (status: AgentDotStatus, updatedAt: string): string => {
  switch (status) {
    case "running":
      return "Running";
    case "waiting":
      return "Needs your input";
    case "error":
      return "Error";
    case "unread":
    case "read":
      return formatRelativeTime(updatedAt);
  }
};

/** One agent row. Tap selects; long-press (or right-click) opens a menu anchored
 * to the row's start with Rename / Delete. */
const AgentRow = ({
  agent,
  isCurrent,
  workspaceID,
  onSelect,
  onRequestDelete,
}: {
  agent: CodingAgentTaskView;
  isCurrent: boolean;
  workspaceID: string;
  onSelect: () => void;
  onRequestDelete: (agent: CodingAgentTaskView) => void;
}): ReactElement => {
  const dotStatus = getAgentDotStatus(agent.status, agent.lastReadAt, agent.updatedAt);
  // The shared optimistic rename (same mutation the desktop sidebar uses):
  // the new title shows immediately and rolls back if the request fails.
  const renameMutation = useTaskRenameMutation(workspaceID);
  const [isRenaming, setIsRenaming] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const { handlers: longPress, consumeClick } = useLongPress(() => setIsMenuOpen(true));

  const handleRenameCommit = (newName: string): void => {
    setIsRenaming(false);
    renameMutation.mutate({ agentId: agent.id, newTitle: newName });
  };

  const handleClick = (): void => {
    if (consumeClick()) return;
    onSelect();
  };

  const dot = (
    <span className={styles.dot}>
      <AgentStatusDot status={dotStatus} size={8} />
    </span>
  );

  if (isRenaming) {
    return (
      <div className={`${styles.row} ${isCurrent ? styles.current : ""}`}>
        {dot}
        <span className={styles.info}>
          <InlineRenameInput
            value={agent.title ?? ""}
            onCommit={handleRenameCommit}
            onCancel={() => setIsRenaming(false)}
            isEditing={true}
            className={styles.renameInput}
          />
          <span className={styles.sub}>{subLabel(dotStatus, agent.updatedAt)}</span>
        </span>
      </div>
    );
  }

  return (
    <div className={styles.rowWrap}>
      <DropdownMenu.Root open={isMenuOpen} onOpenChange={setIsMenuOpen}>
        <DropdownMenu.Trigger>
          <span className={styles.menuAnchor} aria-hidden="true" />
        </DropdownMenu.Trigger>
        {/* Rename starts from an onSelect, and InlineRenameInput takes focus
            synchronously — suppress the menu's close-time focus restore or it
            steals focus back and the resulting blur cancels the rename
            (InlineRenameInput's documented contract). */}
        <DropdownMenu.Content
          align="start"
          side="bottom"
          variant="soft"
          className="mobileTheme"
          onCloseAutoFocus={(e): void => e.preventDefault()}
        >
          <DropdownMenu.Item onSelect={() => setIsRenaming(true)} data-testid={ElementIds.MOBILE_ROW_RENAME_ACTION}>
            <Pencil size={16} /> Rename
          </DropdownMenu.Item>
          <DropdownMenu.Separator />
          <DropdownMenu.Item
            color="red"
            onSelect={() => onRequestDelete(agent)}
            data-testid={ElementIds.MOBILE_ROW_DELETE_ACTION}
          >
            <Trash2 size={16} /> Delete agent
          </DropdownMenu.Item>
        </DropdownMenu.Content>
      </DropdownMenu.Root>
      <button
        type="button"
        className={`${styles.row} ${isCurrent ? styles.current : ""}`}
        aria-current={isCurrent}
        onClick={handleClick}
        data-testid={ElementIds.MOBILE_AGENT_SHEET_ROW}
        {...longPress}
      >
        {dot}
        <span className={styles.info}>
          <span className={styles.name}>{agent.titleOrSomethingLikeIt?.trim() || "Agent"}</span>
          <span className={styles.sub}>{subLabel(dotStatus, agent.updatedAt)}</span>
        </span>
        {isCurrent ? <Check size={16} className={styles.check} /> : null}
      </button>
    </div>
  );
};

/**
 * AgentSheet — the bottom drawer half of the agent switcher (Variant D). Lists
 * every agent in the workspace with a status dot + last-activity line, the
 * active one checked, and a "New agent" row at the bottom. The shell owns the
 * dimmed backdrop and the open state (mirrors WorkspaceDrawer); selecting a row
 * closes the sheet and navigates. Long-press a row to rename or delete it.
 */
export const AgentSheet = ({ isOpen, onClose }: AgentSheetProps): ReactElement => {
  const { workspaceID, agentID } = useWorkspacePageParams();
  const { navigateToAgent } = useImbueNavigate();
  const workspace = useWorkspace(workspaceID);
  const tasks = useAtomValue(tasksArrayAtom);
  const { createAgent } = useCreateAgent();

  const agents = useMemo(
    () =>
      (tasks ?? [])
        .filter((t) => t.workspaceId === workspaceID && !t.isDeleted)
        .sort((a, b) => new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime()),
    [tasks, workspaceID],
  );

  const workspaceName = workspace?.description?.trim() || "this workspace";

  const [deleteTarget, setDeleteTarget] = useState<{ id: string; name: string } | null>(null);
  const { execute: executeDelete } = useOptimisticTaskDelete({
    workspaceId: workspaceID ?? "",
    onNavigateAfterDelete: (deletedId: string): void => {
      // If the currently-viewed agent was deleted, hop to another one in the
      // workspace (deleting any other just drops it from the list).
      if (deletedId === agentID) {
        const next = agents.find((a) => a.id !== deletedId);
        onClose();
        if (next) {
          navigateToAgent(workspaceID ?? "", next.id);
        }
      }
    },
  });
  const handleRequestDelete = (agent: CodingAgentTaskView): void => {
    setDeleteTarget({ id: agent.id, name: agent.titleOrSomethingLikeIt?.trim() || "Agent" });
  };

  const handleDeleteConfirm = (): void => {
    if (!deleteTarget) return;
    executeDelete(deleteTarget.id, deleteTarget.name);
    setDeleteTarget(null);
  };

  return (
    <aside
      className={`${styles.sheet} ${isOpen ? styles.open : ""}`}
      aria-hidden={!isOpen}
      data-testid={ElementIds.MOBILE_AGENT_SHEET}
    >
      <div className={styles.handle} />
      <div className={styles.title}>Agents in {workspaceName}</div>

      <div className={styles.list}>
        {agents.map((agent) => (
          <AgentRow
            key={agent.id}
            agent={agent}
            isCurrent={agent.id === agentID}
            workspaceID={workspaceID ?? ""}
            onSelect={() => {
              onClose();
              navigateToAgent(workspaceID ?? "", agent.id);
            }}
            onRequestDelete={handleRequestDelete}
          />
        ))}
      </div>

      <div className={styles.separator} />
      <button
        type="button"
        className={styles.newAgent}
        onClick={() => {
          onClose();
          void createAgent();
        }}
        data-testid={ElementIds.MOBILE_AGENT_SHEET_NEW_AGENT}
      >
        <span className={styles.newIcon}>
          <Plus size={18} />
        </span>
        New agent
      </button>

      <DeleteConfirmationDialog
        isOpen={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        entityType="agent"
        entityName={deleteTarget?.name ?? ""}
        onConfirm={handleDeleteConfirm}
      />
    </aside>
  );
};
