import { describe, expect, it } from "vitest";

import { LlmModel } from "~/api";

import { getModelCapabilities } from "./modelCapabilities";
import { DEFAULT_LLM_MODEL, getModelLongName, getModelShortName, PRODUCTION_MODELS } from "./modelConstants";

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

describe("Sonnet 5.5 and Haiku 5.5", () => {
  it("are labelled by their pinned generation, with no 1M variant", () => {
    expect(getModelShortName(LlmModel.CLAUDE_5_5_SONNET)).toBe("Sonnet 5.5");
    expect(getModelLongName(LlmModel.CLAUDE_5_5_SONNET)).toBe("Claude 5.5 Sonnet");
    expect(getModelShortName(LlmModel.CLAUDE_5_5_HAIKU)).toBe("Haiku 5.5");
    expect(getModelLongName(LlmModel.CLAUDE_5_5_HAIKU)).toBe("Claude 5.5 Haiku");
  });

  it("support file attachments but not fast mode", () => {
    for (const model of [LlmModel.CLAUDE_5_5_SONNET, LlmModel.CLAUDE_5_5_HAIKU]) {
      expect(getModelCapabilities(model)).toEqual({ supportsFastMode: false, supportsFileAttachments: true });
    }
  });

  it("follow the Opus block in the picker, Sonnet before Haiku", () => {
    expect(PRODUCTION_MODELS.slice(-2)).toEqual([LlmModel.CLAUDE_5_5_SONNET, LlmModel.CLAUDE_5_5_HAIKU]);
  });
});

describe("retired models", () => {
  it("keeps Opus 4.7 out of the picker while leaving it selectable by a stored value", () => {
    expect(PRODUCTION_MODELS).not.toContain(LlmModel.CLAUDE_4_7_OPUS);
    expect(PRODUCTION_MODELS).not.toContain(LlmModel.CLAUDE_4_7_OPUS_200K);
    expect(getModelShortName(LlmModel.CLAUDE_4_7_OPUS_200K)).toBe("Opus 4.7");
  });

  it("keeps the rolling Sonnet and Haiku aliases out of the picker, labelled as rolling", () => {
    for (const model of [LlmModel.CLAUDE_4_SONNET, LlmModel.CLAUDE_4_SONNET_200K, LlmModel.CLAUDE_4_HAIKU]) {
      expect(PRODUCTION_MODELS).not.toContain(model);
      expect(getModelLongName(model)).toMatch(/\(latest/);
    }
  });
});

describe("DEFAULT_LLM_MODEL", () => {
  it("is a model the picker offers", () => {
    // A default the picker does not list is a selection the user cannot get back to
    // after switching away from it.
    expect(PRODUCTION_MODELS).toContain(DEFAULT_LLM_MODEL);
  });

  it("is a large-context variant", () => {
    // New agents get the 1M window; the 200K variants are opt-in from the picker.
    expect(getModelShortName(DEFAULT_LLM_MODEL)).toMatch(/\(1M\)$/);
  });

  it("supports the capabilities a default needs", () => {
    expect(getModelCapabilities(DEFAULT_LLM_MODEL)).toEqual({
      supportsFastMode: true,
      supportsFileAttachments: true,
    });
  });
});
