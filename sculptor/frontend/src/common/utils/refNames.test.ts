import { describe, expect, it } from "vitest";

import { toBareRefName, toRemoteRefName } from "./refNames.ts";

describe("toRemoteRefName", () => {
  it("names the branch on the pull-request remote", () => {
    expect(toRemoteRefName("main")).toBe("origin/main");
  });

  it("keeps every segment of a nested branch name", () => {
    expect(toRemoteRefName("feature/login")).toBe("origin/feature/login");
  });
});

describe("toBareRefName", () => {
  it("strips the pull-request remote", () => {
    expect(toBareRefName("origin/main")).toBe("main");
  });

  it("strips only the remote from a nested remote branch", () => {
    expect(toBareRefName("origin/feature/login")).toBe("feature/login");
  });

  it("keeps a local branch whose name contains a slash", () => {
    expect(toBareRefName("feature/login")).toBe("feature/login");
  });

  it("keeps a local branch without a slash", () => {
    expect(toBareRefName("main")).toBe("main");
  });

  it("inverts toRemoteRefName", () => {
    expect(toBareRefName(toRemoteRefName("release/2.0"))).toBe("release/2.0");
  });
});
