import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";

import type { AsrWorkerRequest, AsrWorkerResponse } from "./asrWorker.ts";

const h = vi.hoisted(() => ({
  pipelineMock: vi.fn(),
  transcribeMock: vi.fn(),
  env: {
    allowLocalModels: true,
    remoteHost: "",
    backends: { onnx: { wasm: {} as { wasmPaths?: string; numThreads?: number } } },
  },
}));

vi.mock("@huggingface/transformers", () => ({ pipeline: h.pipelineMock, env: h.env }));

const INIT = {
  type: "init" as const,
  modelsBaseUrl: "https://backend.test/api/v1/voice-models/",
  wasmBaseUrl: "https://app.test/vendor/voice/transformers-ort/",
  token: "secret-token",
  tokenParam: "x-session-token",
  device: "wasm" as const,
  dtype: "q8" as const,
};

let handleWorkerMessage: (request: AsrWorkerRequest, post: (response: AsrWorkerResponse) => void) => Promise<void>;
let baseFetch: Mock;
let posted: Array<AsrWorkerResponse>;

const post = (response: AsrWorkerResponse): void => void posted.push(response);

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks();
  posted = [];

  h.pipelineMock.mockResolvedValue(h.transcribeMock);
  h.transcribeMock.mockResolvedValue({ text: "" });
  h.env.allowLocalModels = true;
  h.env.remoteHost = "";
  h.env.backends = { onnx: { wasm: {} } };

  baseFetch = vi.fn().mockResolvedValue({ ok: true });
  vi.stubGlobal("fetch", baseFetch);

  ({ handleWorkerMessage } = await import("./asrWorker.ts"));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("handleWorkerMessage", () => {
  it("loads Moonshine on the requested device from the backend and reports ready", async () => {
    await handleWorkerMessage(INIT, post);

    expect(posted).toEqual([{ type: "ready" }]);
    expect(h.pipelineMock).toHaveBeenCalledWith("automatic-speech-recognition", "onnx-community/moonshine-base-ONNX", {
      dtype: INIT.dtype,
      device: INIT.device,
    });
    expect(h.env.allowLocalModels).toBe(false);
    expect(h.env.remoteHost).toBe(INIT.modelsBaseUrl);
    expect(h.env.backends.onnx.wasm.wasmPaths).toBe(INIT.wasmBaseUrl);
    expect(h.env.backends.onnx.wasm.numThreads).toBe(1);
  });

  it("authenticates voice-model fetches during load and restores fetch after", async () => {
    h.pipelineMock.mockImplementation(async () => {
      await globalThis.fetch(`${INIT.modelsBaseUrl}onnx-community/x/resolve/main/config.json`);
      return h.transcribeMock;
    });

    await handleWorkerMessage(INIT, post);

    const [url, init] = baseFetch.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("x-session-token=secret-token");
    expect(init.credentials).toBe("include");
    expect(globalThis.fetch).toBe(baseFetch);
  });

  it("falls back to wasm/q8 when the requested device fails to load", async () => {
    h.pipelineMock.mockRejectedValueOnce(new Error("webgpu load failed"));

    await handleWorkerMessage({ ...INIT, device: "webgpu", dtype: "fp32" }, post);

    expect(posted).toEqual([{ type: "ready" }]);
    expect(h.pipelineMock).toHaveBeenNthCalledWith(
      1,
      "automatic-speech-recognition",
      "onnx-community/moonshine-base-ONNX",
      { dtype: "fp32", device: "webgpu" },
    );
    expect(h.pipelineMock).toHaveBeenNthCalledWith(
      2,
      "automatic-speech-recognition",
      "onnx-community/moonshine-base-ONNX",
      { dtype: "q8", device: "wasm" },
    );
  });

  it("reports init-error when the pipeline fails to load", async () => {
    h.pipelineMock.mockRejectedValue(new Error("model missing"));

    await handleWorkerMessage(INIT, post);

    expect(posted).toEqual([{ type: "init-error", message: "model missing" }]);
  });

  it("transcribes audio and posts the trimmed text with the request id", async () => {
    h.transcribeMock.mockResolvedValue({ text: "  hello there  " });
    await handleWorkerMessage(INIT, post);

    await handleWorkerMessage({ type: "transcribe", id: 7, audio: new Float32Array(1600).buffer }, post);

    expect(posted[1]).toEqual({ type: "result", id: 7, text: "hello there" });
    const audioArg = h.transcribeMock.mock.calls[0]?.[0] as Float32Array;
    expect(audioArg.length).toBe(1600);
  });

  it("returns empty text for a transcribe before init", async () => {
    await handleWorkerMessage({ type: "transcribe", id: 1, audio: new Float32Array(16).buffer }, post);

    expect(posted).toEqual([{ type: "result", id: 1, text: "" }]);
  });

  it("reports a transcribe error with its id", async () => {
    await handleWorkerMessage(INIT, post);
    h.transcribeMock.mockRejectedValue(new Error("decode failed"));

    await handleWorkerMessage({ type: "transcribe", id: 3, audio: new Float32Array(16).buffer }, post);

    expect(posted[1]).toEqual({ type: "transcribe-error", id: 3, message: "decode failed" });
  });
});
