import { describe, expect, it } from "vitest";

import { SCULPTOR_QUERY_KEY_PREFIX } from "~/common/state/queryClient.ts";
import { HTTPException } from "~/common/utils/errors.ts";

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

  it("keeps different limits on separate keys (caller may want more rows)", () => {
    expect(remoteReposQueryKey("github", "foo", 5)).not.toEqual(remoteReposQueryKey("github", "foo", 50));
  });

  it("nests under the reserved sculptor prefix so plugin caches can't collide", () => {
    const key = remoteReposQueryKey("github", "", 5);
    expect(key[0]).toBe(SCULPTOR_QUERY_KEY_PREFIX);
    expect(key[1]).toBe("remoteRepos");
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
    // The provider sits at index 2 of the key (after the prefix and "remoteRepos").
    expect(
      shouldKeepPreviousRemoteReposData("github", [SCULPTOR_QUERY_KEY_PREFIX, "remoteRepos", "github", "foo", 5]),
    ).toBe(true);
  });

  it("clears placeholder data when the previous key is for a different scope", () => {
    // A previous key whose provider slot doesn't match the new provider must
    // not carry forward — otherwise the wrong scope's repos would flash.
    expect(
      shouldKeepPreviousRemoteReposData("github", [SCULPTOR_QUERY_KEY_PREFIX, "remoteRepos", "other", "foo", 5]),
    ).toBe(false);
  });

  it("clears when there's no previous query (first mount)", () => {
    expect(shouldKeepPreviousRemoteReposData("github", undefined)).toBe(false);
  });
});
