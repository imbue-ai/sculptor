import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "../../../api";
import { queryClient } from "../queryClient.ts";
import { MUTATION_SETTLE_TIMEOUT_MS } from "./index";
import { useNamingPatternMutation, useWorkspaceSetupCommandMutation } from "./projects";

const { mockUpdateSetupCommand, mockUpdateNamingPattern } = vi.hoisted(() => ({
  mockUpdateSetupCommand: vi.fn(),
  mockUpdateNamingPattern: vi.fn(),
}));

vi.mock("../../../api", async () => {
  const actual = await vi.importActual<typeof api>("../../../api");
  return {
    ...actual,
    updateWorkspaceSetupCommand: mockUpdateSetupCommand,
    updateNamingPattern: mockUpdateNamingPattern,
  };
});

const PROJECT_ID = "prj-1";
const onError = vi.fn();

const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
  createElement(QueryClientProvider, { client: queryClient }, children);

beforeEach(() => {
  vi.clearAllMocks();
  mockUpdateSetupCommand.mockResolvedValue({ data: null });
  mockUpdateNamingPattern.mockResolvedValue({ data: null });
});

describe("useWorkspaceSetupCommandMutation", () => {
  it("sends the command with the settle timeout", async () => {
    const { result } = renderHook(() => useWorkspaceSetupCommandMutation({ onError }), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, command: "make setup" }));

    expect(mockUpdateSetupCommand).toHaveBeenCalledWith({
      path: { project_id: PROJECT_ID },
      body: { workspaceSetupCommand: "make setup" },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("sends null to resume tracking the default", async () => {
    const { result } = renderHook(() => useWorkspaceSetupCommandMutation({ onError }), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, command: null }));

    expect(mockUpdateSetupCommand).toHaveBeenCalledWith(
      expect.objectContaining({ body: { workspaceSetupCommand: null } }),
    );
  });

  it("reports a rejected request to onError", async () => {
    const error = new Error("timeout");
    mockUpdateSetupCommand.mockRejectedValueOnce(error);
    const { result } = renderHook(() => useWorkspaceSetupCommandMutation({ onError }), { wrapper });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, command: "make setup" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toBe(error);
  });
});

describe("useNamingPatternMutation", () => {
  it("sends the pattern with the settle timeout", async () => {
    const { result } = renderHook(() => useNamingPatternMutation({ onError }), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, pattern: "dev/{slug}" }));

    expect(mockUpdateNamingPattern).toHaveBeenCalledWith({
      path: { project_id: PROJECT_ID },
      body: { namingPattern: "dev/{slug}" },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("reports a rejected request to onError", async () => {
    const error = new Error("timeout");
    mockUpdateNamingPattern.mockRejectedValueOnce(error);
    const { result } = renderHook(() => useNamingPatternMutation({ onError }), { wrapper });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, pattern: "dev/{slug}" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(onError).toHaveBeenCalledOnce();
    expect(onError.mock.calls[0][0]).toBe(error);
  });
});
