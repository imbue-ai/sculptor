import { describe, expect, it } from "vitest";

import { HTTPException } from "~/common/Errors.ts";

import {
  normalizeQuery,
  remoteReposQueryKey,
  shouldKeepPreviousRemoteReposData,
  shouldRetryRemoteRepos,
} from "./useRemoteRepos.ts";

describe("normalizeQuery", () => {
  it("lowercases and trims so case + whitespace variants share a cache entry", () => {
    expect(normalizeQuery("Foo")).toBe("foo");
    expect(normalizeQuery("  foo  ")).toBe("foo");
    expect(normalizeQuery(" FOO\t")).toBe("foo");
  });

  it("returns empty string for whitespace-only input (the browse-mode key)", () => {
    expect(normalizeQuery("")).toBe("");
    expect(normalizeQuery("   ")).toBe("");
  });
});

describe("remoteReposQueryKey", () => {
  it("collapses case + whitespace variants of the same query onto one cache key", () => {
    const a = remoteReposQueryKey("github", "Foo", 5);
    const b = remoteReposQueryKey("github", "  foo  ", 5);
    const c = remoteReposQueryKey("github", "FOO", 5);
    expect(a).toEqual(b);
    expect(b).toEqual(c);
  });

  it("keeps different providers on separate keys", () => {
    expect(remoteReposQueryKey("github", "foo", 5)).not.toEqual(remoteReposQueryKey("gitlab", "foo", 5));
  });

  it("keeps different limits on separate keys (caller may want more rows)", () => {
    expect(remoteReposQueryKey("github", "foo", 5)).not.toEqual(remoteReposQueryKey("github", "foo", 50));
  });

  it("uses 'remoteRepos' as the top-level scope so cache invalidation by prefix is possible", () => {
    expect(remoteReposQueryKey("github", "", 5)[0]).toBe("remoteRepos");
  });
});

describe("shouldRetryRemoteRepos", () => {
  it("does not retry on HTTPException(412) — the combobox surfaces NotConfiguredSection instead", () => {
    const notConfigured = new HTTPException(412, "gh CLI not authenticated");
    expect(shouldRetryRemoteRepos(0, notConfigured)).toBe(false);
  });

  it("retries other HTTPExceptions once and gives up after", () => {
    const fiveHundred = new HTTPException(500, "server error");
    expect(shouldRetryRemoteRepos(0, fiveHundred)).toBe(true);
    expect(shouldRetryRemoteRepos(1, fiveHundred)).toBe(false);
  });

  it("retries non-HTTPException errors (e.g. network failures) once", () => {
    const networkError = new TypeError("Failed to fetch");
    expect(shouldRetryRemoteRepos(0, networkError)).toBe(true);
    expect(shouldRetryRemoteRepos(1, networkError)).toBe(false);
  });
});

describe("shouldKeepPreviousRemoteReposData", () => {
  it("carries previous results forward when query changes within the same provider", () => {
    // Previous query was github + "foo"; new query is github + "fo" — same provider.
    expect(shouldKeepPreviousRemoteReposData("github", ["remoteRepos", "github", "foo", 5])).toBe(true);
  });

  it("clears placeholder data when the provider changes so the wrong provider's repos don't flash", () => {
    // Previous query was github + "foo"; new query is gitlab — wipe.
    expect(shouldKeepPreviousRemoteReposData("gitlab", ["remoteRepos", "github", "foo", 5])).toBe(false);
  });

  it("clears when there's no previous query (first mount)", () => {
    expect(shouldKeepPreviousRemoteReposData("github", undefined)).toBe(false);
  });
});
