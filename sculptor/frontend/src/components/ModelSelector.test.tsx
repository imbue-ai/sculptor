import { Select, Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { ElementIds, LlmModel, type ModelOption } from "~/api";

import { ModelSelectOptions } from "./ModelSelectOptions";
import { ModelSelector } from "./ModelSelector";

const PI_MODELS: ReadonlyArray<ModelOption> = [
  { provider: "anthropic", modelId: "claude-opus-4-8", displayName: "Claude Opus 4.8" },
  { provider: "anthropic", modelId: "claude-sonnet-4-6", displayName: "Claude Sonnet 4.6" },
];

const withStore = (children: ReactNode): ReactElement => (
  <Provider store={createStore()}>
    <Theme>{children}</Theme>
  </Provider>
);

beforeAll(() => {
  // Radix Select calls scrollIntoView on open; jsdom does not implement it.
  Element.prototype.scrollIntoView = (): void => {};
});

afterEach(() => {
  cleanup();
});

describe("ModelSelectOptions", () => {
  // The dropdown content only mounts when the Select is open, so render the
  // options inside an open Select to inspect the items.
  const renderOptions = (models?: ReadonlyArray<ModelOption>): void => {
    render(
      withStore(
        <Select.Root open value={models ? models[0].modelId : LlmModel.CLAUDE_FABLE_5}>
          <Select.Trigger />
          <Select.Content>
            <ModelSelectOptions models={models} />
          </Select.Content>
        </Select.Root>,
      ),
    );
  };

  // Radix renders the selected option's text in both the visible item and a
  // hidden native <select>, so the selected label appears more than once; assert
  // presence with getAllByText rather than the single-match getByText.
  it("renders backend models by display name when provided", () => {
    renderOptions(PI_MODELS);
    expect(screen.getAllByText("Claude Opus 4.8").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Claude Sonnet 4.6").length).toBeGreaterThan(0);
  });

  it("renders the built-in Claude list (by display name) when no backend models are given", () => {
    renderOptions(undefined);
    // The Claude path keeps PRODUCTION_MODELS display names — integration tests
    // select these by exact name, so the fallback must not regress.
    expect(screen.getAllByText("Claude 4.6 Sonnet").length).toBeGreaterThan(0);
    // A pi model id must NOT appear on the Claude path.
    expect(screen.queryByText("Claude Opus 4.8")).not.toBeInTheDocument();
  });
});

describe("ModelSelector", () => {
  it("shows the backend model's display name as the trigger label (pi)", () => {
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_4_OPUS_200K}
          onModelChange={() => {}}
          capabilityValue={true}
          backendModels={PI_MODELS}
          selectedModelId="claude-sonnet-4-6"
        />,
      ),
    );
    expect(screen.getByTestId(ElementIds.MODEL_SELECTOR)).toHaveTextContent("Claude Sonnet 4.6");
  });

  it("keeps the Claude short-name label when no backend models are present", () => {
    render(
      withStore(<ModelSelector model={LlmModel.CLAUDE_FABLE_5} onModelChange={() => {}} capabilityValue={true} />),
    );
    const trigger = screen.getByTestId(ElementIds.MODEL_SELECTOR);
    // The Claude path must not show a raw model_id; it renders the short name.
    expect(trigger).not.toHaveTextContent("claude-");
  });

  it("renders the disabled-with-tooltip treatment when the capability is false", () => {
    render(
      withStore(<ModelSelector model={LlmModel.CLAUDE_FABLE_5} onModelChange={() => {}} capabilityValue={false} />),
    );
    expect(screen.getByTestId(ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION)).toBeInTheDocument();
    expect(screen.queryByTestId(ElementIds.MODEL_SELECTOR)).not.toBeInTheDocument();
  });
});
