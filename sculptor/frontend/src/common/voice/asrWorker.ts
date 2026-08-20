// The ASR worker: owns the Moonshine pipeline so inference never blocks the
// renderer's main thread (which also runs the UI and the VAD's frame
// processing). The engine keeps its one-at-a-time FIFO on the main side, so at
// most one transcribe request is ever outstanding.
//
// Everything renderer-side the worker cannot read itself arrives in the init
// message: the backend models base URL, the app-origin wasm base, and the
// session token (getSessionToken() reads renderer state a worker cannot see).

import { withVoiceModelFetchAuth } from "./fetchAuth.ts";

type AsrOutput = { text: string };
type AsrTranscriber = (audio: Float32Array) => Promise<AsrOutput | Array<AsrOutput>>;

export type AsrWorkerInit = {
  type: "init";
  modelsBaseUrl: string;
  wasmBaseUrl: string;
  token: string | null;
  tokenParam: string;
  /** Chosen on the main thread (only WebGPU when an adapter really exists);
   *  the worker falls back to wasm/q8 itself if this device fails to load. */
  device: "webgpu" | "wasm";
  dtype: "fp32" | "q8";
};

export type AsrWorkerTranscribe = {
  type: "transcribe";
  id: number;
  audio: ArrayBuffer;
};

export type AsrWorkerRequest = AsrWorkerInit | AsrWorkerTranscribe;

export type AsrWorkerResponse =
  | { type: "ready" }
  | { type: "init-error"; message: string }
  | { type: "result"; id: number; text: string }
  | { type: "transcribe-error"; id: number; message: string };

const MOONSHINE_MODEL_ID = "onnx-community/moonshine-base-ONNX";

const describeError = (error: unknown): string =>
  error instanceof Error ? error.message : typeof error === "string" ? error : "Unknown error";

let transcriber: AsrTranscriber | null = null;

const loadPipeline = async (init: AsrWorkerInit): Promise<void> => {
  const transformers = await import("@huggingface/transformers");
  transformers.env.allowLocalModels = false;
  transformers.env.remoteHost = init.modelsBaseUrl;
  // The default wasmPaths points at jsDelivr; serve the wasm from our own origin.
  const wasm = transformers.env.backends.onnx.wasm;
  if (wasm !== undefined) {
    wasm.wasmPaths = init.wasmBaseUrl;
    wasm.numThreads = 1;
  }
  // The explicit task type argument keeps `pipeline`'s return from widening
  // into the whole-task union (which TS reports as "too complex to represent").
  const load = (device: "webgpu" | "wasm", dtype: "fp32" | "q8"): Promise<AsrTranscriber> =>
    transformers.pipeline<"automatic-speech-recognition">("automatic-speech-recognition", MOONSHINE_MODEL_ID, {
      dtype,
      device,
    });
  transcriber = await withVoiceModelFetchAuth(
    { modelsBase: init.modelsBaseUrl, token: init.token, tokenParam: init.tokenParam },
    async () => {
      try {
        return await load(init.device, init.dtype);
      } catch {
        // An adapter can exist yet fail to load the model; wasm/q8 always works.
        return load("wasm", "q8");
      }
    },
  );
};

const transcribe = async (audio: Float32Array): Promise<string> => {
  if (transcriber === null) return "";
  const output = await transcriber(audio);
  const result = Array.isArray(output) ? output[0] : output;
  return (result?.text ?? "").trim();
};

/** Exported so tests can drive the protocol without a real worker scope. */
export const handleWorkerMessage = async (
  request: AsrWorkerRequest,
  post: (response: AsrWorkerResponse) => void,
): Promise<void> => {
  if (request.type === "init") {
    try {
      await loadPipeline(request);
      post({ type: "ready" });
    } catch (error) {
      post({ type: "init-error", message: describeError(error) });
    }
    return;
  }

  try {
    const text = await transcribe(new Float32Array(request.audio));
    post({ type: "result", id: request.id, text });
  } catch (error) {
    post({ type: "transcribe-error", id: request.id, message: describeError(error) });
  }
};

type WorkerScopeLike = {
  onmessage: ((event: MessageEvent<AsrWorkerRequest>) => void) | null;
  postMessage(message: AsrWorkerResponse): void;
};

// Wire up only inside a real dedicated worker: vitest imports this module in a
// window-like scope, and the `webworker` lib types would clash program-wide
// with `dom`, so the scope is duck-typed instead.
const scope = globalThis as Partial<WorkerScopeLike> & { window?: unknown };
if (typeof scope.window === "undefined" && typeof scope.postMessage === "function") {
  scope.onmessage = (event: MessageEvent<AsrWorkerRequest>): void => {
    void handleWorkerMessage(event.data, (response) => scope.postMessage?.(response));
  };
}
