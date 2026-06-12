/** @jest-config-loader ts-node */
/** @jest-config-loader-options {"transpileOnly": true} */

import type { Config } from "jest";

const config: Config = {
  clearMocks: true,
  collectCoverage: true,
  coverageDirectory: "coverage",

  // Required for Lexical
  testEnvironment: "jsdom",

  transform: {
    // We sidestep the babel compiler for jest. The babel compiler cannot access its own
    // configuration file as a .ts, and that means we cannnot run the test.
    // Feel free to remove this when we upgrade node.
    "^.+\\.[tj]sx?$": [
      "babel-jest",
      {
        configFile: false, // don't look for babel.config.* at all
        babelrc: false,
        presets: ["@babel/preset-env", ["@babel/preset-react", { runtime: "automatic" }], "@babel/preset-typescript"],
      },
    ],
  },

  extensionsToTreatAsEsm: [".ts", ".tsx"],

  setupFilesAfterEnv: ["<rootDir>/jest.setup.ts"],

  // Typical test file patterns
  testMatch: [
    "**/*.test.ts",
    "**/*.test.tsx",

    // DO NOT ADD any tests to the following formats:
    // They will be ignored.
    // __tests__/**/*.test.{ts|js}x?
    // tests/**/*.test.{ts|js}x?
  ],
};

/* eslint-disable-next-line import/no-default-export */
export default config;
