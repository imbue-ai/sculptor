import path from "node:path";

import type { StorybookConfig } from "@storybook/react-vite";

import { sharedCss, sharedResolve } from "../vite.base.config.ts";

// The frontend root (parent of `.storybook`), which anchors the `~` alias and
// SCSS load paths.
const FRONTEND_ROOT = path.resolve(__dirname, "..");

const config: StorybookConfig = {
  stories: ["../src/**/*.mdx", "../src/**/*.stories.@(js|jsx|mjs|ts|tsx)"],
  addons: [],
  framework: {
    name: "@storybook/react-vite",
    options: {},
  },
  async viteFinal(config) {
    // Remove the generate-types plugin that requires backend Python dependencies
    config.plugins = config.plugins?.filter((plugin) => {
      if (plugin && typeof plugin === "object" && "name" in plugin) {
        return plugin.name !== "generate-types";
      }
      return true;
    });

    // Storybook derives its own Vite config and cannot auto-load the app's
    // (which lives in vite.web/base/electron.config.ts, not the default
    // vite.config.ts), so the shared `~` -> src alias and the SCSS load paths
    // never reach it. Wire them in explicitly, or every `~/…` import and
    // `@use "scrollbar"` fails to resolve and no story renders.
    config.resolve = {
      ...config.resolve,
      alias: { ...config.resolve?.alias, ...sharedResolve(FRONTEND_ROOT).alias },
    };
    config.css = { ...config.css, ...sharedCss(FRONTEND_ROOT) };

    return config;
  },
};
// eslint-disable-next-line import/no-default-export
export default config;
