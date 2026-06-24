import { describe, expect, it } from "vitest";

import { curateModels, modelOptionFromPi } from "~/harness/pi/models";

describe("modelOptionFromPi", () => {
  it("maps a pi model dict, defaulting provider and name", () => {
    expect(
      modelOptionFromPi({
        id: "claude-opus-4-8",
        name: "Opus",
        provider: "anthropic",
      }),
    ).toEqual({
      provider: "anthropic",
      model_id: "claude-opus-4-8",
      display_name: "Opus",
    });
    expect(modelOptionFromPi({ id: "m1" })).toEqual({
      provider: "anthropic",
      model_id: "m1",
      display_name: "m1",
    });
    expect(modelOptionFromPi({})).toBeNull();
  });
});

describe("curateModels", () => {
  const opt = (id: string): ReturnType<typeof modelOptionFromPi> =>
    modelOptionFromPi({ id });

  it("drops blacklisted + dated-pin ids and sorts newest-first", () => {
    const models = [
      opt("claude-opus-4-1"),
      opt("claude-opus-4-1-20250805"),
      opt("claude-3-opus-latest"),
      opt("claude-sonnet-4-6"),
    ].filter((m): m is NonNullable<typeof m> => m !== null);
    const curated = curateModels(models, null);
    expect(curated.map((m) => m.model_id)).toEqual([
      "claude-sonnet-4-6",
      "claude-opus-4-1",
    ]);
  });

  it("always keeps the current model even if a rule would drop it", () => {
    const current = opt("claude-3-opus-latest");
    const curated = curateModels([], current);
    expect(curated.map((m) => m.model_id)).toEqual(["claude-3-opus-latest"]);
  });
});
