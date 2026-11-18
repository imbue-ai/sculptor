import { Theme } from "@radix-ui/themes";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, type RenderResult, screen, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { JjColocationPreflight } from "~/api";
import { ElementIds } from "~/api";
import { queryClient } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";

import { JjColocationDialog } from "./JjColocationDialog.tsx";

const apiHarness = vi.hoisted(() => ({
  getProjectJjPreflight: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return { ...actual, getProjectJjPreflight: apiHarness.getProjectJjPreflight };
});

const CLEAN_PREFLIGHT: JjColocationPreflight = {
  blockers: [],
  warnings: [],
  hasUncommittedChanges: false,
  jjUnavailableReason: null,
};

const onClose = vi.fn();
const onConfirm = vi.fn();

const store = createStore();

const LocationProbe = (): ReactElement => {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
};

const dialogTree = (isOpen: boolean): ReactElement => (
  <QueryClientProvider client={queryClient}>
    <Provider store={store}>
      <MemoryRouter initialEntries={["/settings?section=REPOSITORIES"]}>
        <Theme>
          <JjColocationDialog
            projectId="prj-1"
            projectPath="/home/dev/code/sculptor"
            isOpen={isOpen}
            onClose={onClose}
            onConfirm={onConfirm}
          />
          <LocationProbe />
        </Theme>
      </MemoryRouter>
    </Provider>
  </QueryClientProvider>
);

const renderDialog = (isOpen: boolean = true): RenderResult => render(dialogTree(isOpen));

const getConfirm = (): HTMLElement => screen.getByTestId(ElementIds.JJ_COLOCATION_DIALOG_CONFIRM);

beforeEach(() => {
  apiHarness.getProjectJjPreflight.mockResolvedValue({ data: CLEAN_PREFLIGHT });
});

afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.clearAllMocks();
});

describe("JjColocationDialog", () => {
  it("reads the pre-flight of the repository when it opens", async () => {
    renderDialog();

    expect(getConfirm()).toBeDisabled();
    expect(screen.getByText(/Checking the repository/)).toBeInTheDocument();
    await waitFor(() => expect(getConfirm()).toBeEnabled());

    expect(apiHarness.getProjectJjPreflight).toHaveBeenCalledWith({ path: { project_id: "prj-1" } });
    expect(screen.getByText("jj git init --colocate")).toBeInTheDocument();
    expect(screen.getByText("/home/dev/code/sculptor")).toBeInTheDocument();
    expect(screen.getByText(/git keeps working in this repository/i)).toBeInTheDocument();
    expect(screen.getByText(/git shows untracked files as added/i)).toBeInTheDocument();
  });

  it("does not read the pre-flight while closed", () => {
    renderDialog(false);

    expect(apiHarness.getProjectJjPreflight).not.toHaveBeenCalled();
  });

  it("reads the pre-flight again each time it opens", async () => {
    const { rerender } = renderDialog();
    await waitFor(() => expect(getConfirm()).toBeEnabled());

    apiHarness.getProjectJjPreflight.mockResolvedValue({ data: { ...CLEAN_PREFLIGHT, blockers: ["LFS"] } });
    rerender(dialogTree(false));
    rerender(dialogTree(true));

    expect(screen.getByText(/Checking the repository/)).toBeInTheDocument();
    expect(getConfirm()).toBeDisabled();
    await screen.findByText(/uses Git LFS/);
    expect(apiHarness.getProjectJjPreflight).toHaveBeenCalledTimes(2);
  });

  it("confirms the colocation", async () => {
    renderDialog();
    await waitFor(() => expect(getConfirm()).toBeEnabled());

    fireEvent.click(getConfirm());

    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("disables confirm and names each blocker", async () => {
    apiHarness.getProjectJjPreflight.mockResolvedValue({
      data: { ...CLEAN_PREFLIGHT, blockers: ["JJ_REPOSITORY_NOT_COLOCATED", "SUBMODULES"] },
    });
    renderDialog();

    await screen.findByText(/Sculptor never deletes a .jj directory/);

    expect(screen.getByText(/uses git submodules/)).toBeInTheDocument();
    expect(getConfirm()).toBeDisabled();
  });

  it("says why jj is unavailable in the backend's words, with a link to the Jujutsu page", async () => {
    apiHarness.getProjectJjPreflight.mockResolvedValue({
      data: {
        ...CLEAN_PREFLIGHT,
        blockers: ["JJ_UNAVAILABLE"],
        jjUnavailableReason: "jj cannot run: Config error: expected a table",
      },
    });
    renderDialog();

    await screen.findByText(/jj cannot run: Config error: expected a table/);
    expect(getConfirm()).toBeDisabled();

    fireEvent.click(screen.getByRole("link", { name: "Open Jujutsu settings" }));

    expect(screen.getByTestId("location")).toHaveTextContent("?section=JJ");
  });

  it("lists warnings and uncommitted changes without blocking", async () => {
    apiHarness.getProjectJjPreflight.mockResolvedValue({
      data: { ...CLEAN_PREFLIGHT, warnings: ["HOOKS", "SPARSE_CHECKOUT"], hasUncommittedChanges: true },
    });
    renderDialog();

    await screen.findByText(/hooks do not run in jj workspaces/i);

    expect(screen.getByText(/sparse checkout/i)).toBeInTheDocument();
    expect(screen.getByText(/uncommitted changes become jj's working-copy commit/i)).toBeInTheDocument();
    expect(getConfirm()).toBeEnabled();
  });

  it("disables confirm when the pre-flight cannot be read", async () => {
    apiHarness.getProjectJjPreflight.mockRejectedValue(
      new HTTPException(409, "Cannot read the repository: not a git repository"),
    );
    renderDialog();

    await screen.findByText(/Cannot read the repository: not a git repository/);

    expect(getConfirm()).toBeDisabled();
  });
});
