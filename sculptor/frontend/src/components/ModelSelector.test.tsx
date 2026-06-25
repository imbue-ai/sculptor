import { Button, DropdownMenu, Select, Theme } from "@radix-ui/themes";
import { cleanup, fireEvent, render, type RenderResult, screen, within } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ElementIds, LlmModel, type ModelOption } from "~/api";
import { getModelLongName, routeModelChange } from "~/common/modelConstants.ts";

import { ModelSelectOptions } from "./ModelSelectOptions";
import { BackendModelItems, ClaudeModelItems, ModelSelector } from "./ModelSelector";

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
  // Radix Select/DropdownMenu call scrollIntoView on open; jsdom does not implement it.
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
    const optionTexts = screen
      .getAllByTestId(new RegExp(`^${ElementIds.MODEL_OPTION}-`))
      .map((item) => item.textContent);
    expect(optionTexts).not.toContain("Anthropic");
    expect(optionTexts).not.toContain("OpenRouter");
  });

  it("places each model under its provider, preserving newest-first order within the group", () => {
    renderOptions(MULTI_PROVIDER_MODELS, ElementIds.MODEL_OPTION);
    const groups = screen.getAllByRole("group");

    const textsIn = (group: HTMLElement): ReadonlyArray<string | null> =>
      within(group)
        .getAllByTestId(new RegExp(`^${ElementIds.MODEL_OPTION}-`))
        .map((item) => item.textContent);

    // Interleaving collapses into contiguous groups, each still newest-first.
    expect(textsIn(groups[0])).toEqual(["Anthropic New", "Anthropic Old"]);
    expect(textsIn(groups[1])).toEqual(["OpenRouter New", "OpenRouter Old"]);
  });

  it("gives each grouped model a MODEL_OPTION test id carrying its model_id", () => {
    renderOptions(MULTI_PROVIDER_MODELS, ElementIds.MODEL_OPTION);

    // Every model is a single option whose testid encodes its model_id — the hook
    // integration tests select options by `<MODEL_OPTION>-<model id>`.
    const options = screen.getAllByTestId(new RegExp(`^${ElementIds.MODEL_OPTION}-`));
    expect(options).toHaveLength(MULTI_PROVIDER_MODELS.length);
    for (const model of MULTI_PROVIDER_MODELS) {
      expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-${model.modelId}`)).toHaveTextContent(model.displayName);
    }
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
          sourcesBackendModels={true}
          backendModels={PI_MODELS}
          selectedModelId="claude-sonnet-4-6"
          onAuthenticate={() => {}}
        />,
      ),
    );
    expect(screen.getByTestId(ElementIds.MODEL_SELECTOR)).toHaveTextContent("Claude Sonnet 4.6");
  });

  it("keeps the Claude short-name label when no backend models are present", () => {
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_FABLE_5}
          onModelChange={() => {}}
          capabilityValue={true}
          onAuthenticate={() => {}}
        />,
      ),
    );
    const trigger = screen.getByTestId(ElementIds.MODEL_SELECTOR);
    // The Claude path must not show a raw model_id; it renders the short name.
    expect(trigger).not.toHaveTextContent("claude-");
  });

  it("renders the disabled-with-tooltip treatment when the capability is false", () => {
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_FABLE_5}
          onModelChange={() => {}}
          capabilityValue={false}
          onAuthenticate={() => {}}
        />,
      ),
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
          sourcesBackendModels={true}
          backendModels={[PI_MODELS[0]]}
          selectedModelId="claude-opus-4-8"
          onAuthenticate={() => {}}
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

  it("prompts to authenticate when a backend harness has no providers", () => {
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_4_OPUS_200K}
          onModelChange={() => {}}
          capabilityValue={true}
          sourcesBackendModels={true}
          backendModels={[]}
          onAuthenticate={() => {}}
        />,
      ),
    );
    // No model list and no built-in fallback for this harness: prompt to
    // authenticate instead of showing the switcher.
    expect(screen.getByTestId(ElementIds.MODEL_SELECTOR_AUTH_PROMPT)).toBeInTheDocument();
    expect(screen.queryByTestId(ElementIds.MODEL_SELECTOR)).not.toBeInTheDocument();
  });

  it("invokes onAuthenticate when the no-providers prompt is clicked", () => {
    const onAuthenticate = vi.fn();
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_4_OPUS_200K}
          onModelChange={() => {}}
          capabilityValue={true}
          sourcesBackendModels={true}
          backendModels={[]}
          onAuthenticate={onAuthenticate}
        />,
      ),
    );
    fireEvent.click(screen.getByTestId(ElementIds.MODEL_SELECTOR_AUTH_PROMPT));
    expect(onAuthenticate).toHaveBeenCalledTimes(1);
  });

  it("shows the interactive switcher (not the auth prompt) when a backend harness has providers", () => {
    render(
      withStore(
        <ModelSelector
          model={LlmModel.CLAUDE_4_OPUS_200K}
          onModelChange={() => {}}
          capabilityValue={true}
          sourcesBackendModels={true}
          backendModels={PI_MODELS}
          selectedModelId="claude-opus-4-8"
          onAuthenticate={() => {}}
        />,
      ),
    );
    expect(screen.getByTestId(ElementIds.MODEL_SELECTOR)).toBeInTheDocument();
    expect(screen.queryByTestId(ElementIds.MODEL_SELECTOR_AUTH_PROMPT)).not.toBeInTheDocument();
  });
});

describe("BackendModelItems", () => {
  // The menu body only mounts when the DropdownMenu is open; render it inside a
  // controlled-open menu to inspect the items.
  const renderItems = (models: ReadonlyArray<ModelOption>, selectedModelId?: string): RenderResult =>
    render(
      withStore(
        <DropdownMenu.Root open>
          <DropdownMenu.Trigger>
            <Button>trigger</Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content>
            <BackendModelItems models={models} selectedModelId={selectedModelId} onValueChange={() => {}} />
          </DropdownMenu.Content>
        </DropdownMenu.Root>,
      ),
    );

  it("groups a single provider's models under one non-selectable header", () => {
    renderItems(PI_MODELS, "claude-opus-4-8");
    // The provider name leads the list as a non-selectable label.
    expect(screen.getByText("Anthropic")).toBeInTheDocument();
    // Both models are selectable options keyed by model_id, shown inline (no cascade).
    expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-claude-opus-4-8`)).toHaveTextContent("Claude Opus 4.8");
    expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-claude-sonnet-4-6`)).toHaveTextContent("Claude Sonnet 4.6");
    // A single provider is not rendered as a cascading sub-trigger.
    expect(screen.queryByTestId(new RegExp(`^${ElementIds.MODEL_PROVIDER_OPTION}-`))).not.toBeInTheDocument();
  });

  it("renders a cascading per-provider menu for multiple providers", () => {
    renderItems(MULTI_PROVIDER_MODELS, "anthropic-new");
    // One top-level sub-trigger per distinct provider, ordered by first appearance.
    const providers = screen.getAllByTestId(new RegExp(`^${ElementIds.MODEL_PROVIDER_OPTION}-`));
    expect(providers.map((item) => item.textContent)).toEqual(["Anthropic", "OpenRouter"]);
    expect(screen.getByTestId(`${ElementIds.MODEL_PROVIDER_OPTION}-anthropic`)).toBeInTheDocument();
    expect(screen.getByTestId(`${ElementIds.MODEL_PROVIDER_OPTION}-openrouter`)).toBeInTheDocument();
    // The models live behind their provider's submenu, so they are not rendered
    // until the user opens it.
    expect(screen.queryByTestId(`${ElementIds.MODEL_OPTION}-anthropic-new`)).not.toBeInTheDocument();
  });
});

describe("ClaudeModelItems", () => {
  // The menu body only mounts when the DropdownMenu is open; render it inside a
  // controlled-open menu to inspect the items.
  const renderClaude = (selectedModel: LlmModel): RenderResult =>
    render(
      withStore(
        <DropdownMenu.Root open>
          <DropdownMenu.Trigger>
            <Button>trigger</Button>
          </DropdownMenu.Trigger>
          <DropdownMenu.Content>
            <ClaudeModelItems
              models={[LlmModel.CLAUDE_4_OPUS_200K, LlmModel.CLAUDE_4_HAIKU]}
              selectedModel={selectedModel}
              onValueChange={() => {}}
            />
          </DropdownMenu.Content>
        </DropdownMenu.Root>,
      ),
    );

  it("renders the built-in Claude models as a flat radio list keyed by model id", () => {
    renderClaude(LlmModel.CLAUDE_4_OPUS_200K);
    // Each model is a selectable option keyed by its LlmModel id and labelled by long name.
    expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-${LlmModel.CLAUDE_4_OPUS_200K}`)).toHaveTextContent(
      getModelLongName(LlmModel.CLAUDE_4_OPUS_200K),
    );
    expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-${LlmModel.CLAUDE_4_HAIKU}`)).toHaveTextContent(
      getModelLongName(LlmModel.CLAUDE_4_HAIKU),
    );
    // The built-in Claude path is always flat — never a cascading provider menu.
    expect(screen.queryByTestId(new RegExp(`^${ElementIds.MODEL_PROVIDER_OPTION}-`))).not.toBeInTheDocument();
  });

  it("marks the current model as the selected radio item", () => {
    renderClaude(LlmModel.CLAUDE_4_HAIKU);
    expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-${LlmModel.CLAUDE_4_HAIKU}`)).toHaveAttribute(
      "aria-checked",
      "true",
    );
    expect(screen.getByTestId(`${ElementIds.MODEL_OPTION}-${LlmModel.CLAUDE_4_OPUS_200K}`)).toHaveAttribute(
      "aria-checked",
      "false",
    );
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
