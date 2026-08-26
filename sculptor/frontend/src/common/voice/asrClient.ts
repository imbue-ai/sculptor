// The main-thread handle on the ASR worker: init handshake, one-at-a-time
// transcribe RPC (the engine's FIFO chain guarantees a single outstanding
// request), and death detection. A dead client stays dead — the engine drops it
// and spawns a fresh one, reloading the pipeline (local-vocal's worker-reload
// pattern).

import type { AsrWorkerInit, AsrWorkerResponse } from "./asrWorker.ts";

export type AsrClientConfig = Omit<AsrWorkerInit, "type">;

export type AsrClient = {
  /** Resolves once the worker's pipeline is loaded; rejects on init failure. */
  ready: Promise<void>;
  isDead: boolean;
  transcribe(audio: Float32Array): Promise<string>;
  dispose(): void;
};

type PendingRequest = { resolve: (text: string) => void; reject: (error: Error) => void };

export const createAsrClient = (config: AsrClientConfig): AsrClient => {
  const worker = new Worker(new URL("./asrWorker.ts", import.meta.url), { type: "module" });
  const pending = new Map<number, PendingRequest>();
  let nextId = 0;
  let resolveReady: () => void = () => undefined;
  let rejectReady: (error: Error) => void = () => undefined;

  const client: AsrClient = {
    ready: new Promise<void>((resolve, reject) => {
      resolveReady = resolve;
      rejectReady = reject;
    }),
    isDead: false,
    transcribe(audio: Float32Array): Promise<string> {
      if (client.isDead) {
        return Promise.reject(new Error("ASR worker is not running"));
      }
      nextId += 1;
      const id = nextId;
      const request = new Promise<string>((resolve, reject) => {
        pending.set(id, { resolve, reject });
      });
      worker.postMessage({ type: "transcribe", id, audio: audio.buffer }, [audio.buffer]);
      return request;
    },
    dispose(): void {
      die(new Error("ASR worker disposed"));
    },
  };

  const die = (error: Error): void => {
    if (client.isDead) return;
    client.isDead = true;
    worker.terminate();
    rejectReady(error);
    for (const request of pending.values()) {
      request.reject(error);
    }
    pending.clear();
  };

  worker.onerror = (event): void => {
    die(new Error(event.message || "ASR worker crashed"));
  };

  worker.onmessage = (event: MessageEvent<AsrWorkerResponse>): void => {
    const response = event.data;
    switch (response.type) {
      case "ready":
        resolveReady();
        break;
      case "init-error":
        die(new Error(response.message));
        break;
      case "result":
        pending.get(response.id)?.resolve(response.text);
        pending.delete(response.id);
        break;
      case "transcribe-error":
        pending.get(response.id)?.reject(new Error(response.message));
        pending.delete(response.id);
        break;
    }
  };

  worker.postMessage({ type: "init", ...config } satisfies AsrWorkerInit);
  return client;
};
