import { Theme } from "@radix-ui/themes";
import "@radix-ui/themes/styles.css";
import type { Preview, StoryContext } from "@storybook/react";
import { useSetAtom } from "jotai";
import type { ReactElement } from "react";
import { useEffect } from "react";

import { themeBuilderSettingsAtom } from "../src/common/state/atoms/themeBuilder.ts";
import type { ShikiThemePairName } from "../src/common/theme/shikiThemes.ts";
import { SHIKI_THEME_PAIR_NAMES } from "../src/common/theme/shikiThemes.ts";
import "../src/index.css";
import "./storybook-overrides.css";

const preview: Preview = {
  parameters: {
    layout: "fullscreen",
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
  },
  globalTypes: {
    theme: {
      description: "Radix UI theme appearance",
      toolbar: {
        title: "Theme",
        icon: "sun",
        items: [
          { value: "light", title: "Light", icon: "sun" },
          { value: "dark", title: "Dark", icon: "moon" },
        ],
        dynamicTitle: true,
      },
    },
    codeTheme: {
      description: "Shiki syntax highlighting theme",
      toolbar: {
        title: "Code Theme",
        icon: "markup",
        items: SHIKI_THEME_PAIR_NAMES.map((name) => ({ value: name, title: name })),
        dynamicTitle: true,
      },
    },
  },
  initialGlobals: {
    theme: "light",
    codeTheme: "GitHub",
  },
};

// eslint-disable-next-line import/no-default-export
export default preview;

/** Syncs the Storybook codeTheme global to the jotai themeBuilderSettings atom. */
const CodeThemeSync = ({ codeTheme }: { codeTheme: ShikiThemePairName }): null => {
  const setSettings = useSetAtom(themeBuilderSettingsAtom);
  useEffect(() => {
    setSettings((prev) => ({ ...prev, codeTheme }));
  }, [codeTheme, setSettings]);
  return null;
};

export const decorators = [
  (Story: () => ReactElement, context: StoryContext): ReactElement => {
    const appearance = (context.globals.theme as "light" | "dark") ?? "light";
    const codeTheme = (context.globals.codeTheme as ShikiThemePairName) ?? "GitHub";
    const isFullscreen = context.parameters?.panelsFullscreen === true;

    if (isFullscreen) {
      return (
        <Theme accentColor="gray" grayColor="gray" appearance={appearance}>
          <CodeThemeSync codeTheme={codeTheme} />
          <div style={{ background: "var(--gray-2)", minHeight: "100vh" }}>
            <Story />
          </div>
        </Theme>
      );
    }

    return (
      <Theme accentColor="gray" grayColor="gray" appearance={appearance}>
        <CodeThemeSync codeTheme={codeTheme} />
        <div
          style={{
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            minHeight: "100vh",
            padding: "2rem",
            background: "var(--gray-2)",
          }}
        >
          <Story />
        </div>
      </Theme>
    );
  },
];
