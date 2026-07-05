import { describe, expect, it } from "vitest";

import { initialLayout, nextLayout } from "../layoutSettle.ts";

describe("nextLayout", () => {
  it("starts stable", () => {
    expect(initialLayout).toEqual({ kind: "stable" });
  });

  it("invalidated -> measuring with the agent id", () => {
    expect(nextLayout(initialLayout, { kind: "invalidated", agentId: "t1" })).toEqual({
      kind: "measuring",
      sinceAgentId: "t1",
    });
  });

  it("converged -> stable while measuring", () => {
    const measuring = { kind: "measuring", sinceAgentId: "t1" } as const;
    expect(nextLayout(measuring, { kind: "converged" })).toEqual({ kind: "stable" });
  });

  it("converged while already stable is an identity no-op", () => {
    expect(nextLayout(initialLayout, { kind: "converged" })).toBe(initialLayout);
  });

  it("a second invalidation re-targets the agent id", () => {
    const measuring = nextLayout(initialLayout, { kind: "invalidated", agentId: "t1" });
    expect(nextLayout(measuring, { kind: "invalidated", agentId: "t2" })).toEqual({
      kind: "measuring",
      sinceAgentId: "t2",
    });
  });
});
