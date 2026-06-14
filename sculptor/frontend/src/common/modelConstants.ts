import { LlmModel } from "~/api";

const modelNames: Partial<Record<LlmModel, { short: string; long: string }>> = {
  [LlmModel.CLAUDE_4_OPUS]: { short: "Opus (1M)", long: "Claude 4.8 Opus (1M)" },
  [LlmModel.CLAUDE_4_OPUS_200K]: { short: "Opus", long: "Claude 4.8 Opus" },
  [LlmModel.CLAUDE_4_7_OPUS]: { short: "Opus 4.7 (1M)", long: "Claude 4.7 Opus (1M)" },
  [LlmModel.CLAUDE_4_7_OPUS_200K]: { short: "Opus 4.7", long: "Claude 4.7 Opus" },
  [LlmModel.CLAUDE_4_6_OPUS]: { short: "Opus 4.6 (1M)", long: "Claude 4.6 Opus (1M)" },
  [LlmModel.CLAUDE_4_6_OPUS_200K]: { short: "Opus 4.6", long: "Claude 4.6 Opus" },
  [LlmModel.CLAUDE_4_SONNET]: { short: "Sonnet (1M)", long: "Claude 4.6 Sonnet (1M)" },
  [LlmModel.CLAUDE_4_SONNET_200K]: { short: "Sonnet", long: "Claude 4.6 Sonnet" },
  [LlmModel.CLAUDE_4_HAIKU]: { short: "Haiku", long: "Claude 4.5 Haiku" },
  [LlmModel.CLAUDE_FABLE_5]: { short: "Fable", long: "Fable" },
  [LlmModel.FAKE_CLAUDE]: { short: "Fake Claude", long: "Fake Claude" },
  [LlmModel.FAKE_CLAUDE_2]: { short: "Fake Claude 2", long: "Fake Claude 2" },
} as const;

export const getModelShortName = (model: LlmModel): string => modelNames[model]?.short || "Unknown";
export const getModelLongName = (model: LlmModel): string => modelNames[model]?.long || "Unknown";

/** Models offered in production model pickers (desktop selector + mobile `+` menu). */
export const PRODUCTION_MODELS: ReadonlyArray<LlmModel> = [
  LlmModel.CLAUDE_FABLE_5,
  LlmModel.CLAUDE_4_OPUS_200K,
  LlmModel.CLAUDE_4_OPUS,
  LlmModel.CLAUDE_4_7_OPUS_200K,
  LlmModel.CLAUDE_4_7_OPUS,
  LlmModel.CLAUDE_4_6_OPUS_200K,
  LlmModel.CLAUDE_4_6_OPUS,
  LlmModel.CLAUDE_4_SONNET_200K,
  LlmModel.CLAUDE_4_SONNET,
  LlmModel.CLAUDE_4_HAIKU,
];
