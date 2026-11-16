import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import { ToastType, workspaceTargetChangeErrorToastAtom } from "~/common/state/atoms/toasts.ts";
import { MUTATION_SETTLE_TIMEOUT_MS } from "~/common/state/mutations/index.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";

import { useWorkspaceTargetChange } from "./useWorkspaceTargetChange.ts";

const { mockUpdateWorkspace } = vi.hoisted(() => ({ mockUpdateWorkspace: vi.fn() }));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return { ...actual, updateWorkspace: mockUpdateWorkspace };
});

const WORKSPACE_ID = "ws-target-1";

const renderTargetChange = (): {
  store: ReturnType<typeof createStore>;
  changeTarget: (targetBranch: string) => void;
} => {
  const store = createStore();
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={queryClient}>
      <Provider store={store}>{children}</Provider>
    </QueryClientProvider>
  );
  const { result } = renderHook(() => useWorkspaceTargetChange(WORKSPACE_ID), { wrapper });
  return { store, changeTarget: result.current };
};

beforeEach(() => {
  vi.clearAllMocks();
  mockUpdateWorkspace.mockResolvedValue({ data: null });
});

describe("useWorkspaceTargetChange", () => {
  it("sends the new target with the settle timeout and raises nothing on success", async () => {
    const { store, changeTarget } = renderTargetChange();

    act(() => changeTarget("main@origin"));

    await waitFor(() =>
      expect(mockUpdateWorkspace).toHaveBeenCalledWith({
        path: { workspace_id: WORKSPACE_ID },
        body: { targetBranch: "main@origin" },
        meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
      }),
    );
    expect(store.get(workspaceTargetChangeErrorToastAtom)).toBeNull();
  });

  it("shows a rejected change with the server's reason", async () => {
    mockUpdateWorkspace.mockRejectedValueOnce(new HTTPException(404, `Workspace ${WORKSPACE_ID} not found`));
    const { store, changeTarget } = renderTargetChange();

    act(() => changeTarget("origin/release"));

    await waitFor(() =>
      expect(store.get(workspaceTargetChangeErrorToastAtom)).toEqual({
        title: "Could not change the target to origin/release",
        description: `Workspace ${WORKSPACE_ID} not found`,
        type: ToastType.ERROR,
        action: null,
      }),
    );
  });
});
