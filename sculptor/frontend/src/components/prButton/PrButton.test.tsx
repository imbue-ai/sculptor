import { cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PrStatusInfo } from "~/api";
import { ElementIds } from "~/api";
import { reusableTabTarget } from "~/common/reusableTabTarget.ts";
import { prStatusAtomFamily } from "~/common/state/atoms/prStatus.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { PrButton } from "./PrButton.tsx";

// posthog isn't initialised in tests; the button captures an analytics event
// on click, so stub it to a no-op.
vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const WORKSPACE_ID = "ws-pr-1";
const PR_URL = "https://github.com/imbue-ai/sculptor/pull/392";

const storeWith = (status: PrStatusInfo): ReturnType<typeof createStore> => {
  const store = createStore();
  store.set(prStatusAtomFamily(WORKSPACE_ID), status);
  return store;
};

const prStatus = (overrides: Partial<PrStatusInfo>): PrStatusInfo => ({
  workspaceId: WORKSPACE_ID,
  prState: "open",
  prIid: 392,
  prWebUrl: PR_URL,
  ...overrides,
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("PrButton opens PRs in a reusable browser tab", () => {
  it("opens an open PR in its stable named tab, not _blank", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch="origin/main" gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "open" })),
    });

    fireEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_OPEN));

    expect(open).toHaveBeenCalledWith(PR_URL, reusableTabTarget(PR_URL));
    expect(open).not.toHaveBeenCalledWith(PR_URL, "_blank");
  });

  it("opens a merged PR in the same reusable tab as the open PR", () => {
    const open = vi.spyOn(window, "open").mockImplementation(() => null);
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch="origin/main" gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "merged" })),
    });

    fireEvent.click(screen.getByTestId(ElementIds.PR_BUTTON_MERGED));

    expect(open).toHaveBeenCalledWith(PR_URL, reusableTabTarget(PR_URL));
  });
});

describe("PrButton without a target branch", () => {
  it("disables Create PR", () => {
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch={null} gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "none" })),
    });

    expect(screen.getByTestId(ElementIds.PR_BUTTON_CREATE)).toBeDisabled();
  });
});

describe("PrButton offers to adopt an existing PR only when it targets another branch", () => {
  const renderWithNoPr = (targetBranch: string, mismatchedPrTargetBranch: string): void => {
    renderWithProviders(<PrButton workspaceId={WORKSPACE_ID} targetBranch={targetBranch} gitProvider="github" />, {
      store: storeWith(prStatus({ prState: "none", mismatchedPrIid: 7, mismatchedPrTargetBranch })),
    });
  };

  it("offers the existing PR when it targets a different branch", () => {
    renderWithNoPr("origin/main", "release");

    expect(screen.getByTestId(ElementIds.PR_BUTTON_ASSIGN)).toBeTruthy();
  });

  it("offers to create a PR when the existing PR targets the remote target's branch", () => {
    renderWithNoPr("origin/main", "main");

    expect(screen.getByTestId(ElementIds.PR_BUTTON_CREATE)).toBeTruthy();
  });

  it("keeps offering the reported PR when the target is a local branch with a slash", () => {
    // PR status matches `feature/login` as `login`, so it reports the PR based
    // on `feature/login` as a mismatch. Answering that with "Create PR" would
    // hide the PR that already exists.
    renderWithNoPr("feature/login", "feature/login");

    expect(screen.getByTestId(ElementIds.PR_BUTTON_ASSIGN)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.PR_BUTTON_CREATE)).toBeNull();
  });
});
