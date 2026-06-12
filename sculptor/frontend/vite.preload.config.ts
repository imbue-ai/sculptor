import { defineConfig } from "vite";

/* eslint-disable-next-line import/no-default-export */
export default defineConfig({
  build: {
    // By default, forge will bundle everything in `.vite/build`.
    outDir: ".vite/build", // explicitly set output directory
    lib: {
      entry: "src/preload.ts",
      formats: ["cjs"], // Use CommonJS format for Electron preload script
      fileName: () => "preload.cjs",
    },
    rollupOptions: {
      // Don't bundle the Electron runtime into the preload
      external: ["electron"],
    },
  },
});
