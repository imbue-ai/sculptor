import { describe, expect, it } from "vitest";

import { LlmModel } from "~/api";

import { getModelCapabilities } from "./modelCapabilities";
import { getModelLongName, getModelShortName, PRODUCTION_MODELS } from "./modelConstants";

describe("Opus 5.5", () => {
  it("is labelled by its pinned generation in both context sizes", () => {
    expect(getModelShortName(LlmModel.CLAUDE_5_5_OPUS)).toBe("Opus 5.5 (1M)");
    expect(getModelShortName(LlmModel.CLAUDE_5_5_OPUS_200K)).toBe("Opus 5.5");
    expect(getModelLongName(LlmModel.CLAUDE_5_5_OPUS)).toBe("Claude 5.5 Opus (1M)");
    expect(getModelLongName(LlmModel.CLAUDE_5_5_OPUS_200K)).toBe("Claude 5.5 Opus");
  });

  it("supports fast mode and file attachments", () => {
    for (const model of [LlmModel.CLAUDE_5_5_OPUS, LlmModel.CLAUDE_5_5_OPUS_200K]) {
      expect(getModelCapabilities(model)).toEqual({ supportsFastMode: true, supportsFileAttachments: true });
    }
  });

  it("leads the Opus block in the picker without displacing Fable", () => {
    const opusStart = PRODUCTION_MODELS.indexOf(LlmModel.CLAUDE_5_5_OPUS_200K);
    expect(opusStart).toBeGreaterThan(PRODUCTION_MODELS.indexOf(LlmModel.CLAUDE_FABLE_5));
    expect(PRODUCTION_MODELS.slice(opusStart, opusStart + 2)).toEqual([
      LlmModel.CLAUDE_5_5_OPUS_200K,
      LlmModel.CLAUDE_5_5_OPUS,
    ]);
    expect(PRODUCTION_MODELS.indexOf(LlmModel.CLAUDE_5_OPUS_200K)).toBeGreaterThan(opusStart);
  });
});

describe("retired models", () => {
  it("keeps Opus 4.7 out of the picker while leaving it selectable by a stored value", () => {
    expect(PRODUCTION_MODELS).not.toContain(LlmModel.CLAUDE_4_7_OPUS);
    expect(PRODUCTION_MODELS).not.toContain(LlmModel.CLAUDE_4_7_OPUS_200K);
    expect(getModelShortName(LlmModel.CLAUDE_4_7_OPUS_200K)).toBe("Opus 4.7");
  });
});
