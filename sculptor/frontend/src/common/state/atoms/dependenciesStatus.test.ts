import { createStore } from "jotai";
import { describe, expect, it } from "vitest";

import type { DependenciesStatus, DependencyInfo, JjReadiness } from "~/api";
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
  const makeStatusWithJjReadiness = (jjReadiness: JjReadiness): DependenciesStatus => ({
    ...makeStatus(makeInfo({})),
    jjReadiness,
  });

  const blockedReadinesses: ReadonlyArray<JjReadiness> = [
    { blocker: "NOT_INSTALLED" },
    { blocker: "NOT_RUNNABLE", error: "Config error: Configuration cannot be parsed as TOML document" },
    { blocker: "UNSUPPORTED_VERSION", path: "/usr/bin/jj", version: "0.28.2" },
    { blocker: "NO_IDENTITY", suggestedIdentity: { name: "", email: "" } },
  ];

  it("fails closed while the dependencies status is still unknown", () => {
    const store = createStore();
    expect(store.get(isJjAvailableAtom)).toBe(false);
  });

  it("is available when the backend reports no blocker", () => {
    const store = createStore();
    store.set(
      dependenciesStatusAtom,
      makeStatusWithJjReadiness({ blocker: null, identity: { name: "Ada Lovelace", email: "ada@example.com" } }),
    );
    expect(store.get(isJjAvailableAtom)).toBe(true);
  });

  it.each(blockedReadinesses)("is unavailable when the backend reports $blocker", (readiness) => {
    const store = createStore();
    store.set(dependenciesStatusAtom, makeStatusWithJjReadiness(readiness));
    expect(store.get(isJjAvailableAtom)).toBe(false);
  });
});
