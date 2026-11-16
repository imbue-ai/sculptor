import { QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import { MUTATION_SETTLE_TIMEOUT_MS } from "~/common/state/mutations/index.ts";
import { queryClient } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";

import { useDiscardFile } from "./useDiscardFile.ts";

const { mockDiscardWorkspaceFile, mockGetWorkspaceDiff } = vi.hoisted(() => ({
  mockDiscardWorkspaceFile: vi.fn(),
  mockGetWorkspaceDiff: vi.fn(),
}));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return { ...actual, discardWorkspaceFile: mockDiscardWorkspaceFile, getWorkspaceDiff: mockGetWorkspaceDiff };
});

const WORKSPACE_ID = "ws-discard";

const renderDiscard = (): { result: { current: ReturnType<typeof useDiscardFile> } } => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={queryClient}>
      <Provider store={createStore()}>{children}</Provider>
    </QueryClientProvider>
  );
  return renderHook(() => useDiscardFile(WORKSPACE_ID), { wrapper });
};

beforeEach(() => {
  mockGetWorkspaceDiff.mockResolvedValue({ data: { diff: { uncommittedDiff: "" } } });
});

afterEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
});

describe("useDiscardFile", () => {
  it("discards the file, re-reads the diff and reports success", async () => {
    mockDiscardWorkspaceFile.mockResolvedValue({ data: { result: { success: true, stdout: "", stderr: "" } } });
    const onDiscarded = vi.fn();
    const { result } = renderDiscard();

    act(() => result.current.discardFile("src/app.py", onDiscarded));

    await waitFor(() => expect(onDiscarded).toHaveBeenCalledOnce());
    expect(mockDiscardWorkspaceFile).toHaveBeenCalledWith({
      path: { workspace_id: WORKSPACE_ID },
      body: { filePath: "src/app.py" },
      meta: { timeout: MUTATION_SETTLE_TIMEOUT_MS },
    });
    expect(mockGetWorkspaceDiff).toHaveBeenCalled();
    expect(result.current.errorMessage).toBeNull();
  });

  it("reports why the backend could not discard the file", async () => {
    mockDiscardWorkspaceFile.mockResolvedValue({
      data: { result: { success: false, stdout: "", stderr: "", error_message: "The working copy is stale" } },
    });
    const onDiscarded = vi.fn();
    const { result } = renderDiscard();

    act(() => result.current.discardFile("src/app.py", onDiscarded));

    await waitFor(() => expect(result.current.errorMessage).toBe("The working copy is stale"));
    expect(onDiscarded).not.toHaveBeenCalled();
    expect(mockGetWorkspaceDiff).not.toHaveBeenCalled();
  });

  it("reports a rejected request with the server's reason, and forgets it on reset", async () => {
    mockDiscardWorkspaceFile.mockRejectedValue(new HTTPException(404, `Workspace ${WORKSPACE_ID} not found`));
    const { result } = renderDiscard();

    act(() => result.current.discardFile("src/app.py", vi.fn()));

    await waitFor(() => expect(result.current.errorMessage).toBe(`Workspace ${WORKSPACE_ID} not found`));

    act(() => result.current.resetError());

    await waitFor(() => expect(result.current.errorMessage).toBeNull());
  });
});
