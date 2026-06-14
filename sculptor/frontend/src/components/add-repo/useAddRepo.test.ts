import { describe, expect, it } from "vitest";

import type { AddRepoPhase } from "./useAddRepo.tsx";
import { deriveDisplayName, deriveWebUrl, initialPhase, phaseReducer } from "./useAddRepo.tsx";

describe("deriveDisplayName", () => {
  it("extracts owner/repo from an https URL with .git suffix", () => {
    expect(deriveDisplayName("https://github.com/imbue-ai/sculptor.git", "fallback")).toBe("imbue-ai/sculptor");
  });

  it("extracts owner/repo from an https URL without .git suffix", () => {
    expect(deriveDisplayName("https://github.com/imbue-ai/sculptor", "fallback")).toBe("imbue-ai/sculptor");
  });

  it("extracts owner/repo from an ssh URL", () => {
    expect(deriveDisplayName("git@github.com:imbue-ai/sculptor.git", "fallback")).toBe("imbue-ai/sculptor");
  });

  it("extracts group/sub/repo from a nested GitLab path", () => {
    expect(deriveDisplayName("https://gitlab.com/group/sub/project.git", "fallback")).toBe("group/sub/project");
  });

  it("trims whitespace before parsing", () => {
    expect(deriveDisplayName("  https://github.com/owner/repo  ", "fallback")).toBe("owner/repo");
  });

  it("falls back to the provided name when the URL doesn't match either shape", () => {
    expect(deriveDisplayName("not-a-url-at-all", "my-fallback")).toBe("my-fallback");
  });

  it("falls back when the URL is empty", () => {
    expect(deriveDisplayName("", "my-fallback")).toBe("my-fallback");
  });
});

describe("deriveWebUrl", () => {
  it("rewrites ssh URLs to https without the .git suffix", () => {
    expect(deriveWebUrl("git@github.com:owner/repo.git")).toBe("https://github.com/owner/repo");
  });

  it("rewrites ssh URLs to https for self-hosted hosts", () => {
    expect(deriveWebUrl("git@gitlab.internal:team/svc.git")).toBe("https://gitlab.internal/team/svc");
  });

  it("passes https URLs through, stripping the .git suffix", () => {
    expect(deriveWebUrl("https://github.com/owner/repo.git")).toBe("https://github.com/owner/repo");
  });

  it("passes http URLs through too", () => {
    expect(deriveWebUrl("http://example.com/owner/repo")).toBe("http://example.com/owner/repo");
  });

  it("returns undefined for unrecognized shapes so the title falls back to plain text", () => {
    expect(deriveWebUrl("not-a-url")).toBeUndefined();
    expect(deriveWebUrl("")).toBeUndefined();
    // Filesystem path — not a URL the link in the progress card can navigate to.
    expect(deriveWebUrl("/home/user/projects/repo")).toBeUndefined();
  });
});

describe("phaseReducer", () => {
  const repoPath = "/home/user/code/repo";

  it("starts in the form phase", () => {
    expect(initialPhase).toEqual({ type: "form" });
  });

  it("SUBMIT_STARTED transitions to validating", () => {
    expect(phaseReducer(initialPhase, { type: "SUBMIT_STARTED", repoPath })).toEqual({
      type: "validating",
      repoPath,
    });
  });

  it("START_CLONING carries displayName and webUrl into the cloning phase", () => {
    const result = phaseReducer(initialPhase, {
      type: "START_CLONING",
      repoPath,
      displayName: "owner/repo",
      webUrl: "https://github.com/owner/repo",
    });
    expect(result).toEqual({
      type: "cloning",
      repoPath,
      displayName: "owner/repo",
      webUrl: "https://github.com/owner/repo",
    });
  });

  it("START_CLONING leaves webUrl undefined when none was derived", () => {
    const result = phaseReducer(initialPhase, {
      type: "START_CLONING",
      repoPath,
      displayName: "owner/repo",
    });
    expect(result).toEqual({
      type: "cloning",
      repoPath,
      displayName: "owner/repo",
      webUrl: undefined,
    });
  });

  it("START_INITIALIZING transitions to initializing", () => {
    expect(phaseReducer({ type: "not-git-repo", repoPath }, { type: "START_INITIALIZING", repoPath })).toEqual({
      type: "initializing",
      repoPath,
    });
  });

  it("BACK_TO_FORM clears any prior phase", () => {
    const prior: AddRepoPhase = { type: "error", repoPath, errorMessage: "boom" };
    expect(phaseReducer(prior, { type: "BACK_TO_FORM" })).toEqual({ type: "form" });
  });

  it("NOT_GIT_REPO captures the path so the validation view can offer init", () => {
    expect(phaseReducer(initialPhase, { type: "NOT_GIT_REPO", repoPath })).toEqual({
      type: "not-git-repo",
      repoPath,
    });
  });

  it("EMPTY_REPO captures the path so the validation view can offer initial commit", () => {
    expect(phaseReducer(initialPhase, { type: "EMPTY_REPO", repoPath })).toEqual({
      type: "empty-repo",
      repoPath,
    });
  });

  it("ERROR carries the message through", () => {
    expect(phaseReducer(initialPhase, { type: "ERROR", repoPath, errorMessage: "Disk full" })).toEqual({
      type: "error",
      repoPath,
      errorMessage: "Disk full",
    });
  });

  it("CLONE_FAILED keeps localPathSuggestion so the 409 'Add as local folder' CTA can fire", () => {
    expect(
      phaseReducer(initialPhase, {
        type: "CLONE_FAILED",
        repoPath,
        errorMessage: "This folder already exists.",
        localPathSuggestion: repoPath,
      }),
    ).toEqual({
      type: "clone-failed",
      repoPath,
      errorMessage: "This folder already exists.",
      localPathSuggestion: repoPath,
    });
  });

  it("CLONE_FAILED omits localPathSuggestion when none was passed (412 / non-conflict)", () => {
    expect(
      phaseReducer(initialPhase, {
        type: "CLONE_FAILED",
        repoPath,
        errorMessage: "gh CLI not authenticated",
      }),
    ).toEqual({
      type: "clone-failed",
      repoPath,
      errorMessage: "gh CLI not authenticated",
      localPathSuggestion: undefined,
    });
  });
});
