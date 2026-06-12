import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { RepoInfo } from "../../../api";
import { repoInfoAtomFamily } from "../atoms/repoInfo.ts";
import { useRepoInfo } from "./useRepoInfo";

const PROJECT_ID = "prj_test123";

const MOCK_REPO_INFO: RepoInfo = {
  repoPath: "/tmp/test-repo",
  currentBranch: "main",
  recentBranches: ["main", "develop"],
  projectId: PROJECT_ID,
};

// Mock the API SDK functions used by useRepoInfo.
const { mockGetRepoInfo, mockGetCurrentBranch } = vi.hoisted(() => ({
  mockGetRepoInfo: vi.fn(),
  mockGetCurrentBranch: vi.fn(),
}));

vi.mock("../../../api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getRepoInfo: mockGetRepoInfo,
    getCurrentBranch: mockGetCurrentBranch,
  };
});

describe("useRepoInfo", () => {
  let store: ReturnType<typeof createStore>;

  const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <Provider store={store}>{children}</Provider>
  );

  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it("fetchCurrentBranch does not overwrite null repoInfo with partial data", async () => {
    // Simulate the scenario: repoInfo atom is null (fetchRepoInfo failed),
    // then fetchCurrentBranch succeeds.  Before the fix, this would create
    // a partial RepoInfo with empty recentBranches, permanently disabling
    // the "Create Workspace" button and preventing retry logic from firing.
    mockGetCurrentBranch.mockResolvedValue({
      data: { currentBranch: "testing" },
    });

    const { result } = renderHook(() => useRepoInfo(PROJECT_ID), { wrapper });

    // repoInfo starts as null
    expect(result.current.repoInfo).toBeNull();

    // Call fetchCurrentBranch while repoInfo is null
    await act(async () => {
      await result.current.fetchCurrentBranch();
    });

    // repoInfo should remain null — fetchCurrentBranch must not create
    // a partial RepoInfo that would prevent the retry mechanism.
    expect(result.current.repoInfo).toBeNull();
  });

  it("fetchCurrentBranch updates branch when repoInfo already exists", async () => {
    // Pre-populate the atom with full repo info
    store.set(repoInfoAtomFamily(PROJECT_ID), MOCK_REPO_INFO);

    mockGetCurrentBranch.mockResolvedValue({
      data: { currentBranch: "feature-branch" },
    });

    const { result } = renderHook(() => useRepoInfo(PROJECT_ID), { wrapper });

    expect(result.current.repoInfo).toEqual(MOCK_REPO_INFO);

    await act(async () => {
      await result.current.fetchCurrentBranch();
    });

    // Branch should be updated, but branches list preserved
    expect(result.current.repoInfo?.currentBranch).toBe("feature-branch");
    expect(result.current.repoInfo?.recentBranches).toEqual(["main", "develop"]);
    expect(result.current.repoInfo?.repoPath).toBe("/tmp/test-repo");
  });

  it("retries when repoInfo is null after fetchRepoInfo failure", async () => {
    vi.useFakeTimers();

    // First call fails, second succeeds
    mockGetRepoInfo.mockRejectedValueOnce(new Error("disk I/O error")).mockResolvedValueOnce({ data: MOCK_REPO_INFO });

    const { result } = renderHook(() => useRepoInfo(PROJECT_ID), { wrapper });

    // Trigger the initial failed fetch
    await act(async () => {
      await result.current.fetchRepoInfo();
    });

    // repoInfo should be null after failure (catch block clears it)
    expect(result.current.repoInfo).toBeNull();

    // Advance past the 3-second retry interval so the effect fires
    await act(async () => {
      vi.advanceTimersByTime(3_100);
    });

    // The retry effect should have called fetchRepoInfo again
    expect(result.current.repoInfo).toEqual(MOCK_REPO_INFO);

    vi.useRealTimers();
  });

  it("keeps retrying when consecutive failures leave the atom null", async () => {
    // Regression: previously the retry useEffect only fired once because the
    // catch block's store.set(null) was a no-op when the atom was already null,
    // so Jotai didn't notify subscribers and the effect didn't re-run.
    vi.useFakeTimers();

    // Fail twice, then succeed on the third attempt.
    mockGetRepoInfo
      .mockRejectedValueOnce(new Error("disk I/O error 1"))
      .mockRejectedValueOnce(new Error("disk I/O error 2"))
      .mockResolvedValueOnce({ data: MOCK_REPO_INFO });

    const { result } = renderHook(() => useRepoInfo(PROJECT_ID), { wrapper });

    // Trigger the initial failed fetch (attempt 1).
    await act(async () => {
      await result.current.fetchRepoInfo();
    });
    expect(result.current.repoInfo).toBeNull();
    expect(mockGetRepoInfo).toHaveBeenCalledTimes(1);

    // Advance past the retry interval — attempt 2 (also fails).
    await act(async () => {
      vi.advanceTimersByTime(3_100);
    });
    expect(result.current.repoInfo).toBeNull();
    expect(mockGetRepoInfo).toHaveBeenCalledTimes(2);

    // Advance again — attempt 3 should fire and succeed.
    await act(async () => {
      vi.advanceTimersByTime(3_100);
    });
    expect(mockGetRepoInfo).toHaveBeenCalledTimes(3);
    expect(result.current.repoInfo).toEqual(MOCK_REPO_INFO);

    vi.useRealTimers();
  });
});
