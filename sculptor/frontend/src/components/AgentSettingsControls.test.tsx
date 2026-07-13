import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
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
  useImbueNavigate: (): Record<string, () => void> => ({
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

describe("AgentSettingsControls", () => {
  it("renders the full Claude control cluster with an enabled model picker", () => {
    render(withStore(<AgentSettingsControls {...defaultProps} />));
    expect(screen.getByTestId(ElementIds.PLAN_MODE_TOGGLE)).toBeTruthy();
    // Opus supports fast mode, so its toggle shows.
    expect(screen.getByTestId(ElementIds.FAST_MODE_TOGGLE)).toBeTruthy();
    expect(screen.getByTestId(ElementIds.MODEL_SELECTOR)).toBeTruthy();
    // This cluster is Claude-only, so the model picker is never the disabled
    // capability-tooltip treatment.
    expect(screen.queryByTestId(ElementIds.CAPABILITY_DISABLED_MODEL_SELECTION)).toBeNull();
  });
});
