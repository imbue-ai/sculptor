import type { ModelCatalogState } from "~/api";
import { LlmModel, type ModelOption } from "~/api";

/**
 * "No usable model": a backend-sourced harness (pi) whose catalog has been fetched
 * and is empty (no authenticated providers). `NOT_FETCHED_YET` is excluded — that is
 * still loading, not empty. Shared by the model picker's disabled state and the
 * composer's send-guard so the two cannot disagree.
 */
export const hasNoUsableModel = (
  sourcesBackendModels: boolean,
  backendModels: ReadonlyArray<ModelOption> | ModelCatalogState,
): boolean => sourcesBackendModels && Array.isArray(backendModels) && backendModels.length === 0;

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

// Fake Claude returns deterministic responses without making LLM calls; only
// shown when integration testing is enabled.
const TESTING_ONLY_MODELS: ReadonlyArray<LlmModel> = [LlmModel.FAKE_CLAUDE, LlmModel.FAKE_CLAUDE_2];

/**
 * `fakeModelDisplayName` (settings `TESTING.FAKE_MODEL_DISPLAY_NAME`, read via
 * `fakeModelDisplayNameAtom`) relabels the deterministic testing models so a
 * demo harness can present scripted agents under a custom name; every other
 * model keeps its real name, and an unset override changes nothing.
 */
export const getModelShortName = (model: LlmModel, fakeModelDisplayName?: string | null): string =>
  fakeModelDisplayName && TESTING_ONLY_MODELS.includes(model)
    ? fakeModelDisplayName
    : modelNames[model]?.short || "Unknown";

export const getModelLongName = (model: LlmModel, fakeModelDisplayName?: string | null): string =>
  fakeModelDisplayName && TESTING_ONLY_MODELS.includes(model)
    ? fakeModelDisplayName
    : modelNames[model]?.long || "Unknown";

// Models offered in production model pickers (desktop selector + mobile `+` menu).
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

/**
 * The built-in Claude switcher list (Claude Code uses the user's existing
 * authentication); the Fake Claude test doubles are appended only when
 * integration testing is enabled. A fake-model display-name override hides
 * them from the picker entirely: a demo harness seeds its scripted agents
 * out-of-band, and the relabelled models must not be user-selectable.
 */
export const getClaudeModelList = (
  isIntegrationTesting: boolean,
  fakeModelDisplayName?: string | null,
): ReadonlyArray<LlmModel> =>
  isIntegrationTesting && !fakeModelDisplayName ? [...PRODUCTION_MODELS, ...TESTING_ONLY_MODELS] : PRODUCTION_MODELS;

export type ProviderGroup = {
  provider: string;
  models: ReadonlyArray<ModelOption>;
};

/**
 * Partition a backend catalog (pi) into per-provider groups, preserving incoming
 * order: the backend delivers it newest-first, which we keep within and across
 * groups.
 */
export const groupModelsByProvider = (models: ReadonlyArray<ModelOption>): ReadonlyArray<ProviderGroup> => {
  const order: Array<string> = [];
  const byProvider = new Map<string, Array<ModelOption>>();
  for (const model of models) {
    const existing = byProvider.get(model.provider);
    if (existing === undefined) {
      order.push(model.provider);
      byProvider.set(model.provider, [model]);
    } else {
      existing.push(model);
    }
  }
  return order.map((provider) => ({ provider, models: byProvider.get(provider) ?? [] }));
};

const providerDisplayNames: Record<string, string> = {
  anthropic: "Anthropic",
  openrouter: "OpenRouter",
  deepseek: "DeepSeek",
  google: "Google",
  openai: "OpenAI",
  "openai-codex": "ChatGPT Plus/Pro (Codex)",
  "github-copilot": "GitHub Copilot",
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
