import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { TargetBranchSelector } from "./TargetBranchSelector.tsx";

const optionFor = (branch: string): HTMLElement => {
  const option = screen
    .getAllByTestId(ElementIds.BRANCH_OPTION)
    .find((candidate) => within(candidate).queryByText(branch) !== null);
  if (option === undefined) {
    throw new Error(`No option for ${branch}`);
  }
  return option;
};

afterEach(() => {
  cleanup();
});

describe("TargetBranchSelector", () => {
  it("badges every candidate that opens pull requests into the existing PR's base", async () => {
    renderWithProviders(
      <TargetBranchSelector
        vcs="git"
        currentTargetBranch="origin/main"
        targetBranches={["origin/main", "origin/release", "upstream/release", "feature/release"]}
        prBaseNames={{
          "origin/main": "main",
          "origin/release": "release",
          "upstream/release": "release",
          "feature/release": "feature/release",
        }}
        onBranchChange={vi.fn()}
        mismatch={{ prBaseName: "release", badge: { text: "PR #847", tooltip: "Open PR targets this branch" } }}
      />,
      { store: createStore() },
    );

    await userEvent.click(screen.getByTestId(ElementIds.TARGET_BRANCH_SELECTOR));

    expect(within(optionFor("origin/release")).getByText("PR #847")).toBeTruthy();
    expect(within(optionFor("upstream/release")).getByText("PR #847")).toBeTruthy();
    expect(within(optionFor("origin/main")).queryByText("PR #847")).toBeNull();
    expect(within(optionFor("feature/release")).queryByText("PR #847")).toBeNull();
  });

  it("flags a workspace with no target branch and lets the user pick one", async () => {
    const onBranchChange = vi.fn();
    renderWithProviders(
      <TargetBranchSelector
        vcs="git"
        currentTargetBranch={null}
        targetBranches={["origin/develop"]}
        prBaseNames={{ "origin/develop": "develop" }}
        onBranchChange={onBranchChange}
      />,
      { store: createStore() },
    );

    const selector = screen.getByTestId(ElementIds.TARGET_BRANCH_SELECTOR);
    expect(within(selector).getByText("No target branch")).toBeTruthy();

    await userEvent.click(selector);
    await userEvent.click(optionFor("origin/develop"));

    expect(onBranchChange).toHaveBeenCalledWith("origin/develop");
  });

  it("names a jj workspace's missing target a bookmark", () => {
    renderWithProviders(
      <TargetBranchSelector
        vcs="jj"
        currentTargetBranch={null}
        targetBranches={["main@origin"]}
        prBaseNames={{ "main@origin": "main" }}
        onBranchChange={vi.fn()}
      />,
      { store: createStore() },
    );

    expect(within(screen.getByTestId(ElementIds.TARGET_BRANCH_SELECTOR)).getByText("No target bookmark")).toBeTruthy();
  });
});
