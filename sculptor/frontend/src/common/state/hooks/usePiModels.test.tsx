import { QueryClientProvider } from "@tanstack/react-query";
import type { RenderHookResult } from "@testing-library/react";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { ModelOption } from "~/api";
import { queryClient } from "~/common/queryClient";

import { usePiModels } from "./usePiModels";

const { mockGetPiModels } = vi.hoisted(() => ({ mockGetPiModels: vi.fn() }));

vi.mock("~/api", async (importOriginal) => {
  const original = (await importOriginal()) as Record<string, unknown>;
  return { ...original, getPiModels: mockGetPiModels };
});

const Wrapper = ({ children }: { children: ReactNode }): ReactElement => (
  <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
);

const PI_MODEL: ModelOption = { provider: "anthropic", modelId: "claude-opus-4-8", displayName: "Claude Opus 4.8" };
const populatedCatalog = { data: { availableModels: [PI_MODEL], defaultModel: PI_MODEL } };

type PiModelsHookResult = ReturnType<typeof usePiModels>;

const renderPiModels = (): RenderHookResult<PiModelsHookResult, unknown> =>
  renderHook(() => usePiModels({ enabled: true }), { wrapper: Wrapper });

beforeEach(() => {
  vi.clearAllMocks();
  // TanStack Query's cache is a process-wide singleton; wipe it so each test
  // starts from a known empty state.
  queryClient.clear();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("usePiModels", () => {
  it("returns the fetched catalog with pi's default preselectable", async () => {
    mockGetPiModels.mockResolvedValue(populatedCatalog);
    const { result } = renderPiModels();

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.availableModels).toEqual([PI_MODEL]);
    expect(result.current.defaultModel).toEqual(PI_MODEL);
  });

  it("resolves an initial fetch failure to the empty catalog, not a stranded loading state", async () => {
    // Consumers key "still resolving" on `data === undefined`; an unreachable
    // backend must land them in the empty state (with its login CTA), not in a
    // loading state nothing ever advances.
    mockGetPiModels.mockRejectedValue(new Error("backend unreachable"));
    const { result } = renderPiModels();

    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data).toEqual({ availableModels: [], defaultModel: null });
    expect(result.current.availableModels).toEqual([]);
    expect(result.current.defaultModel).toBeNull();
    expect(result.current.isError).toBe(true);
  });

  it("keeps the last-known catalog when a refetch fails", async () => {
    // A transient blip during a focus-driven refetch must not swap a populated
    // picker for the empty state's "go authenticate" advice.
    mockGetPiModels.mockResolvedValue(populatedCatalog);
    const { result } = renderPiModels();
    await waitFor(() => expect(result.current.availableModels).toEqual([PI_MODEL]));

    mockGetPiModels.mockRejectedValue(new Error("backend unreachable"));
    result.current.refetch();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.availableModels).toEqual([PI_MODEL]);
    expect(result.current.defaultModel).toEqual(PI_MODEL);
  });
});
