import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type * as api from "~/api";
import { queryClient } from "~/common/state/queryClient.ts";

import { useFileLines } from "./useFileLines.ts";

const { mockReadFile, mockReadFileAtRef } = vi.hoisted(() => ({
  mockReadFile: vi.fn(),
  mockReadFileAtRef: vi.fn(),
}));

vi.mock("~/api", async () => {
  const actual = await vi.importActual<typeof api>("~/api");
  return { ...actual, workspaceReadFile: mockReadFile, workspaceReadFileAtRef: mockReadFileAtRef };
});

const WORKSPACE_ID = "ws-file-lines";
const BASE_COMMIT_ID = "3333333333333333333333333333333333333333";

const renderFileLines = (baseCommitId: string | null): { result: { current: ReturnType<typeof useFileLines> } } => {
  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={queryClient}>
      <Provider store={createStore()}>{children}</Provider>
    </QueryClientProvider>
  );
  return renderHook(() => useFileLines(WORKSPACE_ID, "src/app.py", null, "M", baseCommitId), { wrapper });
};

beforeEach(() => {
  mockReadFile.mockResolvedValue({ data: { content: "new\n", encoding: "utf-8" } });
  mockReadFileAtRef.mockResolvedValue({ data: { content: "old\n", encoding: "utf-8" } });
});

afterEach(() => {
  vi.clearAllMocks();
  queryClient.clear();
});

describe("useFileLines", () => {
  it("reads the before-image at the base commit the backend named", async () => {
    const { result } = renderFileLines(BASE_COMMIT_ID);

    await waitFor(() => expect(result.current.oldLines).toEqual(["old\n"]));
    expect(result.current.newLines).toEqual(["new\n"]);
    expect(mockReadFileAtRef).toHaveBeenCalledWith(
      expect.objectContaining({ body: { path: "src/app.py", gitRef: BASE_COMMIT_ID } }),
    );
  });

  it("asks for no before-image when the diff has no single base", async () => {
    const { result } = renderFileLines(null);

    await waitFor(() => expect(result.current.newLines).toEqual(["new\n"]));
    expect(result.current.oldLines).toBeUndefined();
    expect(mockReadFileAtRef).not.toHaveBeenCalled();
  });
});
