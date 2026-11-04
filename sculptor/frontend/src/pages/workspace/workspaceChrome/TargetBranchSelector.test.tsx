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
  it("badges the remote branch that an existing PR targets", async () => {
    renderWithProviders(
      <TargetBranchSelector
        currentTargetBranch="origin/main"
        targetBranches={["origin/main", "origin/release", "release"]}
        onBranchChange={vi.fn()}
        mismatch={{ targetBranch: "release", badge: { text: "PR #847", tooltip: "Open PR targets this branch" } }}
      />,
      { store: createStore() },
    );

    await userEvent.click(screen.getByTestId(ElementIds.TARGET_BRANCH_SELECTOR));

    expect(within(optionFor("origin/release")).getByText("PR #847")).toBeTruthy();
    expect(within(optionFor("origin/main")).queryByText("PR #847")).toBeNull();
    expect(within(optionFor("release")).queryByText("PR #847")).toBeNull();
  });
});
