import { cleanup, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { GlobalDefaultsSection } from "./GlobalDefaultsSection.tsx";

afterEach(() => {
  cleanup();
});

describe("GlobalDefaultsSection", () => {
  it("says the naming pattern and the deletion policy cover jj workspaces' bookmarks as well as branches", () => {
    renderWithProviders(<GlobalDefaultsSection onSettingChange={vi.fn().mockResolvedValue(undefined)} />, {
      store: createStore(),
    });

    expect(
      screen.getByText(
        "Names the branch, or the jj bookmark, a new workspace creates. Supports <user> and <slug> placeholders. Per-repo overrides on Repositories.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("Branch and bookmark deletion when a workspace is removed")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Applies to a worktree workspace's branch and a jj workspace's bookmarks. “Delete if safe” deletes only what it can without losing work; “Always” deletes regardless.",
      ),
    ).toBeInTheDocument();
  });
});
