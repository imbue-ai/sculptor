import { Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DirectoryEntry } from "~/api";
import { ElementIds } from "~/api";

import { AddRepoForm } from "./AddRepoForm.tsx";

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => <Theme>{children}</Theme>;

const noopFetch = async (): Promise<Array<DirectoryEntry>> => [];

const renderForm = (
  overrides: Partial<Parameters<typeof AddRepoForm>[0]> = {},
): { onBrowse: ReturnType<typeof vi.fn> } => {
  const onBrowse = vi.fn(async () => "/picked/path");
  render(
    <AddRepoForm
      fetchDirectories={noopFetch}
      path=""
      onPathChange={vi.fn()}
      onSubmit={vi.fn()}
      onBrowse={onBrowse}
      canBrowse
      {...overrides}
    />,
    { wrapper: Wrapper },
  );
  return { onBrowse };
};

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("AddRepoForm browse control", () => {
  // Bug: the browse link stayed clickable while the form was disabled, letting
  // the path be overwritten mid-validation. The fix gates handleBrowseClick on
  // `disabled` and marks the control aria-disabled.
  it("does not call onBrowse when the form is disabled", () => {
    const { onBrowse } = renderForm({ disabled: true });
    fireEvent.click(screen.getByTestId(ElementIds.ADD_REPO_BROWSE_LINK));
    expect(onBrowse).not.toHaveBeenCalled();
  });

  it("marks the browse control aria-disabled when the form is disabled", () => {
    renderForm({ disabled: true });
    expect(screen.getByTestId(ElementIds.ADD_REPO_BROWSE_LINK).getAttribute("aria-disabled")).toBe("true");
  });

  it("still calls onBrowse when the form is enabled", () => {
    const { onBrowse } = renderForm({ disabled: false });
    fireEvent.click(screen.getByTestId(ElementIds.ADD_REPO_BROWSE_LINK));
    expect(onBrowse).toHaveBeenCalledTimes(1);
  });
});
