import { Theme } from "@radix-ui/themes";
import type { NewWorkspaceModalOptions, WorkspaceView } from "@sculptor/plugin-sdk";
import { useOpenNewWorkspaceModal, usePluginSetting, useSetPluginSetting, useWorkspaces } from "@sculptor/plugin-sdk";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BoardGroup } from "../linear/board.ts";
import type { LinearBoardData } from "../linear/useLinearBoard.ts";
import { useLinearBoard } from "../linear/useLinearBoard.ts";
import { LinearBoard } from "./LinearBoard.tsx";

// Mock the SDK seam (settings, navigation, workspace list, new-workspace modal)
// and the data hook, so the test exercises the board's view logic — its
// empty/error/populated branches and its row actions — without TanStack, the
// host atoms, or a live fetch.
vi.mock("@sculptor/plugin-sdk", () => ({
  usePluginSetting: vi.fn(() => ["", vi.fn()]),
  useSetPluginSetting: vi.fn(() => vi.fn()),
  useNavigateToWorkspace: () => vi.fn(),
  useOpenNewWorkspaceModal: vi.fn(() => vi.fn()),
  useWorkspaces: vi.fn(() => []),
  openExternal: vi.fn(),
}));
vi.mock("../linear/useLinearBoard.ts", () => ({ useLinearBoard: vi.fn() }));

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const setApiKey = (key: string): void => {
  vi.mocked(usePluginSetting).mockReturnValue([key, vi.fn()]);
};
const setBoard = (overrides: Partial<LinearBoardData>): void => {
  vi.mocked(useLinearBoard).mockReturnValue({
    groups: [],
    isFetching: false,
    isError: false,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  });
};

const renderBoard = (): void => {
  render(
    <Wrapper>
      <LinearBoard />
    </Wrapper>,
  );
};

const workspace = (id: string, description: string): WorkspaceView => ({
  id,
  description,
  branch: null,
  targetBranch: null,
  pullRequestUrl: null,
});

/** One populated group whose single ticket has no associated workspace yet. */
const groupWithUnworkedTicket = (): BoardGroup<WorkspaceView> => ({
  key: "started:In Progress",
  stateName: "In Progress",
  stateType: "started",
  color: "#000",
  rows: [
    {
      issue: {
        identifier: "SCU-42",
        title: "Wire up the thing",
        url: "https://linear.app/x/SCU-42",
        description: "Some details.",
        priorityLabel: null,
        state: null,
        assignee: null,
        attachments: [],
        children: [],
      },
      workspaces: [],
    },
  ],
  hiddenCount: 0,
});

beforeEach(() => {
  vi.clearAllMocks();
  setApiKey("");
  setBoard({});
  vi.mocked(useWorkspaces).mockReturnValue([]);
  vi.mocked(useOpenNewWorkspaceModal).mockReturnValue(vi.fn());
  vi.mocked(useSetPluginSetting).mockReturnValue(vi.fn());
});
afterEach(() => cleanup());

describe("LinearBoard", () => {
  it("prompts for the API key when none is set", () => {
    setApiKey("");
    renderBoard();
    expect(screen.getByText(/Add your Linear API key/)).toBeTruthy();
  });

  it("surfaces the error message with a retry action", () => {
    setApiKey("k");
    setBoard({ isError: true, error: new Error("Linear is down") });
    renderBoard();
    expect(screen.getByText("Linear is down")).toBeTruthy();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeTruthy();
  });

  it("shows the empty state when no issues are assigned", () => {
    setApiKey("k");
    setBoard({ groups: [] });
    renderBoard();
    expect(screen.getByText(/No issues are assigned/)).toBeTruthy();
  });

  it("renders a group header and its ticket rows when populated", () => {
    setApiKey("k");
    setBoard({ groups: [groupWithUnworkedTicket()] });
    renderBoard();
    expect(screen.getByText("In Progress")).toBeTruthy();
    expect(screen.getByText("SCU-42")).toBeTruthy();
    expect(screen.getByText("Wire up the thing")).toBeTruthy();
  });

  it("opens the new-workspace modal pre-filled from the ticket and records the assignment on create", async () => {
    const openModal = vi.fn();
    const setSetting = vi.fn();
    vi.mocked(useOpenNewWorkspaceModal).mockReturnValue(openModal);
    vi.mocked(useSetPluginSetting).mockReturnValue(setSetting);
    setApiKey("k");
    setBoard({ groups: [groupWithUnworkedTicket()] });
    renderBoard();

    await userEvent.click(screen.getByRole("button", { name: /No workspace/ }));
    await userEvent.click(await screen.findByText("Create workspace…"));

    expect(openModal).toHaveBeenCalledTimes(1);
    const options = openModal.mock.calls[0][0] as NewWorkspaceModalOptions;
    expect(options.initialTitle).toBe("SCU-42: Wire up the thing");
    expect(options.initialPrompt).toBe(
      "Work on Linear issue SCU-42: Wire up the thing\nhttps://linear.app/x/SCU-42\n\nSome details.",
    );
    // The modal reports the created workspace's id; the board pins the ticket
    // to it via the same assignment key the workspace panel uses.
    options.onCreated?.("w9");
    expect(setSetting).toHaveBeenCalledWith("assignment:w9", "SCU-42");
  });

  it("writes the assignment when an existing workspace is picked from the submenu", async () => {
    const setSetting = vi.fn();
    vi.mocked(useSetPluginSetting).mockReturnValue(setSetting);
    vi.mocked(useWorkspaces).mockReturnValue([workspace("w1", "My workspace")]);
    setApiKey("k");
    setBoard({ groups: [groupWithUnworkedTicket()] });
    renderBoard();

    await userEvent.click(screen.getByRole("button", { name: /No workspace/ }));
    await userEvent.click(await screen.findByText("Assign workspace"));
    await userEvent.click(await screen.findByText("My workspace"));

    expect(setSetting).toHaveBeenCalledWith("assignment:w1", "SCU-42");
  });
});
