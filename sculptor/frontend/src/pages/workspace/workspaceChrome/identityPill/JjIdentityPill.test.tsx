import { cleanup, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it } from "vitest";

import type { Workspace, WorkspaceJjStateInfo } from "~/api";
import { ElementIds, WorkspaceInitializationStrategy } from "~/api";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";
import { workspaceAtomFamily } from "~/common/state/atoms/workspaces.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { JjIdentityPill } from "./JjIdentityPill.tsx";

type Store = ReturnType<typeof createStore>;

const CHANGE_ID = "kxqpmzvyrstuwlnokxqpmzvyrstuwlno";

const makeStore = (inputs: {
  requestedBookmark: string | null;
  jjState: Partial<WorkspaceJjStateInfo> | null;
}): Store => {
  const store = createStore();
  const workspace: Workspace = {
    objectId: "ws1",
    projectId: "proj-1",
    organizationReference: "org-1",
    description: "My workspace",
    initializationStrategy: WorkspaceInitializationStrategy.JJ_WORKSPACE,
    sourceBranch: "main@origin",
    targetBranch: "main@origin",
    requestedBranchName: inputs.requestedBookmark,
  };
  store.set(workspaceAtomFamily("ws1"), workspace);
  if (inputs.jjState !== null) {
    store.set(workspaceJjStateAtomFamily("ws1"), {
      workspaceId: "ws1",
      workingCopyChangeId: CHANGE_ID,
      workingCopyChangeIdPrefixLength: 2,
      workingCopyDescription: "",
      isWorkingCopyEmpty: false,
      bookmarks: [],
      primaryBookmark: null,
      unbookmarkedRevisionCount: 0,
      hasConflict: false,
      isDivergent: false,
      isWorkingCopyStale: false,
      ...inputs.jjState,
    });
  }
  return store;
};

const renderPill = (store: Store): void => {
  renderWithProviders(<JjIdentityPill workspaceId="ws1" />, { store });
};

const pill = (): HTMLElement => screen.getByTestId(ElementIds.JJ_IDENTITY_PILL);

afterEach(() => {
  cleanup();
});

describe("JjIdentityPill", () => {
  it("shows the primary bookmark and copies it on click", async () => {
    const user = userEvent.setup();
    renderPill(
      makeStore({
        requestedBookmark: "dev/requested",
        jjState: { bookmarks: ["dev/feature"], primaryBookmark: "dev/feature" },
      }),
    );

    expect(within(pill()).getByText("dev/feature")).toBeTruthy();
    await user.click(pill());

    expect(await navigator.clipboard.readText()).toBe("dev/feature");
  });

  it("counts the bookmarks besides the primary one", () => {
    renderPill(
      makeStore({
        requestedBookmark: null,
        jjState: { bookmarks: ["dev/feature", "dev/part-2", "dev/part-3"], primaryBookmark: "dev/feature" },
      }),
    );

    expect(screen.getByTestId(ElementIds.JJ_IDENTITY_MORE_BOOKMARKS).textContent).toBe("+2");
  });

  it("shows no count when the primary bookmark is the only one", () => {
    renderPill(
      makeStore({ requestedBookmark: null, jjState: { bookmarks: ["dev/feature"], primaryBookmark: "dev/feature" } }),
    );

    expect(screen.queryByTestId(ElementIds.JJ_IDENTITY_MORE_BOOKMARKS)).toBeNull();
  });

  it("shows the requested bookmark until it exists, and copies the change id meanwhile", async () => {
    const user = userEvent.setup();
    renderPill(makeStore({ requestedBookmark: "dev/requested", jjState: {} }));

    expect(within(pill()).getByText("dev/requested")).toBeTruthy();
    expect(pill().getAttribute("aria-label")).toBe("Copy change id kxqpmzvy");
    await user.click(pill());

    expect(await navigator.clipboard.readText()).toBe(CHANGE_ID);
  });

  it("shows the change id and description when there is no bookmark and none was requested", async () => {
    const user = userEvent.setup();
    renderPill(makeStore({ requestedBookmark: null, jjState: { workingCopyDescription: "Add the login form" } }));

    expect(pill().textContent).toContain("kxqpmzvy");
    expect(within(pill()).getByText("Add the login form")).toBeTruthy();
    await user.click(pill());

    expect(await navigator.clipboard.readText()).toBe(CHANGE_ID);
  });

  it("marks the described revisions above the primary bookmark", () => {
    renderPill(
      makeStore({
        requestedBookmark: null,
        jjState: { bookmarks: ["dev/feature"], primaryBookmark: "dev/feature", unbookmarkedRevisionCount: 3 },
      }),
    );

    expect(screen.getByTestId(ElementIds.JJ_UNBOOKMARKED_MARKER).textContent).toBe("↑3");
  });

  it("shows no marker when no described revision sits above the bookmark", () => {
    renderPill(
      makeStore({ requestedBookmark: null, jjState: { bookmarks: ["dev/feature"], primaryBookmark: "dev/feature" } }),
    );

    expect(screen.queryByTestId(ElementIds.JJ_UNBOOKMARKED_MARKER)).toBeNull();
  });

  it("badges a working copy with unresolved conflicts", () => {
    renderPill(makeStore({ requestedBookmark: null, jjState: { hasConflict: true } }));

    expect(within(pill()).getByText("conflict")).toBeTruthy();
  });

  it("lists the bookmarks, change, description, flags and target in its card", async () => {
    const user = userEvent.setup();
    renderPill(
      makeStore({
        requestedBookmark: null,
        jjState: {
          bookmarks: ["dev/feature", "dev/part-2"],
          primaryBookmark: "dev/feature",
          workingCopyDescription: "Add the login form",
          isDivergent: true,
        },
      }),
    );

    await user.tab();
    const card = await screen.findByTestId(ElementIds.JJ_IDENTITY_CARD);

    expect(within(card).getByText("dev/feature")).toBeTruthy();
    expect(within(card).getByText("dev/part-2")).toBeTruthy();
    expect(card.textContent).toContain(CHANGE_ID);
    expect(within(card).getByText("Add the login form")).toBeTruthy();
    expect(within(card).getByText("divergent")).toBeTruthy();
    expect(within(card).getByText("main@origin")).toBeTruthy();
  });

  it("names the requested bookmark in its card while the workspace has none", async () => {
    const user = userEvent.setup();
    renderPill(makeStore({ requestedBookmark: "dev/requested", jjState: {} }));

    await user.tab();
    const card = await screen.findByTestId(ElementIds.JJ_IDENTITY_CARD);

    expect(card.textContent).toContain("dev/requested");
    expect(card.textContent).toContain("(no description set)");
  });
});
