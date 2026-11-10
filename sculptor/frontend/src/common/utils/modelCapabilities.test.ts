import { describe, expect, it } from "vitest";

import { LlmModel } from "~/api";

import { getModelCapabilities } from "./modelCapabilities";

// The backend launches fast mode only on these models (FAST_MODE_MODELS in
// sculptor/agents/default/constants.py), so the toggle must appear on exactly the same set.
const FAST_MODE_MODELS: ReadonlyArray<LlmModel> = [
  LlmModel.CLAUDE_4_OPUS,
  LlmModel.CLAUDE_4_OPUS_200K,
  LlmModel.CLAUDE_5_5_OPUS,
  LlmModel.CLAUDE_5_5_OPUS_200K,
  LlmModel.CLAUDE_5_OPUS,
  LlmModel.CLAUDE_5_OPUS_200K,
  LlmModel.CLAUDE_FABLE_5_2,
  LlmModel.FAKE_CLAUDE,
];

describe("getModelCapabilities", () => {
  it.each(Object.values(LlmModel))("offers fast mode on %s only where the backend launches it", (model) => {
    expect(getModelCapabilities(model).supportsFastMode).toBe(FAST_MODE_MODELS.includes(model));
  });
});
