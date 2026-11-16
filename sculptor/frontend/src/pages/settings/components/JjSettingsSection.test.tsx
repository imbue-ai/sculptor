import { act, cleanup, fireEvent, screen } from "@testing-library/react";
import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { DependenciesStatus, DependencyInfo, JjReadiness } from "~/api";
import { ElementIds } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { renderWithProviders } from "~/common/utils/renderWithProviders.tsx";

import { JjSettingsSection } from "./JjSettingsSection.tsx";

const { mockGetDependenciesStatus, mockSetJjIdentity } = vi.hoisted(() => ({
  mockGetDependenciesStatus: vi.fn(),
  mockSetJjIdentity: vi.fn(),
}));

vi.mock("~/api", async (importOriginal) => {
  const original = await importOriginal();
  return {
    ...(original as object),
    getDependenciesStatus: mockGetDependenciesStatus,
    setJjIdentity: mockSetJjIdentity,
  };
});

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (
  jjReadiness: JjReadiness,
  loginShellJj: DependenciesStatus["loginShellJj"] = null,
): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi: makeInfo({}),
  gh: makeInfo({}),
  jj: makeInfo({ installed: true, isVersionInRange: true, mode: "MANAGED", version: "0.46.0" }),
  jjReadiness,
  loginShellJj,
  voiceModels: makeInfo({}),
});

const IDENTITY = { name: "Ada Lovelace", email: "ada@example.com" };
const NO_IDENTITY = makeStatus({ blocker: "NO_IDENTITY", suggestedIdentity: IDENTITY });
const AVAILABLE = makeStatus({ blocker: null, identity: IDENTITY });
const NOT_INSTALLED = makeStatus({ blocker: "NOT_INSTALLED" });

type Deferred<T> = { promise: Promise<{ data: T }>; resolve: (value: T) => void };

const deferred = <T,>(): Deferred<T> => {
  let resolve: (value: T) => void = () => {};
  const promise = new Promise<{ data: T }>((settle) => {
    resolve = (value): void => settle({ data: value });
  });
  return { promise, resolve };
};

describe("JjSettingsSection", () => {
  let store: ReturnType<typeof createStore>;

  const renderSection = (): void => {
    renderWithProviders(<JjSettingsSection onSettingChange={vi.fn().mockResolvedValue(undefined)} />, { store });
  };

  beforeEach(() => {
    store = createStore();
    mockGetDependenciesStatus.mockResolvedValue({ data: NO_IDENTITY });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("asks the backend to re-check on open, and keeps a newer stream frame when the response lands after it", async () => {
    store.set(dependenciesStatusAtom, NO_IDENTITY);
    const recheck = deferred<DependenciesStatus>();
    mockGetDependenciesStatus.mockReturnValueOnce(recheck.promise);
    renderSection();

    act(() => {
      store.set(dependenciesStatusAtom, AVAILABLE);
    });
    await act(async () => {
      recheck.resolve(NO_IDENTITY);
    });

    expect(mockGetDependenciesStatus).toHaveBeenCalledWith({ meta: { skipWsAck: true } });
    expect(store.get(dependenciesStatusAtom)).toBe(AVAILABLE);
  });

  it("re-checks when the user asks, leaving the status to the stream", async () => {
    store.set(dependenciesStatusAtom, NO_IDENTITY);
    renderSection();
    await act(async () => {});

    mockGetDependenciesStatus.mockResolvedValue({ data: AVAILABLE });
    await act(async () => {
      fireEvent.click(screen.getByTestId(ElementIds.JJ_RECHECK_BUTTON));
    });

    expect(mockGetDependenciesStatus).toHaveBeenCalledTimes(2);
    expect(store.get(dependenciesStatusAtom)).toBe(NO_IDENTITY);
    expect(screen.getByTestId(ElementIds.JJ_RECHECK_BUTTON)).toBeEnabled();
  });

  it("shows the other jj the login shell runs, which blocks nothing, beside Sculptor's", async () => {
    const withHomebrewJj = makeStatus(
      { blocker: null, identity: IDENTITY },
      { path: "/opt/homebrew/bin/jj", version: "0.48.0", isVersionInRange: true },
    );
    store.set(dependenciesStatusAtom, withHomebrewJj);
    mockGetDependenciesStatus.mockResolvedValue({ data: withHomebrewJj });
    renderSection();
    await act(async () => {});

    expect(screen.getByText("jj in your terminal")).toBeInTheDocument();
    expect(screen.getByText("/opt/homebrew/bin/jj (jj 0.48.0)")).toBeInTheDocument();
  });

  it("shows no terminal jj when the login shell runs Sculptor's", async () => {
    store.set(dependenciesStatusAtom, AVAILABLE);
    mockGetDependenciesStatus.mockResolvedValue({ data: AVAILABLE });
    renderSection();
    await act(async () => {});

    expect(screen.queryByText("jj in your terminal")).not.toBeInTheDocument();
  });

  it("keeps a newer stream frame when the identity save responds after it", async () => {
    store.set(dependenciesStatusAtom, NO_IDENTITY);
    renderSection();
    await act(async () => {});
    const save = deferred<DependenciesStatus>();
    mockSetJjIdentity.mockReturnValueOnce(save.promise);

    fireEvent.click(screen.getByTestId(ElementIds.JJ_IDENTITY_SUBMIT));
    // The save published AVAILABLE, then jj went away before its response landed.
    act(() => {
      store.set(dependenciesStatusAtom, NOT_INSTALLED);
    });
    await act(async () => {
      save.resolve(AVAILABLE);
    });

    expect(mockSetJjIdentity).toHaveBeenCalledWith({ body: IDENTITY, meta: { skipWsAck: true } });
    expect(store.get(dependenciesStatusAtom)).toBe(NOT_INSTALLED);
  });
});
