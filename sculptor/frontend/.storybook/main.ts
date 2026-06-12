import type { StorybookConfig } from "@storybook/react-vite";

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
    return config;
  },
};
// eslint-disable-next-line import/no-default-export
export default config;
