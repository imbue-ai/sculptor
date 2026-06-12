import react from "@vitejs/plugin-react-swc";
import fs from "node:fs";
import path from "node:path";
import { defineConfig } from "vite";

/**
 * Plugin build. Externalises every peer dependency so the runtime import-map
 * in the host's `index.html` can resolve them to the host's singleton
 * instances. The output is a single ESM file dropped into the host's
 * `public/plugins/<id>/` directory so the host serves it under
 * `/plugins/<id>/main.js`.
 */
const HOST_PUBLIC_PLUGINS = path.resolve(__dirname, "../../public/plugins/linear-issue");

const copyManifest = (): import("vite").Plugin => ({
  name: "copy-plugin-manifest",
  writeBundle(): void {
    const src = path.resolve(__dirname, "manifest.json");
    const dest = path.join(HOST_PUBLIC_PLUGINS, "manifest.json");
    fs.copyFileSync(src, dest);
  },
});

export default defineConfig({
  plugins: [react(), copyManifest()],
  build: {
    outDir: HOST_PUBLIC_PLUGINS,
    emptyOutDir: true,
    sourcemap: true,
    lib: {
      entry: path.resolve(__dirname, "src/index.tsx"),
      formats: ["es"],
      fileName: () => "main.js",
    },
    rollupOptions: {
      external: [
        "react",
        "react/jsx-runtime",
        "react-dom",
        "react-dom/client",
        "jotai",
        "@tanstack/react-query",
        "@radix-ui/themes",
        "lucide-react",
        "@sculptor/plugin-sdk",
      ],
      output: {
        // Don't add hashes — manifest references main.js by name.
        entryFileNames: "main.js",
        assetFileNames: "[name][extname]",
      },
    },
  },
});
