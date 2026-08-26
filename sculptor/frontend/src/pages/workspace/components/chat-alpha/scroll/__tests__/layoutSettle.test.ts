import { describe, expect, it } from "vitest";

import { initialLayout, nextLayout } from "../layoutSettle.ts";

describe("nextLayout", () => {
  it("starts stable", () => {
    expect(initialLayout).toEqual({ kind: "stable" });
  });

  it("invalidated -> measuring with the task id", () => {
    expect(nextLayout(initialLayout, { kind: "invalidated", taskId: "t1" })).toEqual({
      kind: "measuring",
      sinceTaskId: "t1",
    });
  });

  it("converged -> stable while measuring", () => {
    const measuring = { kind: "measuring", sinceTaskId: "t1" } as const;
    expect(nextLayout(measuring, { kind: "converged" })).toEqual({ kind: "stable" });
  });

  it("converged while already stable is an identity no-op", () => {
    expect(nextLayout(initialLayout, { kind: "converged" })).toBe(initialLayout);
  });

  it("a second invalidation re-targets the task id", () => {
    const measuring = nextLayout(initialLayout, { kind: "invalidated", taskId: "t1" });
    expect(nextLayout(measuring, { kind: "invalidated", taskId: "t2" })).toEqual({
      kind: "measuring",
      sinceTaskId: "t2",
    });
  });
});
