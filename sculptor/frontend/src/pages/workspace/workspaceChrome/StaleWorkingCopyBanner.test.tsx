import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createStore } from "jotai";
import { afterEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import type { WorkspaceJjStateInfo } from "~/api";
import { ElementIds } from "~/api";
import { workspaceJjStateAtomFamily } from "~/common/state/atoms/workspaceJjState.ts";
import { MUTATION_SETTLE_TIMEOUT_MS } from "~/common/state/mutations/index.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { StaleWorkingCopyBanner } from "./StaleWorkingCopyBanner.tsx";

const { mockUpdateStaleWorkingCopy } = vi.hoisted(() => ({ mockUpdateStaleWorkingCopy: vi.fn() }));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return { ...actual, updateStaleWorkingCopy: mockUpdateStaleWorkingCopy };
});

const WORKSPACE_ID = "ws-stale";

const renderBanner = (jjState: Partial<WorkspaceJjStateInfo> | null): void => {
  const store = createStore();
  if (jjState !== null) {
    store.set(workspaceJjStateAtomFamily(WORKSPACE_ID), {
      workspaceId: WORKSPACE_ID,
      workingCopyChangeId: "kxqpmzvyrstuwlnokxqpmzvyrstuwlno",
      workingCopyChangeIdPrefixLength: 2,
      workingCopyDescription: "",
      isWorkingCopyEmpty: false,
      bookmarks: [],
      primaryBookmark: null,
      unbookmarkedRevisionCount: 0,
      hasConflict: false,
      isDivergent: false,
      isWorkingCopyStale: false,
      ...jjState,
    });
  }
  renderWithProviders(
    <QueryClientProvider client={queryClient}>
      <StaleWorkingCopyBanner workspaceId={WORKSPACE_ID} />
    </QueryClientProvider>,
    { store },
  );
};

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("StaleWorkingCopyBanner", () => {
  it("shows nothing while the working copy is current", () => {
    renderBanner({ isWorkingCopyStale: false });

    expect(screen.queryByTestId(ElementIds.JJ_STALE_BANNER)).toBeNull();
  });

  it("shows nothing for a workspace with no jj state", () => {
    renderBanner(null);

    expect(screen.queryByTestId(ElementIds.JJ_STALE_BANNER)).toBeNull();
  });

  it("offers to update a stale working copy, and asks the backend to", async () => {
    const user = userEvent.setup();
    mockUpdateStaleWorkingCopy.mockResolvedValue({ data: undefined });
    renderBanner({ isWorkingCopyStale: true });

    expect(screen.getByTestId(ElementIds.JJ_STALE_BANNER).textContent).toContain("working copy is stale");
    await user.click(screen.getByTestId(ElementIds.JJ_UPDATE_STALE_BUTTON));

    await waitFor(() =>
      expect(mockUpdateStaleWorkingCopy).toHaveBeenCalledWith({
        path: { workspace_id: WORKSPACE_ID },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    );
  });

  it("says why the update failed", async () => {
    const user = userEvent.setup();
    mockUpdateStaleWorkingCopy.mockRejectedValue(new HTTPException(409, "jj could not update the working copy"));
    renderBanner({ isWorkingCopyStale: true });

    await user.click(screen.getByTestId(ElementIds.JJ_UPDATE_STALE_BUTTON));

    await waitFor(() =>
      expect(screen.getByTestId(ElementIds.JJ_STALE_BANNER).textContent).toContain(
        "jj could not update the working copy",
      ),
    );
  });
});
