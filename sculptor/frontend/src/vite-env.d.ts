/// <reference types="vite/client" />

// See https://vitejs.dev/guide/env-and-mode.html#intellisense-for-typescript
type ImportMetaEnv = {
  readonly SCULPTOR_API_PORT?: string;
  readonly SCULPTOR_FRONTEND_PORT?: string;
};

type ImportMeta = {
  readonly env: ImportMetaEnv;
};
