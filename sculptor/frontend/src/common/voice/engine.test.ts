import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";

import type { VoiceEngine, VoiceEngineEvents, VoiceEngineState } from "./types.ts";

// Hoisted mocks stay stable across the per-test `vi.resetModules()`, so the
// engine's module-level caches reset while these keep their identity.
const h = vi.hoisted(() => ({
  pipelineMock: vi.fn(),
  transcribeMock: vi.fn(),
  micVadNew: vi.fn(),
  micVadStart: vi.fn(),
  micVadPause: vi.fn(),
  micVadDestroy: vi.fn(),
  getSessionToken: vi.fn(),
  env: {
    allowLocalModels: true,
    remoteHost: "",
    remotePathTemplate: "{model}/resolve/{revision}/",
    backends: { onnx: { wasm: {} as { wasmPaths?: string; numThreads?: number } } },
  },
}));

vi.mock("~/apiClient.ts", () => ({ baseUrl: "https://backend.test" }));
vi.mock("~/common/Auth.ts", () => ({
  SESSION_TOKEN_HEADER_NAME: "x-session-token",
  getSessionToken: h.getSessionToken,
}));
vi.mock("@huggingface/transformers", () => ({ pipeline: h.pipelineMock, env: h.env }));
vi.mock("@ricky0123/vad-web", () => ({ MicVAD: { new: h.micVadNew } }));

// jsdom has no Web Audio; the engine touches audioWorklet.addModule, state,
// resume, and close.
class MockAudioContext {
  static lastAddModule: Mock = vi.fn();
  // The state a newly constructed context reports; tests set "suspended" to
  // exercise the autoplay-policy resume guard.
  static nextState: AudioContextState = "running";
  audioWorklet: { addModule: Mock };
  state: AudioContextState;
  resume: Mock;
  close: Mock;
  constructor() {
    const addModule: Mock = vi.fn().mockResolvedValue(undefined);
    MockAudioContext.lastAddModule = addModule;
    this.audioWorklet = { addModule };
    this.state = MockAudioContext.nextState;
    this.resume = vi.fn().mockImplementation(async (): Promise<void> => {
      this.state = "running";
    });
    this.close = vi.fn().mockResolvedValue(undefined);
  }
}

type CapturedVadOptions = {
  model: string;
  baseAssetPath: string;
  onnxWASMBasePath: string;
  startOnLoad: boolean;
  audioContext: MockAudioContext;
  onSpeechEnd: (audio: Float32Array) => void;
};

type Recorder = {
  events: VoiceEngineEvents;
  states: Array<VoiceEngineState>;
  segments: Array<string>;
  errors: Array<{ kind: string; message: string }>;
};

const createRecorder = (): Recorder => {
  const states: Array<VoiceEngineState> = [];
  const segments: Array<string> = [];
  const errors: Array<{ kind: string; message: string }> = [];
  return {
    states,
    segments,
    errors,
    events: {
      onStateChange: (state): void => void states.push(state),
      onSegment: (text): void => void segments.push(text),
      onError: (error): void => void errors.push(error),
    },
  };
};

// One macrotask flush drains the transcription microtask chain kicked off by
// onSpeechEnd (which returns void, so it cannot be awaited directly).
const flush = (): Promise<void> => new Promise((resolve) => setTimeout(resolve, 0));

const capturedVadOptions = (): CapturedVadOptions => h.micVadNew.mock.calls[0]?.[0] as CapturedVadOptions;

const lastCall = (mock: Mock): Array<unknown> => mock.mock.calls[mock.mock.calls.length - 1] ?? [];

const namedError = (name: string, message: string): Error => Object.assign(new Error(message), { name });

let createVoiceEngine: (events: VoiceEngineEvents) => VoiceEngine;
let baseFetch: Mock;

beforeEach(async () => {
  vi.resetModules();
  vi.resetAllMocks();

  h.pipelineMock.mockResolvedValue(h.transcribeMock);
  h.transcribeMock.mockResolvedValue({ text: "" });
  h.micVadNew.mockImplementation(async () => ({
    start: h.micVadStart,
    pause: h.micVadPause,
    destroy: h.micVadDestroy,
  }));
  h.micVadStart.mockResolvedValue(undefined);
  h.micVadPause.mockResolvedValue(undefined);
  h.micVadDestroy.mockResolvedValue(undefined);
  h.getSessionToken.mockReturnValue(undefined);
  h.env.allowLocalModels = true;
  h.env.remoteHost = "";
  h.env.backends = { onnx: { wasm: {} } };

  baseFetch = vi.fn().mockResolvedValue({ ok: true });
  MockAudioContext.nextState = "running";
  vi.stubGlobal("AudioContext", MockAudioContext);
  vi.stubGlobal("fetch", baseFetch);

  ({ createVoiceEngine } = await import("./engine.ts"));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("createVoiceEngine state machine", () => {
  it("goes idle -> initializing -> listening on start", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();

    expect(recorder.states).toEqual(["initializing", "listening"]);
    expect(h.micVadStart).toHaveBeenCalledTimes(1);
  });

  it("goes listening -> stopping -> idle on stop and releases the microphone", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const context = capturedVadOptions().audioContext;
    await engine.stop();

    expect(recorder.states).toEqual(["initializing", "listening", "stopping", "idle"]);
    expect(h.micVadDestroy).toHaveBeenCalledTimes(1);
    expect(context.close).toHaveBeenCalledTimes(1);
  });

  it("rebuilds the VAD when started again after a stop", async () => {
    const engine = createVoiceEngine(createRecorder().events);

    await engine.start();
    await engine.stop();
    await engine.start();

    expect(h.micVadNew).toHaveBeenCalledTimes(2);
    expect(h.micVadStart).toHaveBeenCalledTimes(2);
  });

  it("resumes a suspended AudioContext so the VAD is not silently dead", async () => {
    MockAudioContext.nextState = "suspended";
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();
    const context = capturedVadOptions().audioContext;

    expect(context.resume).toHaveBeenCalledTimes(1);
    expect(recorder.states).toEqual(["initializing", "listening"]);
  });

  it("ignores a redundant start() while already listening", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    await engine.start();

    expect(recorder.states).toEqual(["initializing", "listening"]);
    expect(h.micVadStart).toHaveBeenCalledTimes(1);
  });

  it("tears down the VAD and closes the audio context on dispose", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const context = capturedVadOptions().audioContext;
    engine.dispose();

    expect(h.micVadDestroy).toHaveBeenCalledTimes(1);
    expect(context.close).toHaveBeenCalledTimes(1);
  });

  it("does not start after dispose", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    engine.dispose();
    await engine.start();

    expect(recorder.states).toEqual([]);
    expect(h.micVadNew).not.toHaveBeenCalled();
  });
});

describe("createVoiceEngine model configuration", () => {
  it("loads Moonshine as q8/wasm from the backend, wasm from the app", async () => {
    const engine = createVoiceEngine(createRecorder().events);

    await engine.start();

    expect(h.pipelineMock).toHaveBeenCalledWith("automatic-speech-recognition", "onnx-community/moonshine-base-ONNX", {
      dtype: "q8",
      device: "wasm",
    });
    expect(h.env.allowLocalModels).toBe(false);
    expect(h.env.remoteHost).toBe("https://backend.test/api/v1/voice-models/");
    expect(h.env.backends.onnx.wasm.wasmPaths).toContain("/vendor/voice/transformers-ort/");
  });

  it("points the VAD at the backend model and app-served wasm, not autostarting", async () => {
    const engine = createVoiceEngine(createRecorder().events);

    await engine.start();
    const options = capturedVadOptions();

    expect(options.model).toBe("v5");
    expect(options.baseAssetPath).toBe("https://backend.test/api/v1/voice-models/vad/");
    expect(options.onnxWASMBasePath).toContain("/vendor/voice/vad-ort/");
    expect(options.startOnLoad).toBe(false);
  });

  it("redirects the VAD worklet request to the app-shipped copy", async () => {
    const engine = createVoiceEngine(createRecorder().events);
    await engine.start();
    const context = capturedVadOptions().audioContext;

    await context.audioWorklet.addModule("https://backend.test/api/v1/voice-models/vad/vad.worklet.bundle.min.js");
    expect(MockAudioContext.lastAddModule).toHaveBeenCalledWith(
      expect.stringContaining("/vendor/voice/vad/vad.worklet.bundle.min.js"),
      undefined,
    );

    await context.audioWorklet.addModule("https://cdn.example.com/other.js");
    expect(MockAudioContext.lastAddModule).toHaveBeenLastCalledWith("https://cdn.example.com/other.js", undefined);
  });

  it("reuses the cached Moonshine pipeline across engines (warm start)", async () => {
    await createVoiceEngine(createRecorder().events).start();
    await createVoiceEngine(createRecorder().events).start();

    expect(h.pipelineMock).toHaveBeenCalledTimes(1);
  });
});

describe("createVoiceEngine error mapping", () => {
  it("maps a blocked microphone to mic-permission-denied", async () => {
    h.micVadStart.mockRejectedValueOnce(namedError("NotAllowedError", "Permission denied"));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.states).toEqual(["initializing", "error"]);
    expect(recorder.errors).toEqual([{ kind: "mic-permission-denied", message: "Permission denied" }]);
  });

  it("maps a missing microphone device to mic-permission-denied", async () => {
    h.micVadStart.mockRejectedValueOnce(namedError("NotFoundError", "No device"));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.errors[0]?.kind).toBe("mic-permission-denied");
  });

  it("maps a model load failure to init-failed", async () => {
    h.pipelineMock.mockRejectedValueOnce(new Error("network down"));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.states).toEqual(["initializing", "error"]);
    expect(recorder.errors[0]?.kind).toBe("init-failed");
  });

  it("maps a non-permission mic start failure to init-failed", async () => {
    h.micVadStart.mockRejectedValueOnce(namedError("InvalidStateError", "worklet blew up"));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.errors[0]?.kind).toBe("init-failed");
  });
});

describe("createVoiceEngine segment handling", () => {
  it("emits a trimmed segment for a completed transcription", async () => {
    h.transcribeMock.mockResolvedValue({ text: "  hello world  " });
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    capturedVadOptions().onSpeechEnd(new Float32Array(16000));
    await flush();

    expect(recorder.segments).toEqual(["hello world"]);
  });

  it("swallows empty and whitespace-only transcriptions", async () => {
    h.transcribeMock.mockResolvedValue({ text: "   " });
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    capturedVadOptions().onSpeechEnd(new Float32Array(16000));
    await flush();

    expect(recorder.segments).toEqual([]);
    expect(recorder.errors).toEqual([]);
  });

  it("reports a failed transcription but keeps listening", async () => {
    h.transcribeMock.mockRejectedValue(new Error("decode failed"));
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    capturedVadOptions().onSpeechEnd(new Float32Array(16000));
    await flush();

    expect(recorder.errors).toEqual([{ kind: "transcription-failed", message: "decode failed" }]);
    expect(recorder.states[recorder.states.length - 1]).toBe("listening");
  });

  it("discards an in-flight transcription when the engine stops", async () => {
    let resolveTranscribe: (value: { text: string }) => void = () => undefined;
    h.transcribeMock.mockReturnValue(
      new Promise((resolve) => {
        resolveTranscribe = resolve;
      }),
    );
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    capturedVadOptions().onSpeechEnd(new Float32Array(16000));
    await engine.stop();
    resolveTranscribe({ text: "late result" });
    await flush();

    expect(recorder.segments).toEqual([]);
  });
});

describe("createVoiceEngine model fetch authentication", () => {
  it("appends the session token to voice-model requests when one is available", async () => {
    h.getSessionToken.mockReturnValue("secret-token");
    await createVoiceEngine(createRecorder().events).start();

    await globalThis.fetch("https://backend.test/api/v1/voice-models/onnx-community/x/resolve/main/config.json");

    const [url, init] = lastCall(baseFetch) as [string, RequestInit];
    expect(url).toContain("x-session-token=secret-token");
    expect(init.credentials).toBe("include");
  });

  it("leaves non voice-model requests untouched", async () => {
    h.getSessionToken.mockReturnValue("secret-token");
    await createVoiceEngine(createRecorder().events).start();

    await globalThis.fetch("https://backend.test/api/v1/other");

    const [url, init] = lastCall(baseFetch) as [string, RequestInit | undefined];
    expect(url).toBe("https://backend.test/api/v1/other");
    expect(init).toBeUndefined();
  });

  it("relies on the same-origin cookie (no token param) for web builds", async () => {
    h.getSessionToken.mockReturnValue(undefined);
    await createVoiceEngine(createRecorder().events).start();

    await globalThis.fetch("https://backend.test/api/v1/voice-models/vad/silero_vad_v5.onnx");

    const [url, init] = lastCall(baseFetch) as [string, RequestInit];
    expect(url).toBe("https://backend.test/api/v1/voice-models/vad/silero_vad_v5.onnx");
    expect(url).not.toContain("x-session-token");
    expect(init.credentials).toBe("include");
  });
});
