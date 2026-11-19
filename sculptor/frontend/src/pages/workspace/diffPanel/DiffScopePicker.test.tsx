import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";
import type { WorkspaceVcs } from "~/common/utils/workspaceVcs.ts";

import { DiffScopePicker } from "./DiffScopePicker.tsx";

const renderPicker = (vcs: WorkspaceVcs): void => {
  renderWithProviders(
    <DiffScopePicker scope="uncommitted" onScopeChange={() => {}} vcs={vcs} uncommittedCount={2} allCount={3} />,
    { store: createStore() },
  );
};

afterEach(() => {
  cleanup();
});

describe("DiffScopePicker", () => {
  it("names a git workspace's scopes All and Uncommitted", () => {
    renderPicker("git");

    expect(screen.getByTestId(ElementIds.DIFF_SCOPE_ALL).textContent).toContain("All 3");
    expect(screen.getByTestId(ElementIds.DIFF_SCOPE_UNCOMMITTED).textContent).toContain("Uncommitted 2");
  });

  it("names a jj workspace's scopes All and Working copy", () => {
    renderPicker("jj");

    expect(screen.getByTestId(ElementIds.DIFF_SCOPE_ALL).textContent).toContain("All 3");
    expect(screen.getByTestId(ElementIds.DIFF_SCOPE_UNCOMMITTED).textContent).toContain("Working copy 2");
    expect(screen.getByTestId(ElementIds.DIFF_SCOPE_UNCOMMITTED).textContent).not.toContain("Uncommitted");
  });
});
