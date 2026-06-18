import { LlmModel, type ModelOption } from "~/api";

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

const providerDisplayNames: Record<string, string> = {
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  deepseek: "DeepSeek",
  google: "Google",
  openai: "OpenAI",
  "amazon-bedrock": "Amazon Bedrock",
};

/**
 * The human-friendly label for a model provider, used as the group header in the
 * pi model switcher. Unknown providers fall back to a capitalized form of the
 * raw provider string.
 */
export const getProviderDisplayName = (provider: string): string =>
  providerDisplayNames[provider] ?? `${provider.charAt(0).toUpperCase()}${provider.slice(1)}`;

/**
 * Route a model-switcher value change to the correct apply path.
 *
 * With a non-empty backend list (pi) the chosen `ModelOption` is applied
 * out-of-band via `onBackendModelChange`; otherwise the value is a Claude
 * `LlmModel` applied per-turn via `onModelChange`. A backend value with no
 * matching option is ignored.
 */
export const routeModelChange = (
  next: string,
  backendModels: ReadonlyArray<ModelOption> | undefined,
  onModelChange: (model: LlmModel) => void,
  onBackendModelChange?: (option: ModelOption) => void,
): void => {
  if (backendModels !== undefined && backendModels.length > 0) {
    const option = backendModels.find((candidate) => candidate.modelId === next);
    if (option !== undefined) {
      onBackendModelChange?.(option);
    }
    return;
  }
  onModelChange(next as LlmModel);
};
