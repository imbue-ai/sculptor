import { LlmModel } from "~/api";

type ModelCapabilities = {
  supportsSystemPrompt: boolean;
  supportsFileAttachments: boolean;
  supportsFastMode: boolean;
};

const MODEL_CAPABILITIES: Partial<Record<LlmModel, ModelCapabilities>> = {
  [LlmModel.CLAUDE_4_7_OPUS]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_7_OPUS_200K]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  // CLAUDE_4_OPUS / CLAUDE_4_OPUS_200K are the current-generation Opus
  // ("Claude 4.8 Opus" — see modelConstants.ts). Newer Opus generations are
  // bound to these enum values by bumping the display label there, so the
  // capabilities below must be kept in sync with that label. Fast mode is
  // supported, matching Opus 4.7 and 4.6 (SCU-1541).
  [LlmModel.CLAUDE_4_OPUS]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_OPUS_200K]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_6_OPUS]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_6_OPUS_200K]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_SONNET]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_4_SONNET_200K]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_4_HAIKU]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  [LlmModel.CLAUDE_FABLE_5]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
  // Test-only models. FAKE_CLAUDE supports fast mode so fast-mode tests using
  // the default test model work out of the box. FAKE_CLAUDE_2 does NOT support
  // fast mode so cross-model contamination tests can send on a fake, non-fast
  // model without calling a real LLM.
  [LlmModel.FAKE_CLAUDE]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.FAKE_CLAUDE_2]: {
    supportsSystemPrompt: true,
    supportsFileAttachments: true,
    supportsFastMode: false,
  },
};

const DEFAULT_CAPABILITIES: ModelCapabilities = {
  supportsSystemPrompt: true,
  supportsFileAttachments: true,
  supportsFastMode: false,
};

export const getModelCapabilities = (model: LlmModel): ModelCapabilities => {
  return MODEL_CAPABILITIES[model] ?? DEFAULT_CAPABILITIES;
};
