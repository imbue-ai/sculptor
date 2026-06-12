import { QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { BUILTIN_SKILLS } from "~/common/builtinSkills";
import { queryClient } from "~/common/queryClient";

import { useSkills } from "./useSkills";

const { mockGetSkills } = vi.hoisted(() => ({ mockGetSkills: vi.fn() }));

vi.mock("~/api", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return { ...original, getSkills: mockGetSkills };
});

const wrapperFor = (workspaceID: string): (({ children }: { children: ReactNode }) => ReactElement) => {
  const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/ws/${workspaceID}`]}>
        <Routes>
          <Route path="/ws/:workspaceID" element={children as ReactElement} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
  Wrapper.displayName = "TestRouterWrapper";
  return Wrapper;
};

beforeEach(() => {
  vi.clearAllMocks();
  // TanStack Query's cache is a process-wide singleton; wipe it so each test
  // starts from a known empty state.
  queryClient.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("useSkills", () => {
  it("starts in a loading state with no skills", () => {
    // Never-resolving promise so we can observe the initial state.
    mockGetSkills.mockReturnValue(new Promise(() => {}));
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    expect(result.current.isLoading).toBe(true);
    expect(result.current.skills).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it("merges built-in skills with skills returned by the API and sorts alphabetically", async () => {
    mockGetSkills.mockResolvedValue({
      data: [
        { name: "zebra", description: "z desc", source: "custom", filePath: "/repo/zebra/SKILL.md" },
        { name: "alpha", description: "a desc", source: "custom", filePath: "/repo/alpha/SKILL.md" },
      ],
    });
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const names = result.current.skills.map((s) => s.name);
    // The list is alphabetically sorted across both sources.
    const expectedNames = [...BUILTIN_SKILLS.map((b) => b.name), "alpha", "zebra"].sort((a, b) => a.localeCompare(b));
    expect(names).toEqual(expectedNames);
  });

  it("maps API source 'plugin' to type 'sculptor' and 'custom' to type 'custom'", async () => {
    mockGetSkills.mockResolvedValue({
      data: [
        { name: "sculptor:fix", description: "from plugin", source: "plugin", filePath: "/p/fix/SKILL.md" },
        { name: "custom-fix", description: "from repo", source: "custom", filePath: "/r/fix/SKILL.md" },
      ],
    });
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const sculptor = result.current.skills.find((s) => s.name === "sculptor:fix");
    const custom = result.current.skills.find((s) => s.name === "custom-fix");
    expect(sculptor?.type).toBe("sculptor");
    expect(custom?.type).toBe("custom");
  });

  it("marks built-in skills with type 'builtin' and a null filePath", async () => {
    mockGetSkills.mockResolvedValue({ data: [] });
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const builtin = result.current.skills.find((s) => s.name === BUILTIN_SKILLS[0]?.name);
    expect(builtin).toBeDefined();
    expect(builtin?.type).toBe("builtin");
    expect(builtin?.filePath).toBeNull();
  });

  it("propagates filePath through verbatim from the API", async () => {
    mockGetSkills.mockResolvedValue({
      data: [{ name: "x", description: "d", source: "custom", filePath: "/repo/.claude/skills/x/SKILL.md" }],
    });
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.skills.find((s) => s.name === "x")?.filePath).toBe("/repo/.claude/skills/x/SKILL.md");
  });

  it("normalizes a missing filePath to null", async () => {
    // The backend may omit `filePath` if the skill has no on-disk source
    // (rare in practice — guards against undefined leaking into the type).
    mockGetSkills.mockResolvedValue({
      data: [{ name: "x", description: "d", source: "custom" }],
    });
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.skills.find((s) => s.name === "x")?.filePath).toBeNull();
  });

  it("sets error to a friendly message when the fetch rejects", async () => {
    mockGetSkills.mockRejectedValue(new Error("network is down"));
    const { result } = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.error).toBe("Failed to load skills");
    expect(result.current.skills).toEqual([]);
  });

  it("starts each workspace with an empty list while the fetch is in flight", async () => {
    // Workspace switches use a different TanStack Query key, so the new
    // workspace has no cached data — `apiSkills` is null and the wrapper
    // returns `[]` until the fetch resolves. The panel never shows the
    // previous workspace's entries.
    // First workspace: returns one skill.
    mockGetSkills.mockResolvedValueOnce({
      data: [{ name: "ws1-skill", description: "d", source: "custom", filePath: "/x" }],
    });
    const first = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-1") });
    await waitFor(() => expect(first.result.current.isLoading).toBe(false));
    expect(first.result.current.skills.some((s) => s.name === "ws1-skill")).toBe(true);

    // Second workspace: never-resolving fetch. The hook starts in a loading
    // state with no leaked entries from the first workspace.
    mockGetSkills.mockReturnValueOnce(new Promise(() => {}));
    const second = renderHook(() => useSkills(), { wrapper: wrapperFor("ws-2") });
    expect(second.result.current.skills).toEqual([]);
    expect(second.result.current.isLoading).toBe(true);
  });
});
