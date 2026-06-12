import { defineConfig } from "vite";

/* eslint-disable-next-line import/no-default-export */
export default defineConfig({
  build: {
    // By default, forge will bundle everything in `.vite/build`.
    outDir: ".vite/build", // explicitly set output directory
    lib: {
      entry: "src/electron/main.ts",
      formats: ["cjs"], // Use CommonJS format for Electron main process
      fileName: () => "main.cjs",
    },
    rollupOptions: {
      external: ["electron"], // don't bundle Electron
    },
  },
});
