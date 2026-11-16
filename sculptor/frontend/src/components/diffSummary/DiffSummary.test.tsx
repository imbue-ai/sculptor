import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DiffArtifact } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { DiffSummary } from "./DiffSummary.tsx";

const { workspaceDiffMock } = vi.hoisted(() => ({ workspaceDiffMock: vi.fn() }));
vi.mock("~/common/state/hooks/useWorkspaceDiff", () => ({ useWorkspaceDiff: workspaceDiffMock }));

const fileDiff = (path: string): string =>
  [`diff --git a/${path} b/${path}`, "--- /dev/null", `+++ b/${path}`, "@@ -0,0 +1 @@", "+hello"].join("\n");

const renderSummary = (changedPaths: ReadonlyArray<string>): void => {
  workspaceDiffMock.mockReturnValue({
    data: { targetBranchDiff: changedPaths.map(fileDiff).join("\n") } as DiffArtifact,
    isFetching: false,
    isGenerating: false,
  });
  renderWithProviders(<DiffSummary workspaceId="ws-1" />, { store: createStore() });
};

afterEach(() => {
  cleanup();
  workspaceDiffMock.mockReset();
});

describe("DiffSummary", () => {
  it("counts one changed file as a file", () => {
    renderSummary(["hello.txt"]);

    expect(screen.getByText("1 file")).toBeInTheDocument();
  });

  it("counts several changed files as files", () => {
    renderSummary(["hello.txt", "world.txt"]);

    expect(screen.getByText("2 files")).toBeInTheDocument();
  });
});
