import { LlmModel } from "~/api";

type ModelCapabilities = {
  supportsFileAttachments: boolean;
  supportsFastMode: boolean;
};

const MODEL_CAPABILITIES: Partial<Record<LlmModel, ModelCapabilities>> = {
  [LlmModel.CLAUDE_4_7_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_7_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  // CLAUDE_4_OPUS / CLAUDE_4_OPUS_200K are the rolling current-generation Opus
  // ("Claude 5 Opus" — see modelConstants.ts). Newer Opus generations are
  // bound to these enum values by bumping the display label there, so the
  // capabilities below must be kept in sync with that label. Fast mode is
  // supported on Opus 5 (and pinned 4.8/4.7/4.6; SCU-1541, SCU-1841).
  [LlmModel.CLAUDE_4_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  // Pinned Opus 5 — fast mode supported.
  [LlmModel.CLAUDE_5_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_5_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  // Pinned Opus 4.8 — fast mode supported (SCU-1841), same as the rolling entry.
  [LlmModel.CLAUDE_4_8_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_8_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_6_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_6_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_SONNET]: {
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_4_SONNET_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_4_HAIKU]: {
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_FABLE_5]: {
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_FABLE_5_1]: {
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  // Test-only models. FAKE_CLAUDE supports fast mode so fast-mode tests using
  // the default test model work out of the box. FAKE_CLAUDE_2 does NOT support
  // fast mode so cross-model contamination tests can send on a fake, non-fast
  // model without calling a real LLM.
  [LlmModel.FAKE_CLAUDE]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.FAKE_CLAUDE_2]: {
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
};

const DEFAULT_CAPABILITIES: ModelCapabilities = {
  supportsFileAttachments: true,
  supportsFastMode: false,
};

export const getModelCapabilities = (model: LlmModel): ModelCapabilities => {
  return MODEL_CAPABILITIES[model] ?? DEFAULT_CAPABILITIES;
};
