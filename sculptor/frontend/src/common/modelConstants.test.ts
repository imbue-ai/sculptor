import { describe, expect, it } from "vitest";

import { LlmModel } from "~/api";

import { getClaudeModelList, getModelLongName, getModelShortName, PRODUCTION_MODELS } from "./modelConstants";

describe("model display names", () => {
  it("returns the real Fake Claude labels when no override is set", () => {
    // Integration tests select these models from the picker by their literal
    // labels, so the unset-override path must stay byte-identical.
    expect(getModelShortName(LlmModel.FAKE_CLAUDE)).toBe("Fake Claude");
    expect(getModelLongName(LlmModel.FAKE_CLAUDE)).toBe("Fake Claude");
    expect(getModelShortName(LlmModel.FAKE_CLAUDE_2, null)).toBe("Fake Claude 2");
    expect(getModelLongName(LlmModel.FAKE_CLAUDE_2, null)).toBe("Fake Claude 2");
  });

  it("relabels only the testing models when an override is set", () => {
    expect(getModelShortName(LlmModel.FAKE_CLAUDE, "Fable")).toBe("Fable");
    expect(getModelLongName(LlmModel.FAKE_CLAUDE, "Fable")).toBe("Fable");
    expect(getModelShortName(LlmModel.FAKE_CLAUDE_2, "Fable")).toBe("Fable");
    expect(getModelLongName(LlmModel.FAKE_CLAUDE_2, "Fable")).toBe("Fable");
    // Production models keep their real names under an override.
    expect(getModelShortName(LlmModel.CLAUDE_4_OPUS_200K, "Fable")).toBe("Opus");
    expect(getModelLongName(LlmModel.CLAUDE_4_SONNET_200K, "Fable")).toBe("Claude 4.6 Sonnet");
  });
});

describe("getClaudeModelList", () => {
  it("appends the testing models only when integration testing is enabled", () => {
    expect(getClaudeModelList(false)).toEqual(PRODUCTION_MODELS);
    expect(getClaudeModelList(true)).toEqual([...PRODUCTION_MODELS, LlmModel.FAKE_CLAUDE, LlmModel.FAKE_CLAUDE_2]);
  });

  it("hides the testing models from the picker when a fake-model display name is set", () => {
    // The demo harness seeds its scripted agents out-of-band; the relabelled
    // models must not be user-selectable.
    expect(getClaudeModelList(true, "Fable")).toEqual(PRODUCTION_MODELS);
    expect(getClaudeModelList(false, "Fable")).toEqual(PRODUCTION_MODELS);
    // A null override behaves exactly like an absent one.
    expect(getClaudeModelList(true, null)).toContain(LlmModel.FAKE_CLAUDE);
  });
});
