import { Button, DropdownMenu, Flex, Text, Tooltip } from "@radix-ui/themes";
import { openExternal, type WorkspaceView } from "@sculptor/plugin-sdk";
import { ChevronDown, FolderGit2 } from "lucide-react";
import type { ReactElement } from "react";

import type { BoardRow } from "../linear/board.ts";

/**
 * One ticket on the board: its identifier and title (opening the issue in Linear
 * on click), with a trailing indicator of whether a Sculptor workspace is
 * already working it. The indicator is the board's whole point — a glance tells
 * you which assigned tickets have a workspace and which don't.
 *
 * The "no workspace" case is a deliberate, fixed-width muted slot rather than
 * empty space: it's where the "start a workspace for this ticket" control will
 * live, so its presence keeps the column aligned today and reserves the spot.
 */
export const BoardTicketRow = ({
  row,
  onOpenWorkspace,
}: {
  row: BoardRow<WorkspaceView>;
  onOpenWorkspace: (workspaceId: string) => void;
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
      <WorkspaceIndicator workspaces={workspaces} onOpenWorkspace={onOpenWorkspace} />
    </Flex>
  );
};

const WorkspaceIndicator = ({
  workspaces,
  onOpenWorkspace,
}: {
  workspaces: ReadonlyArray<WorkspaceView>;
  onOpenWorkspace: (workspaceId: string) => void;
}): ReactElement => {
  // No workspace yet: a muted, fixed-min-width slot (see component docstring).
  if (workspaces.length === 0) {
    return (
      <Text size="1" color="gray" style={{ flexShrink: 0, minWidth: 120, textAlign: "right" }}>
        No workspace
      </Text>
    );
  }

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
