import { Theme } from "@radix-ui/themes";
import { QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, type RenderResult, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore, Provider } from "jotai";
import type { ReactElement } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { Mock } from "vitest";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo, JjColocationState, ProjectJjState } from "~/api";
import { ElementIds } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus.ts";
import { updateProjectJjStatesAtom } from "~/common/state/atoms/projectJjState.ts";
import { ToastType } from "~/common/state/atoms/toasts.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";

import { RepoJjControls } from "./RepoJjControls.tsx";

const apiHarness = vi.hoisted(() => ({
  getProjectJjPreflight: vi.fn(),
  colocateProjectWithJj: vi.fn(),
  updateUseJjForNewWorkspaces: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const actual = (await importOriginal()) as Record<string, unknown>;
  return {
    ...actual,
    getProjectJjPreflight: apiHarness.getProjectJjPreflight,
    colocateProjectWithJj: apiHarness.colocateProjectWithJj,
    updateUseJjForNewWorkspaces: apiHarness.updateUseJjForNewWorkspaces,
  };
});

const PROJECT_ID = "prj-1";
const UNAVAILABLE_TOOLTIP = "Ensure that jujutsu VCS is available in the settings panel to use these features";
const LOCKED_TOOLTIP =
  "Sculptor will not destroy your jj colocation. Use the command line to complete this if you are sure.";

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const JJ_AVAILABLE_STATUS: DependenciesStatus = {
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({}),
  gh: makeInfo({}),
  jj: makeInfo({ installed: true }),
  jjReadiness: { blocker: null, identity: { name: "Ada Lovelace", email: "ada@example.com" } },
  voiceModels: makeInfo({}),
};

const jjState = (colocation: JjColocationState, colocationError: string | null = null): ProjectJjState => ({
  projectId: PROJECT_ID,
  colocation,
  colocationError,
  createsJjWorkspaces: colocation === "COLOCATED",
});

let store = createStore();
const setToast = vi.fn();

const LocationProbe = (): ReactElement => {
  const location = useLocation();
  return <div data-testid="location">{location.search}</div>;
};

const controlsTree = (useJjForNewWorkspaces: boolean): ReactElement => (
  <QueryClientProvider client={queryClient}>
    <Provider store={store}>
      <MemoryRouter initialEntries={["/settings?section=REPOSITORIES"]}>
        <Theme>
          <RepoJjControls
            projectId={PROJECT_ID}
            projectPath="/home/dev/code/sculptor"
            useJjForNewWorkspaces={useJjForNewWorkspaces}
            setToast={setToast}
          />
          <LocationProbe />
        </Theme>
      </MemoryRouter>
    </Provider>
  </QueryClientProvider>
);

const renderControls = (useJjForNewWorkspaces: boolean = false): RenderResult =>
  render(controlsTree(useJjForNewWorkspaces));

const streamJjState = (state: ProjectJjState): void => {
  act(() => {
    store.set(updateProjectJjStatesAtom, { [PROJECT_ID]: state });
  });
};

const getColocationSwitch = (): HTMLElement => screen.getByTestId(ElementIds.REPO_JJ_COLOCATION_SWITCH);
const getUseJjSwitch = (): HTMLElement => screen.getByTestId(ElementIds.REPO_JJ_USE_FOR_NEW_WORKSPACES_SWITCH);

const expectTooltipOnHover = async (control: HTMLElement, text: string): Promise<void> => {
  // A disabled switch receives no pointer events, so the tooltip hangs off its wrapper.
  await userEvent.hover(control.parentElement ?? control);
  expect((await screen.findAllByText(text)).length).toBeGreaterThan(0);
};

const confirmColocation = async (): Promise<void> => {
  fireEvent.click(getColocationSwitch());
  const confirm = await screen.findByTestId(ElementIds.JJ_COLOCATION_DIALOG_CONFIRM);
  await waitFor(() => expect(confirm).toBeEnabled());
  fireEvent.click(confirm);
};

// Holds the next request open until the test settles it. TanStack Query
// notifies observers on a timeout, so callers wait for the outcome they expect.
const holdNextRequest = (request: Mock): { resolve: () => Promise<void>; reject: (error: Error) => Promise<void> } => {
  let resolveRequest: (value: unknown) => void = () => {};

  let rejectRequest: (error: Error) => void = () => {};
  request.mockReturnValueOnce(
    new Promise((resolve, reject) => {
      resolveRequest = resolve;
      rejectRequest = reject;
    }),
  );
  return {
    resolve: (): Promise<void> =>
      act(async () => {
        resolveRequest({ data: null });
      }),
    reject: (error): Promise<void> =>
      act(async () => {
        rejectRequest(error);
      }),
  };
};

beforeEach(() => {
  store = createStore();
  store.set(dependenciesStatusAtom, JJ_AVAILABLE_STATUS);
  store.set(updateProjectJjStatesAtom, { [PROJECT_ID]: jjState("ABSENT") });
  apiHarness.getProjectJjPreflight.mockResolvedValue({
    data: { blockers: [], warnings: [], hasUncommittedChanges: false },
  });
  apiHarness.colocateProjectWithJj.mockResolvedValue({ data: null });
  apiHarness.updateUseJjForNewWorkspaces.mockResolvedValue({ data: true });
});

afterEach(() => {
  cleanup();
  queryClient.clear();
  vi.clearAllMocks();
  vi.useRealTimers();
});

describe("while jj is unavailable", () => {
  beforeEach(() => {
    store.set(dependenciesStatusAtom, null);
  });

  it("disables both switches, rather than showing the absent repository as off", () => {
    renderControls();

    expect(getColocationSwitch()).toBeDisabled();
    expect(getUseJjSwitch()).toBeDisabled();
  });

  it("explains why on hover", async () => {
    renderControls();

    await expectTooltipOnHover(getColocationSwitch(), UNAVAILABLE_TOOLTIP);
  });

  it("links to the Jujutsu page", () => {
    renderControls();

    fireEvent.click(screen.getByRole("link", { name: "Open Jujutsu settings" }));

    expect(screen.getByTestId("location")).toHaveTextContent("?section=JJ");
  });
});

describe("the colocation switch", () => {
  it("asks for confirmation before colocating", async () => {
    renderControls();

    fireEvent.click(getColocationSwitch());

    expect(await screen.findByTestId(ElementIds.JJ_COLOCATION_DIALOG)).toBeInTheDocument();
    expect(apiHarness.colocateProjectWithJj).not.toHaveBeenCalled();
    expect(getColocationSwitch()).not.toBeChecked();
  });

  it("shows the colocation initializing from confirm until the stream reports it, then locks on", async () => {
    renderControls();

    await confirmColocation();

    expect(await screen.findByText("Initializing jujutsu colocation")).toBeInTheDocument();
    expect(apiHarness.colocateProjectWithJj).toHaveBeenCalledWith(
      expect.objectContaining({ path: { project_id: PROJECT_ID } }),
    );
    expect(screen.queryByTestId(ElementIds.JJ_COLOCATION_DIALOG)).not.toBeInTheDocument();
    expect(getColocationSwitch()).toBeDisabled();

    streamJjState(jjState("INITIALIZING"));
    expect(screen.getByText("Initializing jujutsu colocation")).toBeInTheDocument();

    streamJjState(jjState("COLOCATED"));
    expect(screen.queryByText("Initializing jujutsu colocation")).not.toBeInTheDocument();
    expect(getColocationSwitch()).toBeChecked();
    expect(getColocationSwitch()).toBeDisabled();
  });

  it("shows a failure the stream reports once the colocation has started", async () => {
    renderControls();

    await confirmColocation();
    expect(await screen.findByText("Initializing jujutsu colocation")).toBeInTheDocument();
    streamJjState(jjState("INITIALIZING"));
    streamJjState(jjState("FAILED", "jj: Failed to import refs"));

    expect(screen.getByTestId(ElementIds.JJ_COLOCATION_ERROR)).toHaveTextContent("jj: Failed to import refs");
    expect(screen.queryByText("Initializing jujutsu colocation")).not.toBeInTheDocument();
  });

  it("shows a failure the stream reports before the colocation request resolves", async () => {
    const request = holdNextRequest(apiHarness.colocateProjectWithJj);
    renderControls();

    await confirmColocation();
    streamJjState(jjState("INITIALIZING"));
    streamJjState(jjState("FAILED", "jj: Failed to import refs"));
    await request.resolve();

    await waitFor(() => expect(screen.queryByText("Initializing jujutsu colocation")).not.toBeInTheDocument());
    expect(screen.getByTestId(ElementIds.JJ_COLOCATION_ERROR)).toHaveTextContent("jj: Failed to import refs");
  });

  it("returns to off when the stream never reports the colocation", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    renderControls();

    await confirmColocation();
    expect(await screen.findByText("Initializing jujutsu colocation")).toBeInTheDocument();
    // Let the accepted request settle first: the timeout starts from its success.
    await act(() => vi.advanceTimersByTimeAsync(1_000));
    expect(screen.getByText("Initializing jujutsu colocation")).toBeInTheDocument();

    await act(() => vi.advanceTimersByTimeAsync(10_000));

    expect(screen.queryByText("Initializing jujutsu colocation")).not.toBeInTheDocument();
    expect(getColocationSwitch()).toBeEnabled();
    expect(getColocationSwitch()).not.toBeChecked();
  });

  it("shows a toast and stays off when the colocation is refused", async () => {
    const request = holdNextRequest(apiHarness.colocateProjectWithJj);
    renderControls();

    await confirmColocation();
    expect(await screen.findByText("Initializing jujutsu colocation")).toBeInTheDocument();
    await request.reject(new HTTPException(409, "The repository cannot be colocated with jj: LFS"));

    await waitFor(() => expect(screen.queryByText("Initializing jujutsu colocation")).not.toBeInTheDocument());
    expect(setToast).toHaveBeenCalledWith({
      type: ToastType.ERROR,
      title: "The repository cannot be colocated with jj: LFS",
    });
    expect(getColocationSwitch()).toBeEnabled();
  });

  it("locks on for a repository already colocated, and says why on hover", async () => {
    store.set(updateProjectJjStatesAtom, { [PROJECT_ID]: jjState("COLOCATED") });
    renderControls();

    expect(getColocationSwitch()).toBeChecked();
    expect(getColocationSwitch()).toBeDisabled();
    // Radix greys out every disabled switch; the locked one keeps its "on" look.
    expect(getColocationSwitch().className).toMatch(/lockedOnSwitch/);
    await expectTooltipOnHover(getColocationSwitch(), LOCKED_TOOLTIP);
  });

  it("shows why a colocation failed, and retries it", async () => {
    store.set(updateProjectJjStatesAtom, { [PROJECT_ID]: jjState("FAILED", "jj: Failed to import refs") });
    renderControls();

    expect(screen.getByTestId(ElementIds.JJ_COLOCATION_ERROR)).toHaveTextContent("jj: Failed to import refs");
    expect(getColocationSwitch()).not.toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Retry" }));

    expect(await screen.findByText("Initializing jujutsu colocation")).toBeInTheDocument();
    expect(apiHarness.colocateProjectWithJj).toHaveBeenCalledOnce();
    expect(screen.queryByTestId(ElementIds.JJ_COLOCATION_ERROR)).not.toBeInTheDocument();
  });
});

describe("the use jj for new workspaces switch", () => {
  it("waits for the colocation, and says so on hover", async () => {
    renderControls();

    expect(getUseJjSwitch()).toBeDisabled();
    await expectTooltipOnHover(getUseJjSwitch(), "Initialize the jujutsu colocation first");
  });

  it("says what it does", () => {
    renderControls();

    expect(
      screen.getByText(
        "New workspaces in this repository are jj workspaces, with no git inside. Existing workspaces keep their kind.",
      ),
    ).toBeInTheDocument();
  });

  it("shows the requested value while the request is pending, and the stored value after it fails", async () => {
    store.set(updateProjectJjStatesAtom, { [PROJECT_ID]: jjState("COLOCATED") });
    const request = holdNextRequest(apiHarness.updateUseJjForNewWorkspaces);
    renderControls(true);
    expect(getUseJjSwitch()).toBeChecked();

    fireEvent.click(getUseJjSwitch());

    await waitFor(() => expect(getUseJjSwitch()).not.toBeChecked());
    expect(apiHarness.updateUseJjForNewWorkspaces).toHaveBeenCalledWith(
      expect.objectContaining({ path: { project_id: PROJECT_ID }, body: { useJjForNewWorkspaces: false } }),
    );

    await request.reject(new HTTPException(409, "Project prj-1 is not a jj colocation"));

    await waitFor(() => expect(getUseJjSwitch()).toBeChecked());
    expect(setToast).toHaveBeenCalledWith({ type: ToastType.ERROR, title: "Project prj-1 is not a jj colocation" });
  });

  it("shows the stored value the stream delivers once the request succeeds", async () => {
    store.set(updateProjectJjStatesAtom, { [PROJECT_ID]: jjState("COLOCATED") });
    const request = holdNextRequest(apiHarness.updateUseJjForNewWorkspaces);
    const { rerender } = renderControls(false);

    fireEvent.click(getUseJjSwitch());
    await waitFor(() => expect(getUseJjSwitch()).toBeChecked());

    expect(getUseJjSwitch()).toBeDisabled();

    rerender(controlsTree(true));
    await request.resolve();

    await waitFor(() => expect(getUseJjSwitch()).toBeEnabled());
    expect(getUseJjSwitch()).toBeChecked();
    expect(setToast).not.toHaveBeenCalled();
  });
});
