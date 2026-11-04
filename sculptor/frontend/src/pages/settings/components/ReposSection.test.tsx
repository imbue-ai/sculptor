import { Theme } from "@radix-ui/themes";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, type RenderResult, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import { MemoryRouter } from "react-router-dom";
import type { Mock } from "vitest";
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

const renderSection = (): RenderResult => {
  const result = render(
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
  return result;
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

// Holds the next save request open until the test rejects it, so the test can
// act while the request is in flight.
const holdNextSave = (save: Mock): { reject: (error: Error) => Promise<void> } => {
  let rejectRequest: (error: Error) => void = () => {};
  save.mockReturnValueOnce(
    new Promise((_resolve, reject) => {
      rejectRequest = reject;
    }),
  );
  return {
    reject: (error): Promise<void> =>
      act(async () => {
        rejectRequest(error);
        await flushMicrotasks();
      }),
  };
};

const FIELDS = [
  {
    name: "setup command",
    save: apiHarness.updateWorkspaceSetupCommand,
    getInput: getSetupCommandInput,
    savedValue: "make setup",
  },
  {
    name: "naming pattern",
    save: apiHarness.updateNamingPattern,
    getInput: getNamingPatternInput,
    savedValue: "dev/{slug}",
  },
];

const REJECTION = { type: ToastType.ERROR, title: "rejected" };

beforeEach(() => {
  store = createStore();
  store.set(updateProjectsAtom, [PROJECT]);
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe.each(FIELDS)("a failed $name save", ({ save, getInput, savedValue }) => {
  it("restores the saved value and shows a toast", async () => {
    const request = holdNextSave(save);
    renderSection();

    editAndBlur(getInput(), "rejected edit");
    await request.reject(new Error("rejected"));

    expect(getInput().value).toBe(savedValue);
    expect(setToast).toHaveBeenCalledWith(REJECTION);
  });

  it("keeps a newer draft typed while the request was in flight", async () => {
    const request = holdNextSave(save);
    renderSection();

    editAndBlur(getInput(), "rejected edit");
    fireEvent.change(getInput(), { target: { value: "newer draft" } });
    await request.reject(new Error("rejected"));

    expect(getInput().value).toBe("newer draft");
    expect(setToast).toHaveBeenCalledWith(REJECTION);
  });

  it("keeps a draft typed into the field after it re-mounted", async () => {
    const request = holdNextSave(save);
    renderSection();

    editAndBlur(getInput(), "rejected edit");
    fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_REPO_ROW_CONFIG_TOGGLE));
    fireEvent.click(screen.getByTestId(ElementIds.SETTINGS_REPO_ROW_CONFIG_TOGGLE));
    fireEvent.change(getInput(), { target: { value: "newer draft" } });
    await request.reject(new Error("rejected"));

    expect(getInput().value).toBe("newer draft");
  });

  it("still shows a toast when the section unmounts before the request fails", async () => {
    const request = holdNextSave(save);
    const { unmount } = renderSection();

    editAndBlur(getInput(), "rejected edit");
    unmount();
    await request.reject(new Error("rejected"));

    expect(setToast).toHaveBeenCalledWith(REJECTION);
  });
});

describe("a successful repo config save", () => {
  it("leaves the project atom to the stream", async () => {
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
