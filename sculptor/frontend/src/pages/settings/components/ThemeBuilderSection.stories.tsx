import type { Meta, StoryObj } from "@storybook/react-vite";
import { createStore, Provider as JotaiProvider } from "jotai";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";

import type { ThemeBuilderSettings } from "~/common/state/atoms/themeBuilder.ts";
import { DEFAULT_THEME_BUILDER_SETTINGS, themeBuilderSettingsAtom } from "~/common/state/atoms/themeBuilder.ts";

import { ThemeBuilderSection } from "./ThemeBuilderSection.tsx";

const Wrapper = ({ initialSettings }: { initialSettings: ThemeBuilderSettings }): ReactElement => {
  const store = createStore();
  store.set(themeBuilderSettingsAtom, initialSettings);
  return (
    <MemoryRouter>
      <JotaiProvider store={store}>
        <div style={{ width: "600px" }}>
          <ThemeBuilderSection />
        </div>
      </JotaiProvider>
    </MemoryRouter>
  );
};

const meta = {
  title: "Custom/ThemeBuilderSection",
  component: Wrapper,
} satisfies Meta<typeof Wrapper>;

// eslint-disable-next-line import/no-default-export
export default meta;

type Story = StoryObj<typeof meta>;

export const Default: Story = {
  args: {
    initialSettings: DEFAULT_THEME_BUILDER_SETTINGS,
  },
};

export const CustomTheme: Story = {
  args: {
    initialSettings: {
      ...DEFAULT_THEME_BUILDER_SETTINGS,
      accentColor: "blue",
      grayColor: "slate",
      appearance: "dark",
      radius: "full",
      scaling: "110%",
      panelBackground: "solid",
      dangerColor: "crimson",
      successColor: "teal",
      warningColor: "orange",
      infoColor: "cyan",
    },
  },
};
