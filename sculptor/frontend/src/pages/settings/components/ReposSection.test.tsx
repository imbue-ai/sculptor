import { Theme } from "@radix-ui/themes";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { Project } from "~/api";
import { ElementIds } from "~/api";
import { projectAtomFamily, updateProjectsAtom } from "~/common/state/atoms/projects.ts";
import { ToastType } from "~/common/state/atoms/toasts.ts";
import { queryClient } from "~/common/state/queryClient.ts";

import { ReposSection } from "./ReposSection.tsx";

const apiHarness = vi.hoisted(() => ({
  updateWorkspaceSetupCommand: vi.fn(),
  updateNamingPattern: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    updateWorkspaceSetupCommand: apiHarness.updateWorkspaceSetupCommand,
    updateNamingPattern: apiHarness.updateNamingPattern,
  };
});

const PROJECT: Project = {
  objectId: "prj-1",
  organizationReference: "org-1",
  name: "sculptor",
  userGitRepoUrl: "file:///home/dev/code/sculptor",
  isPathAccessible: true,
  workspaceSetupCommand: "make setup",
  namingPattern: "dev/{slug}",
};

let store = createStore();
const setToast = vi.fn();

const renderSection = (): void => {
  render(
    <QueryClientProvider client={queryClient}>
      <Provider store={store}>
        <MemoryRouter>
          <Theme>
            <ReposSection setToast={setToast} />
          </Theme>
        </MemoryRouter>
      </Provider>
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_REPO_ROW_CONFIG_TOGGLE));
};

const getSetupCommandInput = (): HTMLTextAreaElement =>
  screen.getByTestId(ElementIds.SETTINGS_WORKSPACE_SETUP_COMMAND_INPUT) as HTMLTextAreaElement;

const getNamingPatternInput = (): HTMLInputElement =>
  screen.getByTestId(ElementIds.SETTINGS_NAMING_PATTERN_INPUT) as HTMLInputElement;

const editAndBlur = (field: HTMLTextAreaElement | HTMLInputElement, value: string): void => {
  fireEvent.change(field, { target: { value } });
  fireEvent.blur(field);
};

// Lets every pending promise continuation run, so a write chained after the
// request resolving would have landed by the time the test asserts.
const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

beforeEach(() => {
  store = createStore();
  store.set(updateProjectsAtom, [PROJECT]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ReposSection repo config saves", () => {
  it("restores the saved setup command and shows a toast when the save fails", async () => {
    apiHarness.updateWorkspaceSetupCommand.mockRejectedValue(new Error("disk full"));
    renderSection();

    editAndBlur(getSetupCommandInput(), "make broken");

    await waitFor(() => expect(setToast).toHaveBeenCalledWith({ type: ToastType.ERROR, title: "disk full" }));
    expect(getSetupCommandInput().value).toBe("make setup");
  });

  it("restores the saved naming pattern and shows a toast when the save fails", async () => {
    apiHarness.updateNamingPattern.mockRejectedValue(new Error("invalid pattern"));
    renderSection();

    editAndBlur(getNamingPatternInput(), "bad/{");

    await waitFor(() => expect(setToast).toHaveBeenCalledWith({ type: ToastType.ERROR, title: "invalid pattern" }));
    expect(getNamingPatternInput().value).toBe("dev/{slug}");
  });

  it("leaves the project atom to the stream when a save succeeds", async () => {
    apiHarness.updateWorkspaceSetupCommand.mockResolvedValue({ data: "make fast" });
    apiHarness.updateNamingPattern.mockResolvedValue({ data: "dev/{ticket}" });
    renderSection();

    editAndBlur(getSetupCommandInput(), "make fast");
    editAndBlur(getNamingPatternInput(), "dev/{ticket}");
    await flushMicrotasks();

    expect(apiHarness.updateWorkspaceSetupCommand).toHaveBeenCalledOnce();
    expect(apiHarness.updateNamingPattern).toHaveBeenCalledOnce();
    expect(store.get(projectAtomFamily(PROJECT.objectId))).toBe(PROJECT);
    expect(getSetupCommandInput().value).toBe("make fast");
    expect(getNamingPatternInput().value).toBe("dev/{ticket}");
    expect(setToast).not.toHaveBeenCalled();
  });
});
