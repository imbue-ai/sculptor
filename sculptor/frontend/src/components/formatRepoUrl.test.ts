import { describe, expect, it } from "vitest";

import { formatRepoUrl } from "./formatRepoUrl.ts";

describe("formatRepoUrl", () => {
  it("returns empty string for null/undefined/empty", () => {
    expect(formatRepoUrl(null)).toBe("");
    expect(formatRepoUrl(undefined)).toBe("");
    expect(formatRepoUrl("")).toBe("");
  });

  it("trims https github URLs to org/repo", () => {
    expect(formatRepoUrl("https://github.com/imbue-ai/sculptor")).toBe("imbue-ai/sculptor");
    expect(formatRepoUrl("https://github.com/imbue-ai/sculptor.git")).toBe("imbue-ai/sculptor");
  });

  it("trims http URLs to path", () => {
    expect(formatRepoUrl("http://git.example.com/team/project.git")).toBe("team/project");
  });

  it("trims SSH-style git URLs to org/repo", () => {
    expect(formatRepoUrl("git@github.com:imbue-ai/sculptor.git")).toBe("imbue-ai/sculptor");
    expect(formatRepoUrl("git@git.example.com:team/project")).toBe("team/project");
  });

  it("trims ssh:// URLs to path", () => {
    expect(formatRepoUrl("ssh://git@github.com/imbue-ai/sculptor.git")).toBe("imbue-ai/sculptor");
  });

  it("trims file:// URLs to last two path segments", () => {
    expect(formatRepoUrl("file:///Users/me/code/sculptor")).toBe("code/sculptor");
    expect(formatRepoUrl("file:///srv/repos/sculptor")).toBe("repos/sculptor");
  });

  it("trims bare absolute paths to last two segments", () => {
    expect(formatRepoUrl("/Users/me/code/sculptor")).toBe("code/sculptor");
    expect(formatRepoUrl("~/code/notes")).toBe("code/notes");
  });

  it("returns single-segment paths as-is", () => {
    expect(formatRepoUrl("file:///root")).toBe("root");
    expect(formatRepoUrl("/root")).toBe("root");
  });

  it("returns unrecognised input unchanged", () => {
    expect(formatRepoUrl("not-a-url")).toBe("not-a-url");
  });
});
