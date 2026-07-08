/// <reference types="vite/client" />

// See https://vitejs.dev/guide/env-and-mode.html#intellisense-for-typescript
type ImportMetaEnv = {
  readonly SCULPTOR_API_PORT?: string;
  readonly SCULPTOR_FRONTEND_PORT?: string;
  // Set only by the `just frontend` dev recipe: starts the empty first-run prompt
  // box blank so QA can type immediately. Unset for packaged builds and tests.
  readonly SCULPTOR_EMPTY_FIRST_RUN_PROMPT?: string;
};

type ImportMeta = {
  readonly env: ImportMetaEnv;
};

/**
 * Virtual module provided by the plugin-runtime-stubs Vite plugin. Exposes the
 * host's installed version of each shared package, embedded at build time.
 */
declare module "virtual:sculptor/plugin-host-versions" {
  export const hostPackageVersions: Readonly<Record<string, string>>;
}
