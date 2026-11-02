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

const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
  createElement(QueryClientProvider, { client: queryClient }, children);

beforeEach(() => {
  vi.clearAllMocks();
  mockUpdateSetupCommand.mockResolvedValue({ data: null });
  mockUpdateNamingPattern.mockResolvedValue({ data: null });
});

describe("useWorkspaceSetupCommandMutation", () => {
  it("sends the command with the settle timeout", async () => {
    const { result } = renderHook(() => useWorkspaceSetupCommandMutation(), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, command: "make setup" }));

    expect(mockUpdateSetupCommand).toHaveBeenCalledWith({
      path: { project_id: PROJECT_ID },
      body: { workspaceSetupCommand: "make setup" },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("sends null to resume tracking the default", async () => {
    const { result } = renderHook(() => useWorkspaceSetupCommandMutation(), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, command: null }));

    expect(mockUpdateSetupCommand).toHaveBeenCalledWith(
      expect.objectContaining({ body: { workspaceSetupCommand: null } }),
    );
  });

  it("surfaces a rejected request as a mutation error", async () => {
    mockUpdateSetupCommand.mockRejectedValueOnce(new Error("timeout"));
    const { result } = renderHook(() => useWorkspaceSetupCommandMutation(), { wrapper });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, command: "make setup" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("timeout");
  });
});

describe("useNamingPatternMutation", () => {
  it("sends the pattern with the settle timeout", async () => {
    const { result } = renderHook(() => useNamingPatternMutation(), { wrapper });

    await act(() => result.current.mutateAsync({ projectId: PROJECT_ID, pattern: "dev/{slug}" }));

    expect(mockUpdateNamingPattern).toHaveBeenCalledWith({
      path: { project_id: PROJECT_ID },
      body: { namingPattern: "dev/{slug}" },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
  });

  it("surfaces a rejected request as a mutation error", async () => {
    mockUpdateNamingPattern.mockRejectedValueOnce(new Error("timeout"));
    const { result } = renderHook(() => useNamingPatternMutation(), { wrapper });

    act(() => {
      result.current.mutate({ projectId: PROJECT_ID, pattern: "dev/{slug}" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error?.message).toBe("timeout");
  });
});
