import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RevisionHistoryResponse, RevisionInfo } from "~/api";
import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { RevisionList } from "./RevisionList.tsx";

const FORK_POINT = "9876543210fedcba9876543210fedcba98765432";

const makeRevision = (
  overrides: Partial<RevisionInfo> & Pick<RevisionInfo, "changeId" | "commitId">,
): RevisionInfo => ({
  changeIdPrefixLength: 1,
  description: "",
  authorName: "Ada Lovelace",
  timestamp: new Date().toISOString(),
  parentCommitIds: [FORK_POINT],
  files: [{ path: "notes.md", status: "A", oldPath: null, additions: 1, deletions: 0 }],
  bookmarks: [],
  isWorkingCopy: false,
  isEmpty: false,
  hasConflict: false,
  isDivergent: false,
  ...overrides,
});

const WORKING_COPY = makeRevision({
  changeId: "wwwwwwwwwwwwwwwwwwwwwwwwwwwwwwww",
  commitId: "1111111111111111111111111111111111111111",
  isWorkingCopy: true,
});
const DESCRIBED = makeRevision({
  changeId: "dddddddddddddddddddddddddddddddd",
  commitId: "2222222222222222222222222222222222222222",
  description: "Add notes",
});

const renderList = (inputs: {
  history: RevisionHistoryResponse | null | undefined;
  isPending?: boolean;
  target?: string | null;
  expandedChangeIds?: ReadonlySet<string>;
  onToggleRevision?: (changeId: string) => void;
  onSelectFile?: (revision: RevisionInfo, filePath: string) => void;
}): void => {
  renderWithProviders(
    <RevisionList
      history={inputs.history}
      isPending={inputs.isPending ?? false}
      target={inputs.target === undefined ? "main@origin" : inputs.target}
      expandedChangeIds={inputs.expandedChangeIds ?? new Set<string>()}
      onToggleRevision={inputs.onToggleRevision ?? vi.fn()}
      onSelectFile={inputs.onSelectFile ?? vi.fn()}
    />,
    { store: createStore() },
  );
};

afterEach(() => {
  cleanup();
});

describe("RevisionList", () => {
  it("lists the revisions newest first and names the fork point", () => {
    renderList({ history: { revisions: [WORKING_COPY, DESCRIBED], forkPoint: FORK_POINT } });

    const rows = screen.getAllByTestId(ElementIds.REVISION_ENTRY);
    expect(rows.map((row) => row.dataset.changeId)).toEqual([WORKING_COPY.changeId, DESCRIBED.changeId]);
    expect(screen.getByTestId(ElementIds.REVISIONS_FORK_POINT).textContent).toBe("fork point (main@origin · 98765432)");
  });

  it("names only the fork point's commit when the workspace has no target", () => {
    renderList({ history: { revisions: [WORKING_COPY], forkPoint: FORK_POINT }, target: null });

    expect(screen.getByTestId(ElementIds.REVISIONS_FORK_POINT).textContent).toBe("fork point (98765432)");
  });

  it("toggles a revision by its change id and selects a file with its revision", async () => {
    const user = userEvent.setup();
    const onToggleRevision = vi.fn();
    const onSelectFile = vi.fn();
    renderList({
      history: { revisions: [WORKING_COPY, DESCRIBED], forkPoint: FORK_POINT },
      expandedChangeIds: new Set([DESCRIBED.changeId]),
      onToggleRevision,
      onSelectFile,
    });
    const describedRow = screen.getAllByTestId(ElementIds.REVISION_ENTRY)[1];

    await user.click(within(describedRow).getByText("Add notes"));
    expect(onToggleRevision).toHaveBeenCalledWith(DESCRIBED.changeId);

    await user.click(within(describedRow).getByTestId(ElementIds.FILE_BROWSER_TREE_ROW));
    expect(onSelectFile).toHaveBeenCalledWith(DESCRIBED, "notes.md");
  });

  it("says it is loading until the revisions arrive", () => {
    renderList({ history: undefined, isPending: true });

    expect(screen.getByText("Loading revisions…")).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.REVISIONS_FORK_POINT)).toBeNull();
  });

  it("says when there are no revisions to show", () => {
    renderList({ history: null });

    expect(screen.getByText("No revisions available")).toBeTruthy();
  });
});
