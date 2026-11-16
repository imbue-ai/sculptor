import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import { queryClient } from "../queryClient.ts";
import { MUTATION_SETTLE_TIMEOUT_MS } from "./index";
import { useColocateProjectMutation, useUseJjForNewWorkspacesMutation } from "./projectJj";

const { mockColocate, mockUpdateUseJj } = vi.hoisted(() => ({
  mockColocate: vi.fn(),
  mockUpdateUseJj: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    colocateProjectWithJj: mockColocate,
    updateUseJjForNewWorkspaces: mockUpdateUseJj,
  };
});

const PROJECT_ID = "prj-1";
const onError = vi.fn();

const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
  createElement(QueryClientProvider, { client: queryClient }, children);

beforeEach(() => {
  vi.clearAllMocks();
  mockColocate.mockResolvedValue({ data: null });
  mockUpdateUseJj.mockResolvedValue({ data: true });
});

describe("useColocateProjectMutation", () => {
  it("posts the colocation with the settle timeout", async () => {
    const { result } = renderHook(() => useColocateProjectMutation({ onError }), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID }));

    expect(mockColocate).toHaveBeenCalledWith({
      path: { project_id: PROJECT_ID },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("reports a rejected request to onError", async () => {
    const error = new Error("409");
    mockColocate.mockRejectedValueOnce(error);
    const { result } = renderHook(() => useColocateProjectMutation({ onError }), { wrapper });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toBe(error);
  });
});

describe("useUseJjForNewWorkspacesMutation", () => {
  it("sends the requested value with the settle timeout", async () => {
    const { result } = renderHook(() => useUseJjForNewWorkspacesMutation({ onError }), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, useJjForNewWorkspaces: false }));

    expect(mockUpdateUseJj).toHaveBeenCalledWith({
      path: { project_id: PROJECT_ID },
      body: { useJjForNewWorkspaces: false },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("reports a rejected request to onError", async () => {
    const error = new Error("412");
    mockUpdateUseJj.mockRejectedValueOnce(error);
    const { result } = renderHook(() => useUseJjForNewWorkspacesMutation({ onError }), { wrapper });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, useJjForNewWorkspaces: true });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toBe(error);
  });
});
