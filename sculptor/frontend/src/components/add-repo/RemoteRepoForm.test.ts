import { describe, expect, it } from "vitest";

import type { RemoteRepo } from "~/api";

import { computeSubmittable, deriveNameFromUrl } from "./remoteRepoFormHelpers.ts";

const sampleRepo: RemoteRepo = {
  fullName: "imbue-ai/sculptor",
  cloneUrl: "https://github.com/imbue-ai/sculptor.git",
  sshUrl: "git@github.com:imbue-ai/sculptor.git",
  isPrivate: false,
  pushedAt: "2026-01-15T10:30:00Z",
  description: null,
};

describe("deriveNameFromUrl", () => {
  it("returns the repo segment of an https URL", () => {
    expect(deriveNameFromUrl("https://github.com/owner/repo.git")).toBe("repo");
  });

  it("strips the .git suffix", () => {
    expect(deriveNameFromUrl("https://github.com/owner/repo")).toBe("repo");
  });

  it("returns the last segment of a nested group path", () => {
    expect(deriveNameFromUrl("https://github.com/group/sub/name.git")).toBe("name");
  });

  it("returns the repo segment of an ssh URL", () => {
    expect(deriveNameFromUrl("git@github.com:group/sub/name.git")).toBe("name");
  });

  it("returns empty string for empty input so the form stays not-ready", () => {
    expect(deriveNameFromUrl("")).toBe("");
    expect(deriveNameFromUrl("   ")).toBe("");
  });

  it("returns the trimmed input when there's no slash or colon to cut on", () => {
    expect(deriveNameFromUrl("plain-name")).toBe("plain-name");
  });
});

describe("computeSubmittable", () => {
  const baseSearchInputs = {
    provider: "github" as const,
    view: "search" as const,
    selectedRepo: sampleRepo,
    urlInput: "",
    name: "sculptor",
    effectiveTargetDir: "/home/user/code",
  };

  it("returns ready=true with full payload in search view when a repo is selected", () => {
    const result = computeSubmittable(baseSearchInputs);
    expect(result.ready).toBe(true);
    expect(result.payload).toEqual({
      provider: "github",
      url: "https://github.com/imbue-ai/sculptor.git",
      targetDir: "/home/user/code",
      name: "sculptor",
      fullName: "imbue-ai/sculptor",
    });
  });

  it("forwards the selectedRepo.fullName as the slug in search view", () => {
    const result = computeSubmittable(baseSearchInputs);
    expect(result.payload?.fullName).toBe("imbue-ai/sculptor");
  });

  it("returns ready=false when no repo is selected in search view", () => {
    expect(computeSubmittable({ ...baseSearchInputs, selectedRepo: undefined }).ready).toBe(false);
  });

  it("returns ready=false when name is blank in search view", () => {
    expect(computeSubmittable({ ...baseSearchInputs, name: "  " }).ready).toBe(false);
  });

  it("returns ready=false when targetDir is blank in search view", () => {
    expect(computeSubmittable({ ...baseSearchInputs, effectiveTargetDir: "" }).ready).toBe(false);
  });

  const baseUrlInputs = {
    provider: "github" as const,
    view: "url" as const,
    selectedRepo: undefined,
    urlInput: "https://github.com/group/repo.git",
    name: "repo",
    effectiveTargetDir: "/home/user/code/github",
  };

  it("returns ready=true in URL view with no selectedRepo", () => {
    const result = computeSubmittable(baseUrlInputs);
    expect(result.ready).toBe(true);
    expect(result.payload?.url).toBe("https://github.com/group/repo.git");
  });

  it("omits fullName in URL view (the manual-URL flow has no slug)", () => {
    const result = computeSubmittable(baseUrlInputs);
    expect(result.payload?.fullName).toBeUndefined();
  });

  it("trims surrounding whitespace from urlInput and name before submitting", () => {
    const result = computeSubmittable({
      ...baseUrlInputs,
      urlInput: "  https://github.com/group/repo.git  ",
      name: "  repo  ",
    });
    expect(result.payload?.url).toBe("https://github.com/group/repo.git");
    expect(result.payload?.name).toBe("repo");
  });

  it("returns ready=false when urlInput is blank in URL view", () => {
    expect(computeSubmittable({ ...baseUrlInputs, urlInput: "   " }).ready).toBe(false);
  });
});
