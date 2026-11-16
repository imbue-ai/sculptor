import { cleanup, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ElementIds } from "~/api";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";
import type { WorkspaceVcs } from "~/common/utils/workspaceVcs.ts";

import { DiscardDialog } from "./DiscardDialog.tsx";

const renderDialog = (inputs: {
  vcs: WorkspaceVcs;
  isDiscarding?: boolean;
  errorMessage?: string | null;
  onConfirm?: () => void;
  onOpenChange?: (open: boolean) => void;
}): void => {
  renderWithProviders(
    <DiscardDialog
      open
      onOpenChange={inputs.onOpenChange ?? vi.fn()}
      filePath="src/app.py"
      vcs={inputs.vcs}
      isDiscarding={inputs.isDiscarding ?? false}
      errorMessage={inputs.errorMessage ?? null}
      onConfirm={inputs.onConfirm ?? vi.fn()}
    />,
    { store: createStore() },
  );
};

const dialog = (): HTMLElement => screen.getByTestId(ElementIds.DISCARD_DIALOG);

afterEach(() => {
  cleanup();
});

describe("DiscardDialog", () => {
  it("warns a git workspace that a discard cannot be undone", () => {
    renderDialog({ vcs: "git" });

    expect(dialog().textContent).toContain("Discard changes to app.py? This cannot be undone.");
  });

  it("tells a jj workspace that the discarded content stays in the operation log", () => {
    renderDialog({ vcs: "jj" });

    expect(dialog().textContent).toContain("Discard changes to app.py?");
    expect(dialog().textContent).toContain("recoverable from the jj operation log");
    expect(dialog().textContent).not.toContain("cannot be undone");
  });

  it("stays open on confirm so the caller can close it once the discard lands", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    renderDialog({ vcs: "jj", onConfirm, onOpenChange });

    await user.click(screen.getByTestId(ElementIds.DISCARD_DIALOG_CONFIRM));

    expect(onConfirm).toHaveBeenCalledOnce();
    expect(onOpenChange).not.toHaveBeenCalled();
  });

  it("shows why a discard failed", () => {
    renderDialog({ vcs: "jj", errorMessage: "The working copy is stale" });

    expect(screen.getByTestId(ElementIds.DISCARD_DIALOG_ERROR).textContent).toContain("The working copy is stale");
  });

  it("disables the confirm button while the discard runs", () => {
    renderDialog({ vcs: "git", isDiscarding: true });

    expect(screen.getByTestId(ElementIds.DISCARD_DIALOG_CONFIRM)).toHaveProperty("disabled", true);
  });
});
