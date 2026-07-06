import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { Provider, createStore } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { EffortLevel, ElementIds, LlmModel } from "~/api";

import { AgentSettingsControls } from "./AgentSettingsControls.tsx";

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

// A stub navigate so the component's navigation wiring doesn't throw.
vi.mock("~/common/NavigateUtils.ts", () => ({
  useImbueNavigate: () => ({
    navigateToWorkspace: (): void => {},
    navigateToAgent: (): void => {},
    navigateToHome: (): void => {},
    navigateToGlobalSettings: (): void => {},
    navigateToRepoSetupCommand: (): void => {},
    navigateToRoot: (): void => {},
  }),
}));

const defaultProps = {
  model: LlmModel.CLAUDE_4_OPUS,
  onModelChange: (): void => {},
  effort: EffortLevel.XHIGH,
  onEffortChange: (): void => {},
  isFastMode: false,
  onFastModeToggle: (): void => {},
  isPlanMode: false,
  onPlanModeToggle: (): void => {},
};

describe("AgentSettingsControls canSelectModel", () => {
  it("renders an enabled model picker when canSelectModel defaults to true", () => {
    render(withStore(<AgentSettingsControls {...defaultProps} />));
    expect(screen.getByTestId(ElementIds.MODEL_SELECTOR)).toBeTruthy();
    expect(screen.queryByTestId(ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION)).toBeNull();
  });

  it("renders a disabled model picker when canSelectModel is false", () => {
    render(withStore(<AgentSettingsControls {...defaultProps} canSelectModel={false} />));
    expect(screen.queryByTestId(ElementIds.MODEL_SELECTOR)).toBeNull();
    expect(screen.getByTestId(ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION)).toBeTruthy();
  });
});

describe("AgentSettingsControls canUseFastMode", () => {
  it("hides the fast-mode toggle when canUseFastMode is false", () => {
    render(withStore(<AgentSettingsControls {...defaultProps} canUseFastMode={false} />));
    expect(screen.queryByTestId(ElementIds.FAST_MODE_TOGGLE)).toBeNull();
  });

  it("shows the fast-mode toggle when the model supports it and canUseFastMode is true", () => {
    render(withStore(<AgentSettingsControls {...defaultProps} canUseFastMode={true} />));
    expect(screen.getByTestId(ElementIds.FAST_MODE_TOGGLE)).toBeTruthy();
  });
});
