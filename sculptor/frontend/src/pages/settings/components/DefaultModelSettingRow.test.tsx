import { Theme } from "@radix-ui/themes";
import { cleanup, render, screen } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { ElementIds, LlmModel } from "~/api";

import { DefaultModelSettingRow } from "./DefaultModelSettingRow.tsx";

const withStore = (children: ReactNode): ReactElement => (
  <Provider store={createStore()}>
    <Theme>{children}</Theme>
  </Provider>
);

afterEach(() => {
  cleanup();
});

describe("DefaultModelSettingRow", () => {
  it("names a saved default that the picker no longer lists", () => {
    render(withStore(<DefaultModelSettingRow model={LlmModel.CLAUDE_4_8_OPUS} onChange={() => {}} />));
    expect(screen.getByTestId(ElementIds.SETTINGS_DEFAULT_MODEL_SELECT)).toHaveTextContent("Claude 4.8 Opus");
  });

  it("names a saved default that the picker lists", () => {
    render(withStore(<DefaultModelSettingRow model={LlmModel.CLAUDE_5_5_OPUS} onChange={() => {}} />));
    expect(screen.getByTestId(ElementIds.SETTINGS_DEFAULT_MODEL_SELECT)).toHaveTextContent("Claude 5.5 Opus");
  });

  it("reads Most Recently Used when no default is saved", () => {
    render(withStore(<DefaultModelSettingRow model={null} onChange={() => {}} />));
    expect(screen.getByTestId(ElementIds.SETTINGS_DEFAULT_MODEL_SELECT)).toHaveTextContent("Most Recently Used");
  });
});
