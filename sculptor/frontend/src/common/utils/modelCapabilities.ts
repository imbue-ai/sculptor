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
  // The rolling "latest Opus" alias resolves through the managed Claude CLI's own
  // `opus` alias, so bumping CLAUDE_VERSION_RANGE can move it onto a new generation
  // without this file changing. Re-check the new CLI's alias target when bumping:
  // these capabilities are a claim about whichever model it resolves to.
  [LlmModel.CLAUDE_4_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_4_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_5_5_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_5_5_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_5_OPUS]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
  [LlmModel.CLAUDE_5_OPUS_200K]: {
    supportsFileAttachments: true,
    supportsFastMode: true,
  },
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
