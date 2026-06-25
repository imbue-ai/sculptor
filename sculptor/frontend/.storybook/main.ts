import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import type { StorybookConfig } from "@storybook/react-vite";

const SRC_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../src");

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
    // Resolve the `~` -> src alias explicitly: the tsconfig-paths plugin does not
    // resolve `~/...ts` (explicit extension) imports under Storybook's vite.
    const existingAlias = config.resolve?.alias;
    config.resolve = config.resolve ?? {};
    config.resolve.alias = Array.isArray(existingAlias)
      ? [...existingAlias, { find: /^~\//, replacement: `${SRC_DIR}/` }]
      : { ...existingAlias, "~": SRC_DIR };
    return config;
  },
};
// eslint-disable-next-line import/no-default-export
export default config;
