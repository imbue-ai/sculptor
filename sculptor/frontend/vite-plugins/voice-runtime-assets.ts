import fs from "node:fs";
import path from "node:path";

import type { Plugin } from "vite";

/**
 * Serve the voice engine's runtime code from the app's own origin in both dev
 * and packaged builds.
 *
 * The on-device speech engine (`src/common/voice/`) runs Silero VAD and Moonshine
 * through ONNX Runtime wasm and a VAD audio worklet. Those are *code* (not model
 * weights, which come from the backend's managed voice-models endpoint), so they
 * ship with the app. Transformers.js and vad-web each embed their own
 * onnxruntime-web build, so each gets the wasm set it expects (two sets):
 *
 *   - transformers.js: the `jsep` wasm the bundled ORT loads, served under
 *     `/vendor/voice/transformers-ort/` (wired via `env.backends.onnx.wasm.wasmPaths`).
 *   - vad-web: the plain wasm its `onnxruntime-web/wasm` entry loads, served under
 *     `/vendor/voice/vad-ort/` (wired via `onnxWASMBasePath`).
 *   - vad-web's audio worklet, served under `/vendor/voice/vad/` (the engine points
 *     vad-web's `baseAssetPath` at the backend for the Silero weights and redirects
 *     the worklet request here).
 *
 * The default is otherwise a CDN (jsDelivr), which the engine must never hit at
 * runtime. In dev a middleware streams the files straight from node_modules; the
 * build emits them at a stable, unhashed path the engine URLs match.
 */

const URL_PREFIX = "/vendor/voice/";

/** Files copied out of node_modules, keyed by their served sub-path under `/vendor/voice/`. */
const VOICE_ASSETS = [
  {
    source: "node_modules/@huggingface/transformers/dist/ort-wasm-simd-threaded.jsep.mjs",
    served: "transformers-ort/ort-wasm-simd-threaded.jsep.mjs",
  },
  {
    source: "node_modules/@huggingface/transformers/dist/ort-wasm-simd-threaded.jsep.wasm",
    served: "transformers-ort/ort-wasm-simd-threaded.jsep.wasm",
  },
  {
    source: "node_modules/@ricky0123/vad-web/node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.mjs",
    served: "vad-ort/ort-wasm-simd-threaded.mjs",
  },
  {
    source: "node_modules/@ricky0123/vad-web/node_modules/onnxruntime-web/dist/ort-wasm-simd-threaded.wasm",
    served: "vad-ort/ort-wasm-simd-threaded.wasm",
  },
  {
    source: "node_modules/@ricky0123/vad-web/dist/vad.worklet.bundle.min.js",
    served: "vad/vad.worklet.bundle.min.js",
  },
] as const satisfies ReadonlyArray<{ source: string; served: string }>;

const CONTENT_TYPES: Record<string, string> = {
  ".wasm": "application/wasm",
  ".mjs": "text/javascript",
  ".js": "text/javascript",
};

const contentTypeFor = (file: string): string => CONTENT_TYPES[path.extname(file)] ?? "application/octet-stream";

export const voiceRuntimeAssets = (root: string): Plugin => ({
  name: "sculptor:voice-runtime-assets",

  configureServer(server): void {
    // Match the served prefix anywhere in the URL so it works under a base path
    // (e.g. the OpenHost `/proxy/<port>/` front) as well as the plain root.
    server.middlewares.use((req, res, next): void => {
      const url = (req.url ?? "").split("?")[0];
      const index = url.indexOf(URL_PREFIX);
      if (index === -1) {
        next();
        return;
      }
      const served = url.slice(index + URL_PREFIX.length);
      const asset = VOICE_ASSETS.find((candidate) => candidate.served === served);
      if (asset === undefined) {
        next();
        return;
      }
      const absolute = path.resolve(root, asset.source);
      if (!fs.existsSync(absolute)) {
        next();
        return;
      }
      res.setHeader("Content-Type", contentTypeFor(absolute));
      res.setHeader("Cache-Control", "no-cache");
      fs.createReadStream(absolute).pipe(res);
    });
  },

  generateBundle(): void {
    for (const asset of VOICE_ASSETS) {
      // Explicit fileName (unhashed) keeps the path the engine's URLs reference.
      this.emitFile({
        type: "asset",
        fileName: `vendor/voice/${asset.served}`,
        source: fs.readFileSync(path.resolve(root, asset.source)),
      });
    }
  },
});
