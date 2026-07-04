import { Theme } from "@radix-ui/themes";
import type { WorkspaceView } from "@sculptor/plugin-sdk";
import { usePluginSetting } from "@sculptor/plugin-sdk";
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { BoardGroup } from "../linear/board.ts";
import type { LinearBoardData } from "../linear/useLinearBoard.ts";
import { useLinearBoard } from "../linear/useLinearBoard.ts";
import { LinearBoard } from "./LinearBoard.tsx";

// Mock the SDK seam (api-key setting + navigation) and the data hook, so the
// test exercises the board's view logic — its empty/error/populated branches —
// without TanStack, the host atoms, or a live fetch.
vi.mock("@sculptor/plugin-sdk", () => ({
  usePluginSetting: vi.fn(() => ["", vi.fn()]),
  useNavigateToWorkspace: () => vi.fn(),
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

beforeEach(() => {
  setApiKey("");
  setBoard({});
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
    const group: BoardGroup<WorkspaceView> = {
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
            description: null,
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
    };
    setApiKey("k");
    setBoard({ groups: [group] });
    renderBoard();
    expect(screen.getByText("In Progress")).toBeTruthy();
    expect(screen.getByText("SCU-42")).toBeTruthy();
    expect(screen.getByText("Wire up the thing")).toBeTruthy();
  });
});
