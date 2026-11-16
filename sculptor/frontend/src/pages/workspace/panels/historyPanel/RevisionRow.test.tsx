import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RevisionInfo } from "~/api";
import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { RevisionRow } from "./RevisionRow.tsx";

const makeRevision = (overrides: Partial<RevisionInfo> = {}): RevisionInfo => ({
  changeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
  changeIdPrefixLength: 2,
  commitId: "0123456789abcdef0123456789abcdef01234567",
  description: "Add the login form\n\nWith validation.\n",
  authorName: "Ada Lovelace",
  timestamp: new Date().toISOString(),
  parentCommitIds: ["fedcba9876543210fedcba9876543210fedcba98"],
  files: [
    { path: "src/login.py", status: "A", oldPath: null, additions: 10, deletions: 0 },
    { path: "src/app.py", status: "M", oldPath: null, additions: 2, deletions: 1 },
  ],
  bookmarks: [],
  isWorkingCopy: false,
  isEmpty: false,
  hasConflict: false,
  isDivergent: false,
  ...overrides,
});

const renderRow = (inputs: {
  revision: RevisionInfo;
  isExpanded?: boolean;
  onToggle?: () => void;
  onFileClick?: (filePath: string) => void;
}): HTMLElement => {
  renderWithProviders(
    <RevisionRow
      revision={inputs.revision}
      isFirst
      isExpanded={inputs.isExpanded ?? false}
      onToggle={inputs.onToggle ?? vi.fn()}
      onFileClick={inputs.onFileClick ?? vi.fn()}
    />,
    { store: createStore() },
  );
  return screen.getByTestId(ElementIds.REVISION_ENTRY);
};

afterEach(() => {
  cleanup();
});

describe("RevisionRow", () => {
  it("shows the first line of the description", () => {
    const row = renderRow({ revision: makeRevision() });

    expect(within(row).getByText("Add the login form")).toBeTruthy();
    expect(row.textContent).not.toContain("With validation.");
  });

  it("says when a revision has no description", () => {
    const row = renderRow({ revision: makeRevision({ description: "" }) });

    expect(within(row).getByText("(no description set)")).toBeTruthy();
  });

  it("emphasises the unique prefix of the change id", () => {
    const row = renderRow({ revision: makeRevision() });

    expect(row.querySelector("strong")?.textContent).toBe("kx");
    expect(row.textContent).toContain("kxqpmzvy");
  });

  it("shows the stats and the short commit id", () => {
    const row = renderRow({ revision: makeRevision() });

    expect(row.textContent).toContain("+12");
    expect(row.textContent).toContain("-1");
    expect(row.textContent).toContain("2 files");
    expect(row.textContent).toContain("01234567");
    expect(row.textContent).not.toContain("0123456789");
  });

  it("chips the bookmarks and every flag that is set", () => {
    const row = renderRow({
      revision: makeRevision({
        bookmarks: ["dev/login", "dev/login-v2"],
        isWorkingCopy: true,
        isEmpty: true,
        hasConflict: true,
        isDivergent: true,
        files: [],
      }),
    });

    for (const chip of ["dev/login", "dev/login-v2", "working copy", "empty", "conflict", "divergent"]) {
      expect(within(row).getByText(chip)).toBeTruthy();
    }
  });

  it("chips nothing for a plain revision", () => {
    const row = renderRow({ revision: makeRevision() });

    for (const chip of ["working copy", "empty", "conflict", "divergent"]) {
      expect(within(row).queryByText(chip)).toBeNull();
    }
  });

  it("mutes an empty working copy and nothing else", () => {
    const emptyWorkingCopy = renderRow({ revision: makeRevision({ isWorkingCopy: true, isEmpty: true, files: [] }) });
    expect(emptyWorkingCopy.dataset.muted).toBe("true");
    cleanup();

    const editedWorkingCopy = renderRow({ revision: makeRevision({ isWorkingCopy: true }) });
    expect(editedWorkingCopy.dataset.muted).toBe("false");
  });

  it("toggles on click and lists its files when expanded", async () => {
    const user = userEvent.setup();
    const onToggle = vi.fn();
    const onFileClick = vi.fn();
    const row = renderRow({ revision: makeRevision(), isExpanded: true, onToggle, onFileClick });

    await user.click(within(row).getByText("Add the login form"));
    expect(onToggle).toHaveBeenCalledOnce();

    const fileRows = within(row).getAllByTestId(ElementIds.FILE_BROWSER_TREE_ROW);
    const loginRow = fileRows.find((fileRow) => fileRow.textContent?.includes("login.py"));
    expect(loginRow).toBeDefined();
    await user.click(loginRow as HTMLElement);
    expect(onFileClick).toHaveBeenCalledWith("src/login.py");
  });

  it("lists no files while collapsed", () => {
    const row = renderRow({ revision: makeRevision(), isExpanded: false });

    expect(within(row).queryAllByTestId(ElementIds.FILE_BROWSER_TREE_ROW)).toHaveLength(0);
  });
});
