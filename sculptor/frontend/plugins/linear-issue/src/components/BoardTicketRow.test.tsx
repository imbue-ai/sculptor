import { Theme } from "@radix-ui/themes";
import type { WorkspaceView } from "@sculptor/plugin-sdk";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { LinearIssue } from "../linear/client.ts";
import type { BoardRow } from "../linear/board.ts";
import { BoardTicketRow } from "./BoardTicketRow.tsx";

// The row reads only `openExternal` from the SDK (for the issue link); stub it so
// the import resolves without the host runtime. Navigation is a prop, not a hook.
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

describe("BoardTicketRow", () => {
  it("shows the muted 'No workspace' slot when nothing is associated", () => {
    render(
      <Wrapper>
        <BoardTicketRow row={row([])} onOpenWorkspace={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByText("No workspace")).toBeTruthy();
  });

  it("labels the open button with the single workspace and navigates to it on click", async () => {
    const onOpen = vi.fn();
    render(
      <Wrapper>
        <BoardTicketRow row={row([workspace("w1", "My workspace")])} onOpenWorkspace={onOpen} />
      </Wrapper>,
    );
    await userEvent.click(screen.getByRole("button", { name: /My workspace/ }));
    expect(onOpen).toHaveBeenCalledWith("w1");
  });

  it("collapses several workspaces into a count", () => {
    render(
      <Wrapper>
        <BoardTicketRow row={row([workspace("w1", "A"), workspace("w2", "B")])} onOpenWorkspace={vi.fn()} />
      </Wrapper>,
    );
    expect(screen.getByText(/2 workspaces/)).toBeTruthy();
  });
});
