import { describe, expect, it } from "vitest";

import { toPrBaseRefName, toRemoteRefName } from "./refNames.ts";

describe("toRemoteRefName", () => {
  it("names the branch on the pull-request remote", () => {
    expect(toRemoteRefName("main")).toBe("origin/main");
  });

  it("keeps every segment of a nested branch name", () => {
    expect(toRemoteRefName("feature/login")).toBe("origin/feature/login");
  });
});

describe("toPrBaseRefName", () => {
  it("drops the remote from a remote-tracking target", () => {
    expect(toPrBaseRefName("origin/main")).toBe("main");
  });

  it("keeps the rest of a nested remote branch", () => {
    expect(toPrBaseRefName("origin/feature/login")).toBe("feature/login");
  });

  it("leaves a target without a slash as it is", () => {
    expect(toPrBaseRefName("main")).toBe("main");
  });

  it("drops the first segment of a local target with a slash, as PR status does", () => {
    expect(toPrBaseRefName("feature/login")).toBe("login");
  });

  it("inverts toRemoteRefName", () => {
    expect(toPrBaseRefName(toRemoteRefName("release/2.0"))).toBe("release/2.0");
  });
});
