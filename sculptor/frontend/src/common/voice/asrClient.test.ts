import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { AsrClient, AsrClientConfig } from "./asrClient.ts";
import type { AsrWorkerResponse } from "./asrWorker.ts";

class FakeWorker {
  static instances: Array<FakeWorker> = [];
  onmessage: ((event: { data: AsrWorkerResponse }) => void) | null = null;
  onerror: ((event: { message?: string }) => void) | null = null;
  postMessage = vi.fn();
  terminate = vi.fn();
  constructor() {
    FakeWorker.instances.push(this);
  }
  emit(response: AsrWorkerResponse): void {
    this.onmessage?.({ data: response });
  }
}

const CONFIG = {
  modelsBaseUrl: "https://backend.test/api/v1/voice-models/",
  wasmBaseUrl: "https://app.test/vendor/voice/transformers-ort/",
  token: null,
  tokenParam: "x-session-token",
};

let createAsrClient: (config: AsrClientConfig) => AsrClient;

const makeClient = (): { client: AsrClient; worker: FakeWorker } => {
  const client = createAsrClient(CONFIG);
  const worker = FakeWorker.instances[FakeWorker.instances.length - 1];
  return { client, worker };
};

beforeEach(async () => {
  vi.resetModules();
  FakeWorker.instances = [];
  vi.stubGlobal("Worker", FakeWorker);
  ({ createAsrClient } = await import("./asrClient.ts"));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createAsrClient", () => {
  it("sends init with the config and resolves ready on the worker's ready", async () => {
    const { client, worker } = makeClient();

    expect(worker.postMessage).toHaveBeenCalledWith({ type: "init", ...CONFIG });
    worker.emit({ type: "ready" });

    await expect(client.ready).resolves.toBeUndefined();
    expect(client.isDead).toBe(false);
  });

  it("transfers audio buffers and resolves the matching result", async () => {
    const { client, worker } = makeClient();
    worker.emit({ type: "ready" });

    const request = client.transcribe(new Float32Array([1, 2, 3]));

    const [message, transfer] = worker.postMessage.mock.calls[1] as [
      { type: string; id: number; audio: ArrayBuffer },
      Array<ArrayBuffer>,
    ];
    expect(message.type).toBe("transcribe");
    expect(transfer).toEqual([message.audio]);

    worker.emit({ type: "result", id: message.id, text: "spoken" });
    await expect(request).resolves.toBe("spoken");
  });

  it("rejects the matching request on a transcribe error without dying", async () => {
    const { client, worker } = makeClient();
    worker.emit({ type: "ready" });

    const request = client.transcribe(new Float32Array(4));
    const [message] = worker.postMessage.mock.calls[1] as [{ id: number }];
    worker.emit({ type: "transcribe-error", id: message.id, message: "decode failed" });

    await expect(request).rejects.toThrow("decode failed");
    expect(client.isDead).toBe(false);
  });

  it("dies on init-error: ready rejects and the worker terminates", async () => {
    const { client, worker } = makeClient();

    worker.emit({ type: "init-error", message: "no model" });

    await expect(client.ready).rejects.toThrow("no model");
    expect(client.isDead).toBe(true);
    expect(worker.terminate).toHaveBeenCalledTimes(1);
  });

  it("dies on a worker crash: pending requests reject and later ones refuse", async () => {
    const { client, worker } = makeClient();
    worker.emit({ type: "ready" });
    await client.ready;

    const pending = client.transcribe(new Float32Array(4));
    worker.onerror?.({ message: "boom" });

    await expect(pending).rejects.toThrow("boom");
    expect(client.isDead).toBe(true);
    expect(worker.terminate).toHaveBeenCalledTimes(1);
    await expect(client.transcribe(new Float32Array(4))).rejects.toThrow("not running");
  });
});
