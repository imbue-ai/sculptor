import { Select, Theme } from "@radix-ui/themes";
import { cleanup, render, type RenderResult, screen, within } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ElementIds, LlmModel, type ModelOption } from "~/api";
import { routeModelChange } from "~/common/modelConstants.ts";

import { ModelSelectOptions } from "./ModelSelectOptions";
import { ModelSelector } from "./ModelSelector";

const PI_MODELS: ReadonlyArray<ModelOption> = [
  { provider: "anthropic", modelId: "claude-opus-4-8", displayName: "Claude Opus 4.8" },
  { provider: "anthropic", modelId: "claude-sonnet-4-6", displayName: "Claude Sonnet 4.6" },
];

// A multi-provider catalog, interleaved across providers the way the backend's
// global newest-first sort can deliver it.
const MULTI_PROVIDER_MODELS: ReadonlyArray<ModelOption> = [
  { provider: "anthropic", modelId: "anthropic-new", displayName: "Anthropic New" },
  { provider: "openrouter", modelId: "openrouter-new", displayName: "OpenRouter New" },
  { provider: "anthropic", modelId: "anthropic-old", displayName: "Anthropic Old" },
  { provider: "openrouter", modelId: "openrouter-old", displayName: "OpenRouter Old" },
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
  const renderOptions = (models?: ReadonlyArray<ModelOption>, optionTestId?: string): RenderResult =>
    render(
      withStore(
        <Select.Root open value={models ? models[0].modelId : LlmModel.CLAUDE_FABLE_5}>
          <Select.Trigger />
          <Select.Content>
            <ModelSelectOptions models={models} optionTestId={optionTestId} />
          </Select.Content>
        </Select.Root>,
      ),
    );

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
    // The Claude path stays a flat list — no provider group headers.
    expect(screen.queryAllByRole("group")).toHaveLength(0);
  });

  it("groups backend models under a non-selectable provider header, ordered by first appearance", () => {
    renderOptions(MULTI_PROVIDER_MODELS, ElementIds.MODEL_OPTION);

    // One group per distinct provider, ordered by first appearance in the catalog.
    const groups = screen.getAllByRole("group");
    expect(groups).toHaveLength(2);
    expect(within(groups[0]).getByText("Anthropic")).toBeInTheDocument();
    expect(within(groups[1]).getByText("OpenRouter")).toBeInTheDocument();

    // The provider headers are labels, never selectable model options.
    const optionTexts = screen.getAllByTestId(ElementIds.MODEL_OPTION).map((item) => item.textContent);
    expect(optionTexts).not.toContain("Anthropic");
    expect(optionTexts).not.toContain("OpenRouter");
  });

  it("places each model under its provider, preserving newest-first order within the group", () => {
    renderOptions(MULTI_PROVIDER_MODELS, ElementIds.MODEL_OPTION);
    const groups = screen.getAllByRole("group");

    const textsIn = (group: HTMLElement): ReadonlyArray<string | null> =>
      within(group)
        .getAllByTestId(ElementIds.MODEL_OPTION)
        .map((item) => item.textContent);

    // Interleaving collapses into contiguous groups, each still newest-first.
    expect(textsIn(groups[0])).toEqual(["Anthropic New", "Anthropic Old"]);
    expect(textsIn(groups[1])).toEqual(["OpenRouter New", "OpenRouter Old"]);
  });

  it("keeps the MODEL_OPTION test id and model_id value on each grouped item", () => {
    // A <form> ancestor makes Radix emit a hidden native <option value=…> per
    // item, exposing each item's model_id value in the DOM.
    const { container } = render(
      withStore(
        <form>
          <Select.Root open value={MULTI_PROVIDER_MODELS[0].modelId}>
            <Select.Trigger />
            <Select.Content>
              <ModelSelectOptions models={MULTI_PROVIDER_MODELS} optionTestId={ElementIds.MODEL_OPTION} />
            </Select.Content>
          </Select.Root>
        </form>,
      ),
    );

    // Every model stays one MODEL_OPTION item — the testid integration tests
    // read the dropdown options by.
    expect(screen.getAllByTestId(ElementIds.MODEL_OPTION)).toHaveLength(MULTI_PROVIDER_MODELS.length);

    // Each item's `value` (model_id) survives grouping unchanged.
    const optionValues = Array.from(container.querySelectorAll("option")).map((option) => option.getAttribute("value"));
    expect(optionValues).toEqual(expect.arrayContaining(MULTI_PROVIDER_MODELS.map((model) => model.modelId)));
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

  it("disables the switcher when the backend list has a single model", () => {
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_4_OPUS_200K}
          onModelChange={() => {}}
          capabilityValue={true}
          backendModels={[PI_MODELS[0]]}
          selectedModelId="claude-opus-4-8"
        />,
      ),
    );
    // Still shows the current model, but the trigger is disabled (nothing to
    // switch to) and not the capability-denial treatment.
    const trigger = screen.getByTestId(ElementIds.MODEL_SELECTOR);
    expect(trigger).toHaveTextContent("Claude Opus 4.8");
    expect(trigger).toBeDisabled();
    expect(screen.queryByTestId(ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION)).not.toBeInTheDocument();
  });
});

describe("routeModelChange", () => {
  it("routes a pi change to onBackendModelChange with the chosen ModelOption", () => {
    const onBackendModelChange = vi.fn();
    const onModelChange = vi.fn();
    routeModelChange("claude-sonnet-4-6", PI_MODELS, onModelChange, onBackendModelChange);
    expect(onBackendModelChange).toHaveBeenCalledTimes(1);
    expect(onBackendModelChange).toHaveBeenCalledWith(PI_MODELS[1]);
    // The Claude per-turn handler must NOT fire on the pi path.
    expect(onModelChange).not.toHaveBeenCalled();
  });

  it("routes a Claude change to onModelChange when no backend list is present", () => {
    const onBackendModelChange = vi.fn();
    const onModelChange = vi.fn();
    routeModelChange(LlmModel.CLAUDE_4_SONNET, undefined, onModelChange, onBackendModelChange);
    expect(onModelChange).toHaveBeenCalledWith(LlmModel.CLAUDE_4_SONNET);
    expect(onBackendModelChange).not.toHaveBeenCalled();
  });

  it("ignores a backend value with no matching option", () => {
    const onBackendModelChange = vi.fn();
    const onModelChange = vi.fn();
    routeModelChange("claude-nope", PI_MODELS, onModelChange, onBackendModelChange);
    expect(onBackendModelChange).not.toHaveBeenCalled();
    expect(onModelChange).not.toHaveBeenCalled();
  });
});
