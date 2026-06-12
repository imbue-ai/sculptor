import { defineConfig } from "@hey-api/openapi-ts";

// eslint-disable-next-line import/no-default-export
export default defineConfig({
  input: "./sculptor_schema.json",
  output: "src/api",
  plugins: [
    {
      enums: "javascript",
      name: "@hey-api/typescript",
    },
    {
      name: "@hey-api/client-fetch",
      throwOnError: true,
    },
    {
      name: "@hey-api/sdk",
      asClass: false,
    },
  ],
});
