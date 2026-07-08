import { Theme } from "@radix-ui/themes";
import type { WorkspaceView } from "@sculptor/plugin-sdk";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ComponentProps, ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LinearIssue } from "../linear/client.ts";
import type { BoardRow } from "../linear/board.ts";
import { BoardTicketRow } from "./BoardTicketRow.tsx";

// The row reads only `openExternal` from the SDK (for the issue link); stub it so
// the import resolves without the host runtime. All actions are props, not hooks.
vi.mock("@sculptor/plugin-sdk", () => ({ openExternal: vi.fn() }));

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

afterEach(() => cleanup());

const workspace = (id: string, description: string): WorkspaceView => ({
  id,
  description,
  branch: null,
  targetBranch: null,
  pullRequestUrl: null,
});

const issue: LinearIssue = {
  identifier: "SCU-1",
  title: "Do the thing",
  url: "https://linear.app/x/SCU-1",
  description: null,
  priorityLabel: null,
  state: null,
  assignee: null,
  attachments: [],
  children: [],
};

const row = (workspaces: ReadonlyArray<WorkspaceView>): BoardRow<WorkspaceView> => ({ issue, workspaces });

const renderRow = (overrides: Partial<ComponentProps<typeof BoardTicketRow>> = {}): void => {
  render(
    <Wrapper>
      <BoardTicketRow
        row={row([])}
        allWorkspaces={[]}
        onOpenWorkspace={vi.fn()}
        onCreateWorkspace={vi.fn()}
        onAssignWorkspace={vi.fn()}
        {...overrides}
      />
    </Wrapper>,
  );
};

describe("BoardTicketRow", () => {
  it("shows the quiet 'No workspace' menu trigger when nothing is associated", () => {
    renderRow();
    expect(screen.getByRole("button", { name: /No workspace/ })).toBeTruthy();
  });

  it("invokes the create callback with the row's issue from 'Create workspace…'", async () => {
    const onCreate = vi.fn();
    renderRow({ onCreateWorkspace: onCreate });
    await userEvent.click(screen.getByRole("button", { name: /No workspace/ }));
    await userEvent.click(await screen.findByText("Create workspace…"));
    expect(onCreate).toHaveBeenCalledWith(issue);
  });

  it("assigns an existing workspace picked from the submenu", async () => {
    const onAssign = vi.fn();
    renderRow({ allWorkspaces: [workspace("w1", "My workspace")], onAssignWorkspace: onAssign });
    await userEvent.click(screen.getByRole("button", { name: /No workspace/ }));
    await userEvent.click(await screen.findByText("Assign workspace"));
    await userEvent.click(await screen.findByText("My workspace"));
    expect(onAssign).toHaveBeenCalledWith("w1", issue);
  });

  it("shows a disabled placeholder in the assign submenu when there are no workspaces", async () => {
    renderRow({ allWorkspaces: [] });
    await userEvent.click(screen.getByRole("button", { name: /No workspace/ }));
    await userEvent.click(await screen.findByText("Assign workspace"));
    const placeholder = await screen.findByText("No workspaces");
    expect(placeholder.closest("[role='menuitem']")?.getAttribute("aria-disabled")).toBe("true");
  });

  it("labels the open button with the single workspace and navigates to it on click", async () => {
    const onOpen = vi.fn();
    renderRow({ row: row([workspace("w1", "My workspace")]), onOpenWorkspace: onOpen });
    await userEvent.click(screen.getByRole("button", { name: /My workspace/ }));
    expect(onOpen).toHaveBeenCalledWith("w1");
  });

  it("collapses several workspaces into a count", () => {
    renderRow({ row: row([workspace("w1", "A"), workspace("w2", "B")]) });
    expect(screen.getByText(/2 workspaces/)).toBeTruthy();
  });
});
