import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";

import { CombinedDiffView } from "./CombinedDiffView";

// Build a minimal unified diff string for a single file.
const makeAdditionDiff = (filePath: string): string =>
  [
    `diff --git a/${filePath} b/${filePath}`,
    "new file mode 100644",
    "--- /dev/null",
    `+++ b/${filePath}`,
    "@@ -0,0 +1 @@",
    "+hello",
  ].join("\n");

const makeDeletionDiff = (filePath: string): string =>
  [
    `diff --git a/${filePath} b/${filePath}`,
    "deleted file mode 100644",
    `--- a/${filePath}`,
    "+++ /dev/null",
    "@@ -1 +0,0 @@",
    "-goodbye",
  ].join("\n");

const makeModificationDiff = (filePath: string): string =>
  [
    `diff --git a/${filePath} b/${filePath}`,
    `--- a/${filePath}`,
    `+++ b/${filePath}`,
    "@@ -1 +1 @@",
    "-old line",
    "+new line",
  ].join("\n");

// Mock useWorkspaceDiff to return controlled diff data.
let mockUncommittedDiff: string | null = null;
vi.mock("~/common/state/hooks/useWorkspace.ts", () => ({
  useWorkspace: (): { targetBranch: string } => ({ targetBranch: "origin/main" }),
}));
vi.mock("~/common/state/hooks/useWorkspaceDiff.ts", () => ({
  useWorkspaceDiff: (): { data: { uncommittedDiff: string | null } } => ({
    data: { uncommittedDiff: mockUncommittedDiff },
  }),
}));

// Mock PierreDiffView — it relies on shadow DOM / web components that aren't
// available in jsdom.  The mock mirrors the real component's handle logic:
// render the handle when viewType is "split" and hideHandle is not set.
vi.mock("./PierreDiffView.tsx", () => ({
  PierreDiffView: ({ viewType, hideHandle }: { viewType: string; hideHandle?: boolean }): ReactElement => (
    <div data-testid="pierre-diff-view">
      {viewType === "split" && !hideHandle && <div data-testid={ElementIds.DIFF_SPLIT_COLUMN_HANDLE} />}
    </div>
  ),
}));

// Mock useFileLines — avoids network calls in tests.
vi.mock("./useFileLines.ts", () => ({
  useFileLines: (): { oldLines: undefined; newLines: undefined } => ({
    oldLines: undefined,
    newLines: undefined,
  }),
}));

// Mock FileDropdownMenu — it depends on react-router which isn't available in
// this unit-test context.
vi.mock("~/pages/workspace/panels/fileBrowser/FileDropdownMenu.tsx", () => ({
  FileDropdownMenu: ({ children }: { children: ReactNode }): ReactElement => <>{children}</>,
}));

// Mock CommitButton — it depends on workspace routing context.
vi.mock("~/pages/workspace/panels/fileBrowser/CommitButton.tsx", () => ({
  CommitButton: (): ReactElement => <div data-testid="commit-button" />,
}));

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => {
  const store = createStore();
  return (
    <Provider store={store}>
      <Theme>{children}</Theme>
    </Provider>
  );
};

afterEach(() => {
  cleanup();
  mockUncommittedDiff = null;
});

describe("CombinedDiffView", () => {
  describe("SplitDiffHandle visibility", () => {
    it("does not render the split handle when all files are additions", () => {
      mockUncommittedDiff = makeAdditionDiff("new-file.ts");

      render(<CombinedDiffView workspaceId="ws-1" viewType="split" isActive={true} />, { wrapper: Wrapper });

      expect(screen.queryByTestId(ElementIds.DIFF_SPLIT_COLUMN_HANDLE)).not.toBeInTheDocument();
    });

    it("does not render the split handle when all files are deletions", () => {
      mockUncommittedDiff = makeDeletionDiff("removed-file.ts");

      render(<CombinedDiffView workspaceId="ws-1" viewType="split" isActive={true} />, { wrapper: Wrapper });

      expect(screen.queryByTestId(ElementIds.DIFF_SPLIT_COLUMN_HANDLE)).not.toBeInTheDocument();
    });

    it("does not render the split handle when files are a mix of additions and deletions only", () => {
      mockUncommittedDiff = [makeAdditionDiff("new-file.ts"), makeDeletionDiff("old-file.ts")].join("\n");

      render(<CombinedDiffView workspaceId="ws-1" viewType="split" isActive={true} />, { wrapper: Wrapper });

      expect(screen.queryByTestId(ElementIds.DIFF_SPLIT_COLUMN_HANDLE)).not.toBeInTheDocument();
    });

    it("does not render the split handle even when files include modifications", () => {
      mockUncommittedDiff = [makeAdditionDiff("new-file.ts"), makeModificationDiff("changed-file.ts")].join("\n");

      render(<CombinedDiffView workspaceId="ws-1" viewType="split" isActive={true} />, { wrapper: Wrapper });

      expect(screen.queryByTestId(ElementIds.DIFF_SPLIT_COLUMN_HANDLE)).not.toBeInTheDocument();
    });

    it("does not render the split handle in unified mode even with modifications", () => {
      mockUncommittedDiff = makeModificationDiff("changed-file.ts");

      render(<CombinedDiffView workspaceId="ws-1" viewType="unified" isActive={true} />, { wrapper: Wrapper });

      expect(screen.queryByTestId(ElementIds.DIFF_SPLIT_COLUMN_HANDLE)).not.toBeInTheDocument();
    });
  });
});
