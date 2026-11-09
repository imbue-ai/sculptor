import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { DependenciesStatus, DependencyInfo, JjBlocker } from "~/api";
import { dependenciesStatusAtom, isJjAvailableAtom, isPiAvailableAtom } from "~/common/state/atoms/dependenciesStatus";

const makeInfo = (overrides: Partial<DependencyInfo>): DependencyInfo => ({ installed: false, ...overrides });

const makeStatus = (pi: DependencyInfo): DependenciesStatus => ({
  git: makeInfo({ installed: true }),
  claude: makeInfo({ installed: true }),
  pi,
  gh: makeInfo({}),
  jj: makeInfo({}),
  jjReadiness: { blocker: "NOT_INSTALLED" },
  voiceModels: makeInfo({}),
});

describe("isPiAvailableAtom", () => {
  it("fails open while the dependencies status is still unknown", () => {
    const store = createStore();
    expect(store.get(isPiAvailableAtom)).toBe(true);
  });

  it("is available when a pi binary is installed and within the pinned range", () => {
    const store = createStore();
    store.set(dependenciesStatusAtom, makeStatus(makeInfo({ installed: true, isVersionInRange: true })));
    expect(store.get(isPiAvailableAtom)).toBe(true);
  });

  it("is unavailable when no pi binary is installed", () => {
    const store = createStore();
    store.set(dependenciesStatusAtom, makeStatus(makeInfo({ installed: false })));
    expect(store.get(isPiAvailableAtom)).toBe(false);
  });

  it("is unavailable when the resolved pi is outside the pinned range", () => {
    const store = createStore();
    store.set(
      dependenciesStatusAtom,
      makeStatus(makeInfo({ installed: true, version: "0.50.0", isVersionInRange: false })),
    );
    expect(store.get(isPiAvailableAtom)).toBe(false);
  });
});

describe("isJjAvailableAtom", () => {
  const makeStatusWithJjBlocker = (blocker: JjBlocker | null): DependenciesStatus => ({
    ...makeStatus(makeInfo({})),
    jjReadiness: { blocker },
  });

  it("fails closed while the dependencies status is still unknown", () => {
    const store = createStore();
    expect(store.get(isJjAvailableAtom)).toBe(false);
  });

  it("is available when the backend reports no blocker", () => {
    const store = createStore();
    store.set(dependenciesStatusAtom, makeStatusWithJjBlocker(null));
    expect(store.get(isJjAvailableAtom)).toBe(true);
  });

  it.each(["NOT_INSTALLED", "NOT_RUNNABLE", "UNSUPPORTED_VERSION", "NO_IDENTITY"] as const)(
    "is unavailable when the backend reports %s",
    (blocker) => {
      const store = createStore();
      store.set(dependenciesStatusAtom, makeStatusWithJjBlocker(blocker));
      expect(store.get(isJjAvailableAtom)).toBe(false);
    },
  );
});
