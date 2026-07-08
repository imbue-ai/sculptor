import { Button, DropdownMenu, Flex, Text, Tooltip } from "@radix-ui/themes";
import { openExternal, type WorkspaceView } from "@sculptor/plugin-sdk";
import { ChevronDown, FolderGit2 } from "lucide-react";
import type { ReactElement } from "react";

import type { BoardRow } from "../linear/board.ts";
import type { LinearIssue } from "../linear/client.ts";

// Width of the trailing "No workspace" slot, matching the workspace indicators
// so the trailing column stays aligned down the board.
const WORKSPACE_SLOT_MIN_WIDTH_PX = 120;

// Height cap (with scroll) for the assign submenu: it lists every workspace,
// and long-lived installs can have far more than fit on screen.
const ASSIGN_SUBMENU_MAX_HEIGHT_PX = 320;

/**
 * One ticket on the board: its identifier and title (opening the issue in Linear
 * on click), with a trailing indicator of whether a Sculptor workspace is
 * already working it. The indicator is the board's whole point — a glance tells
 * you which assigned tickets have a workspace and which don't.
 *
 * The "no workspace" case is a quiet "No workspace" menu in the same
 * fixed-width slot: it creates a new workspace pre-filled from the ticket, or
 * assigns one of the existing workspaces (`allWorkspaces`) to it. Purely
 * presentational — creation, assignment, and navigation are all callbacks, so
 * the row stays free of SDK hooks.
 */
export const BoardTicketRow = ({
  row,
  allWorkspaces,
  onOpenWorkspace,
  onCreateWorkspace,
  onAssignWorkspace,
}: {
  row: BoardRow<WorkspaceView>;
  /**
   * Every workspace the assign menu can offer (not just this ticket's);
   * `undefined` while the workspace list hasn't loaded yet, which the assign
   * submenu renders as a loading placeholder rather than "No workspaces".
   */
  allWorkspaces: ReadonlyArray<WorkspaceView> | undefined;
  onOpenWorkspace: (workspaceId: string) => void;
  onCreateWorkspace: (issue: LinearIssue) => void;
  onAssignWorkspace: (workspaceId: string, issue: LinearIssue) => void;
}): ReactElement => {
  const { issue, workspaces } = row;
  return (
    <Flex align="center" justify="between" gap="3" px="2" py="2" style={{ borderTop: "1px solid var(--gray-a3)" }}>
      <Flex
        align="baseline"
        gap="2"
        role="button"
        tabIndex={0}
        onClick={() => openExternal(issue.url)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            openExternal(issue.url);
          }
        }}
        title={`${issue.identifier} — open in Linear`}
        style={{ cursor: "pointer", minWidth: 0, flexGrow: 1 }}
      >
        {/* Fixed-width identifier column so every title starts at the same x,
            regardless of 3- vs 4-digit ticket numbers. `min-width` (not a fixed
            width) lets an unusually long identifier still extend rather than
            clip. `inline-block` is what makes the min-width apply to the span. */}
        <Text
          size="1"
          style={{
            fontFamily: "var(--code-font-family)",
            color: "var(--gray-11)",
            flexShrink: 0,
            display: "inline-block",
            // Sized to clear a full team-key + 4-digit number (e.g. "SCU-1634")
            // so the title column stays put; longer identifiers still extend
            // rather than clip.
            minWidth: "4.5rem",
          }}
        >
          {issue.identifier}
        </Text>
        <Text size="2" truncate>
          {issue.title}
        </Text>
      </Flex>
      {workspaces.length === 0 ? (
        <NoWorkspaceMenu
          issue={issue}
          allWorkspaces={allWorkspaces}
          onCreateWorkspace={onCreateWorkspace}
          onAssignWorkspace={onAssignWorkspace}
        />
      ) : (
        <WorkspaceIndicator workspaces={workspaces} onOpenWorkspace={onOpenWorkspace} />
      )}
    </Flex>
  );
};

/**
 * The no-workspace slot: reads as quiet gray text until hovered, but is the
 * menu for getting a workspace onto the ticket — create a new one pre-filled
 * from the issue, or assign an existing one. The fixed min-width matches the
 * workspace indicators so the trailing column stays aligned down the board.
 */
const NoWorkspaceMenu = ({
  issue,
  allWorkspaces,
  onCreateWorkspace,
  onAssignWorkspace,
}: {
  issue: LinearIssue;
  allWorkspaces: ReadonlyArray<WorkspaceView> | undefined;
  onCreateWorkspace: (issue: LinearIssue) => void;
  onAssignWorkspace: (workspaceId: string, issue: LinearIssue) => void;
}): ReactElement => (
  <DropdownMenu.Root>
    <DropdownMenu.Trigger>
      <Button
        size="1"
        variant="ghost"
        color="gray"
        style={{ flexShrink: 0, minWidth: WORKSPACE_SLOT_MIN_WIDTH_PX, justifyContent: "flex-end" }}
      >
        No workspace
        <ChevronDown size={13} />
      </Button>
    </DropdownMenu.Trigger>
    <DropdownMenu.Content>
      <DropdownMenu.Item onSelect={() => onCreateWorkspace(issue)}>Create workspace…</DropdownMenu.Item>
      <DropdownMenu.Sub>
        <DropdownMenu.SubTrigger>Assign workspace</DropdownMenu.SubTrigger>
        <DropdownMenu.SubContent style={{ maxHeight: ASSIGN_SUBMENU_MAX_HEIGHT_PX, overflowY: "auto" }}>
          <AssignSubmenuItems issue={issue} allWorkspaces={allWorkspaces} onAssignWorkspace={onAssignWorkspace} />
        </DropdownMenu.SubContent>
      </DropdownMenu.Sub>
    </DropdownMenu.Content>
  </DropdownMenu.Root>
);

/**
 * The assign submenu's body: a loading placeholder while the workspace list is
 * still `undefined` (the SDK hasn't delivered the first batch), a "No
 * workspaces" placeholder for a loaded-but-empty list, and otherwise one item
 * per workspace.
 */
const AssignSubmenuItems = ({
  issue,
  allWorkspaces,
  onAssignWorkspace,
}: {
  issue: LinearIssue;
  allWorkspaces: ReadonlyArray<WorkspaceView> | undefined;
  onAssignWorkspace: (workspaceId: string, issue: LinearIssue) => void;
}): ReactElement => {
  if (allWorkspaces === undefined) {
    return <DropdownMenu.Item disabled>Loading workspaces…</DropdownMenu.Item>;
  }
  if (allWorkspaces.length === 0) {
    return <DropdownMenu.Item disabled>No workspaces</DropdownMenu.Item>;
  }
  return (
    <>
      {allWorkspaces.map((workspace) => (
        <DropdownMenu.Item key={workspace.id} onSelect={() => onAssignWorkspace(workspace.id, issue)}>
          {workspace.description}
        </DropdownMenu.Item>
      ))}
    </>
  );
};

const WorkspaceIndicator = ({
  workspaces,
  onOpenWorkspace,
}: {
  workspaces: ReadonlyArray<WorkspaceView>;
  onOpenWorkspace: (workspaceId: string) => void;
}): ReactElement => {
  // Exactly one: a direct button into that workspace, labelled with its name.
  if (workspaces.length === 1) {
    const workspace = workspaces[0];
    return (
      <Tooltip content={`Open workspace · ${workspace.description}`}>
        <Button
          size="1"
          variant="soft"
          color="gray"
          onClick={() => onOpenWorkspace(workspace.id)}
          style={{ flexShrink: 0, maxWidth: 220 }}
        >
          <FolderGit2 size={13} />
          <Text truncate>{workspace.description}</Text>
        </Button>
      </Tooltip>
    );
  }

  // Several workspaces working the same ticket: a menu to pick one.
  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger>
        <Button size="1" variant="soft" color="gray" style={{ flexShrink: 0 }}>
          <FolderGit2 size={13} />
          {workspaces.length} workspaces
          <ChevronDown size={13} />
        </Button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Content>
        {workspaces.map((workspace) => (
          <DropdownMenu.Item key={workspace.id} onSelect={() => onOpenWorkspace(workspace.id)}>
            {workspace.description}
          </DropdownMenu.Item>
        ))}
      </DropdownMenu.Content>
    </DropdownMenu.Root>
  );
};
