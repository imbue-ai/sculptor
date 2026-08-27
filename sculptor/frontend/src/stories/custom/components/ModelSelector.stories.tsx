import type { Meta, StoryObj } from "@storybook/react-vite";

import type { ModelOption } from "~/api";
import { LlmModel } from "~/api";
import { ModelSelector } from "~/components/ModelSelector";

const SINGLE_PROVIDER_MODELS: ReadonlyArray<ModelOption> = [
  { provider: "anthropic", modelId: "claude-opus-4-8", displayName: "Claude Opus 4.8" },
  { provider: "anthropic", modelId: "claude-sonnet-4-6", displayName: "Claude Sonnet 4.6" },
  { provider: "anthropic", modelId: "claude-haiku-4-5", displayName: "Claude Haiku 4.5" },
];

const MULTI_PROVIDER_MODELS: ReadonlyArray<ModelOption> = [
  { provider: "anthropic", modelId: "claude-opus-4-8", displayName: "Claude Opus 4.8" },
  { provider: "anthropic", modelId: "claude-sonnet-4-6", displayName: "Claude Sonnet 4.6" },
  { provider: "openrouter", modelId: "deepseek-v3", displayName: "DeepSeek V3" },
  { provider: "openrouter", modelId: "llama-3.3-70b", displayName: "Llama 3.3 70B" },
  { provider: "google", modelId: "gemini-2.5-pro", displayName: "Gemini 2.5 Pro" },
];

const noop = (): void => {};

const meta: Meta<typeof ModelSelector> = {
  title: "Custom/ModelSelector",
  component: ModelSelector,
  args: {
    model: LlmModel.CLAUDE_4_OPUS_200K,
    onModelChange: noop,
    onBackendModelChange: noop,
    capabilityValue: true,
  },
};
// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof ModelSelector>;

/** Claude (no backend catalog): the built-in model list. */
export const ClaudeList: Story = {
  args: { sourcesBackendModels: false },
};

/** Pi, one provider: a non-selectable provider header over its models. */
export const SingleProvider: Story = {
  args: {
    sourcesBackendModels: true,
    backendModels: SINGLE_PROVIDER_MODELS,
    selectedModelId: "claude-opus-4-8",
  },
};

/** Pi, multiple providers: a top-level entry per provider, each cascading into its models. */
export const MultiProvider: Story = {
  args: {
    sourcesBackendModels: true,
    backendModels: MULTI_PROVIDER_MODELS,
    selectedModelId: "claude-opus-4-8",
  },
};

/** Pi, no authenticated providers: a prompt to authenticate. */
export const NoProviders: Story = {
  args: {
    sourcesBackendModels: true,
    backendModels: [],
  },
};
