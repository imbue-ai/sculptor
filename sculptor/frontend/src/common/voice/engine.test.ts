import { afterEach, beforeEach, describe, expect, it, type Mock, vi } from "vitest";

import type { VoiceEngine, VoiceEngineEvents, VoiceEngineState } from "./engineContract.ts";

// Hoisted mocks stay stable across the per-test `vi.resetModules()`, so the
// engine's module-level caches reset while these keep their identity.
const h = vi.hoisted(() => ({
  transcribeMock: vi.fn(),
  createAsrClient: vi.fn(),
  asrClientDead: { value: false },
  micVadNew: vi.fn(),
  micVadStart: vi.fn(),
  micVadPause: vi.fn(),
  micVadDestroy: vi.fn(),
  getSessionToken: vi.fn(),
}));

vi.mock("~/common/apiClient.ts", () => ({ baseUrl: "https://backend.test" }));
vi.mock("~/common/utils/sessionToken.ts", () => ({
  SESSION_TOKEN_HEADER_NAME: "x-session-token",
  getSessionToken: h.getSessionToken,
}));
vi.mock("./asrClient.ts", () => ({ createAsrClient: h.createAsrClient }));
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
  positiveSpeechThreshold: number;
  negativeSpeechThreshold: number;
  redemptionMs: number;
  preSpeechPadMs: number;
  minSpeechMs: number;
  onFrameProcessed: (probabilities: unknown, frame: Float32Array) => void;
  onSpeechStart: () => void;
  onVADMisfire: () => void;
  onSpeechEnd: (audio: Float32Array) => void;
};

type Recorder = {
  events: VoiceEngineEvents;
  states: Array<VoiceEngineState>;
  segments: Array<string>;
  previews: Array<string>;
  discardCount: number;
  errors: Array<{ kind: string; message: string }>;
};

const createRecorder = (): Recorder => {
  const recorder: Recorder = {
    states: [],
    segments: [],
    previews: [],
    discardCount: 0,
    errors: [],
    events: undefined as unknown as VoiceEngineEvents,
  };
  recorder.events = {
    onStateChange: (state): void => void recorder.states.push(state),
    onSegment: (text): void => void recorder.segments.push(text),
    onPreview: (text): void => void recorder.previews.push(text),
    onPreviewDiscard: (): void => {
      recorder.discardCount += 1;
    },
    onError: (error): void => void recorder.errors.push(error),
  };
  return recorder;
};

const FRAME_SAMPLES = 512;

// Marks speech start and feeds enough frames to cross the stop-flush minimum
// (but stays under the preview minimum unless `frames` says otherwise).
const speakFrames = (options: CapturedVadOptions, frames: number): void => {
  options.onSpeechStart();
  for (let index = 0; index < frames; index += 1) {
    options.onFrameProcessed({}, new Float32Array(FRAME_SAMPLES));
  }
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

  h.asrClientDead.value = false;
  h.createAsrClient.mockImplementation(() => ({
    ready: Promise.resolve(),
    get isDead(): boolean {
      return h.asrClientDead.value;
    },
    transcribe: h.transcribeMock,
    dispose: vi.fn(),
  }));
  h.transcribeMock.mockResolvedValue("");
  h.micVadNew.mockImplementation(async () => ({
    start: h.micVadStart,
    pause: h.micVadPause,
    destroy: h.micVadDestroy,
  }));
  h.micVadStart.mockResolvedValue(undefined);
  h.micVadPause.mockResolvedValue(undefined);
  h.micVadDestroy.mockResolvedValue(undefined);
  h.getSessionToken.mockReturnValue(undefined);

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
  it("spawns the ASR worker pointed at the backend models and app-served wasm", async () => {
    const engine = createVoiceEngine(createRecorder().events);

    await engine.start();

    expect(h.createAsrClient).toHaveBeenCalledWith({
      modelsBaseUrl: "https://backend.test/api/v1/voice-models/",
      wasmBaseUrl: expect.stringContaining("/vendor/voice/transformers-ort/"),
      token: null,
      tokenParam: "x-session-token",
      device: "wasm",
      dtype: "q8",
    });
  });

  it("points the VAD at the backend model and app-served wasm, not autostarting", async () => {
    const engine = createVoiceEngine(createRecorder().events);

    await engine.start();
    const options = capturedVadOptions();

    expect(options.model).toBe("v5");
    expect(options.positiveSpeechThreshold).toBe(0.5);
    expect(options.negativeSpeechThreshold).toBe(0.35);
    expect(options.redemptionMs).toBe(800);
    expect(options.preSpeechPadMs).toBe(300);
    expect(options.minSpeechMs).toBe(200);
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

  it("reuses the ASR worker across engines (warm start)", async () => {
    await createVoiceEngine(createRecorder().events).start();
    await createVoiceEngine(createRecorder().events).start();

    expect(h.createAsrClient).toHaveBeenCalledTimes(1);
  });

  it("respawns a dead ASR worker on the next start", async () => {
    const engine = createVoiceEngine(createRecorder().events);
    await engine.start();
    await engine.stop();

    h.asrClientDead.value = true;
    await engine.start();

    expect(h.createAsrClient).toHaveBeenCalledTimes(2);
  });
});

describe("createVoiceEngine error mapping", () => {
  it("maps a blocked microphone to mic-permission-denied", async () => {
    h.micVadStart.mockRejectedValueOnce(namedError("NotAllowedError", "Permission denied"));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.states).toEqual(["initializing", "idle"]);
    expect(recorder.errors).toEqual([{ kind: "mic-permission-denied", message: "Permission denied" }]);
  });

  it("maps a missing microphone device to mic-permission-denied", async () => {
    h.micVadStart.mockRejectedValueOnce(namedError("NotFoundError", "No device"));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.errors[0]?.kind).toBe("mic-permission-denied");
  });

  it("maps a model load failure to init-failed", async () => {
    h.createAsrClient.mockImplementation(() => ({
      ready: Promise.reject(new Error("network down")),
      isDead: true,
      transcribe: h.transcribeMock,
      dispose: vi.fn(),
    }));
    const recorder = createRecorder();

    await createVoiceEngine(recorder.events).start();

    expect(recorder.states).toEqual(["initializing", "idle"]);
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
    h.transcribeMock.mockResolvedValue("  hello world  ");
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const options = capturedVadOptions();
    speakFrames(options, 8);
    options.onSpeechEnd(new Float32Array(16000));
    await flush();

    expect(recorder.segments).toEqual(["hello world"]);
  });

  it("swallows empty and whitespace-only transcriptions", async () => {
    h.transcribeMock.mockResolvedValue("   ");
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const options = capturedVadOptions();
    speakFrames(options, 8);
    options.onSpeechEnd(new Float32Array(16000));
    await flush();

    expect(recorder.segments).toEqual([]);
    expect(recorder.errors).toEqual([]);
  });

  it("reports a failed transcription but keeps listening", async () => {
    h.transcribeMock.mockRejectedValue(new Error("decode failed"));
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const options = capturedVadOptions();
    speakFrames(options, 8);
    options.onSpeechEnd(new Float32Array(16000));
    await flush();

    expect(recorder.errors).toEqual([{ kind: "transcription-failed", message: "decode failed" }]);
    expect(recorder.states[recorder.states.length - 1]).toBe("listening");
  });

  it("emits a transcription that was still in flight when the engine stopped", async () => {
    let resolveTranscribe: (value: string) => void = () => undefined;
    h.transcribeMock.mockReturnValue(
      new Promise((resolve) => {
        resolveTranscribe = resolve;
      }),
    );
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const options = capturedVadOptions();
    speakFrames(options, 8);
    options.onSpeechEnd(new Float32Array(16000));
    const stopping = engine.stop();
    resolveTranscribe("late result");
    await stopping;
    await flush();

    expect(recorder.segments).toEqual(["late result"]);
    expect(recorder.states[recorder.states.length - 1]).toBe("idle");
  });
});

describe("createVoiceEngine utterance accumulation", () => {
  it("flushes the in-progress utterance as a final segment on stop", async () => {
    h.transcribeMock.mockResolvedValue("flushed words");
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const options = capturedVadOptions();
    speakFrames(options, 8);
    await engine.stop();
    await flush();

    const flushedAudio = h.transcribeMock.mock.calls[0]?.[0] as Float32Array;
    expect(flushedAudio.length).toBe(8 * FRAME_SAMPLES);
    expect(recorder.segments).toEqual(["flushed words"]);
    expect(recorder.states[recorder.states.length - 1]).toBe("idle");
  });

  it("flushes even a very short utterance, and a junk fold discards itself", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    speakFrames(capturedVadOptions(), 2);
    await engine.stop();
    await flush();

    // The blip is transcribed (the default mock returns junk-empty text) and
    // the empty final discards rather than emitting.
    expect(h.transcribeMock).toHaveBeenCalledTimes(1);
    expect(recorder.segments).toEqual([]);
    expect(recorder.previews).toEqual([]);
    expect(recorder.discardCount).toBe(1);
  });

  it("emits a throttled preview while an utterance is in progress", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(0);
    try {
      h.transcribeMock.mockResolvedValue("partial words");
      const recorder = createRecorder();
      const engine = createVoiceEngine(recorder.events);

      await engine.start();
      const options = capturedVadOptions();
      speakFrames(options, 16);
      expect(recorder.previews).toEqual([]);

      nowSpy.mockReturnValue(1000);
      options.onFrameProcessed({}, new Float32Array(FRAME_SAMPLES));
      await flush();

      expect(recorder.previews).toEqual(["partial words"]);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("keeps the preview visible until the natural final replaces it", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(0);
    try {
      h.transcribeMock.mockResolvedValue("spoken sentence");
      const recorder = createRecorder();
      const engine = createVoiceEngine(recorder.events);

      await engine.start();
      const options = capturedVadOptions();
      speakFrames(options, 16);
      nowSpy.mockReturnValue(1000);
      options.onFrameProcessed({}, new Float32Array(FRAME_SAMPLES));
      await flush();
      options.onSpeechEnd(new Float32Array(16000));
      await flush();

      // The interim preview, then the drain fold's progress preview.
      expect(recorder.previews).toEqual(["spoken sentence", "spoken sentence"]);
      expect(recorder.segments).toEqual(["spoken sentence"]);
      expect(recorder.discardCount).toBe(0);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("commits a head slice mid-turn so window transcriptions stay bounded", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(0);
    try {
      h.transcribeMock.mockResolvedValue("chunk words");
      const recorder = createRecorder();
      const engine = createVoiceEngine(recorder.events);

      await engine.start();
      const options = capturedVadOptions();
      options.onSpeechStart();
      const loudFrame = (): Float32Array => {
        const frame = new Float32Array(FRAME_SAMPLES);
        frame.fill(0.1);
        return frame;
      };
      for (let i = 0; i < 400; i += 1) options.onFrameProcessed({}, loudFrame());
      // A genuine pause: long enough to qualify as an inter-word gap.
      for (let i = 0; i < 8; i += 1) options.onFrameProcessed({}, new Float32Array(FRAME_SAMPLES));
      for (let i = 0; i < 300; i += 1) options.onFrameProcessed({}, loudFrame());
      await flush();

      // The head committed while the turn was still live, and it is bounded.
      expect(h.transcribeMock).toHaveBeenCalled();
      const head = h.transcribeMock.mock.calls[0]?.[0] as Float32Array;
      expect(head.length).toBeGreaterThan(0);
      expect(head.length).toBeLessThanOrEqual(20 * 16000);

      options.onSpeechEnd(new Float32Array(16000));
      await flush();
      // The final folds committed + drained tail; the seam de-dup collapses the
      // mock's identical chunk texts into one.
      expect(recorder.segments).toEqual(["chunk words"]);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("parks the preview while a commit fold is pending and runs it at the first idle", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(0);
    try {
      let resolveHead: (value: string) => void = () => undefined;
      h.transcribeMock.mockReturnValueOnce(
        new Promise((resolve) => {
          resolveHead = resolve;
        }),
      );
      h.transcribeMock.mockResolvedValue("late preview");
      const recorder = createRecorder();
      const engine = createVoiceEngine(recorder.events);

      await engine.start();
      const options = capturedVadOptions();
      options.onSpeechStart();
      const loudFrame = (): Float32Array => {
        const frame = new Float32Array(FRAME_SAMPLES);
        frame.fill(0.1);
        return frame;
      };
      for (let i = 0; i < 400; i += 1) options.onFrameProcessed({}, loudFrame());
      for (let i = 0; i < 8; i += 1) options.onFrameProcessed({}, new Float32Array(FRAME_SAMPLES));
      for (let i = 0; i < 300; i += 1) options.onFrameProcessed({}, loudFrame());

      // The head slice is a pending commit; the elapsed interval PARKS the
      // preview (latest capture wins) without running it.
      nowSpy.mockReturnValue(10_000);
      options.onFrameProcessed({}, loudFrame());
      await flush();
      expect(h.transcribeMock).toHaveBeenCalledTimes(1);

      // The fold settles -> the parked preview runs at the first idle moment.
      resolveHead("first chunk");
      await flush();
      expect(h.transcribeMock).toHaveBeenCalledTimes(2);
      expect(recorder.previews).toContain("first chunk");
      expect(recorder.previews[recorder.previews.length - 1]).toBe("first chunk late preview");
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("folds every slice and drain chunk with no audio lost, with progress while draining", async () => {
    const nowSpy = vi.spyOn(Date, "now").mockReturnValue(0);
    try {
      let call = 0;
      h.transcribeMock.mockImplementation(async () => {
        call += 1;
        return `part${call}`;
      });
      const recorder = createRecorder();
      const engine = createVoiceEngine(recorder.events);

      await engine.start();
      const options = capturedVadOptions();
      options.onSpeechStart();
      const loudFrame = (): Float32Array => {
        const frame = new Float32Array(FRAME_SAMPLES);
        frame.fill(0.1);
        return frame;
      };
      const totalFrames = 400 + 8 + 700;
      for (let i = 0; i < 400; i += 1) options.onFrameProcessed({}, loudFrame());
      for (let i = 0; i < 8; i += 1) options.onFrameProcessed({}, new Float32Array(FRAME_SAMPLES));
      for (let i = 0; i < 700; i += 1) options.onFrameProcessed({}, loudFrame());
      await flush();

      options.onSpeechEnd(new Float32Array(16000));
      await flush();
      await flush();

      // One pause-anchored head + a two-chunk forced-cut drain: nothing lost.
      expect(recorder.segments).toEqual(["part1 part2 part3"]);
      // The drain reported progress after its non-final fold.
      expect(recorder.previews).toContain("part1 part2");
      const transcribedSamples = h.transcribeMock.mock.calls.reduce(
        (total, callArgs) => total + (callArgs[0] as Float32Array).length,
        0,
      );
      expect(transcribedSamples).toBe(totalFrames * FRAME_SAMPLES);
    } finally {
      nowSpy.mockRestore();
    }
  });

  it("discards the preview on a VAD misfire", async () => {
    const recorder = createRecorder();
    const engine = createVoiceEngine(recorder.events);

    await engine.start();
    const options = capturedVadOptions();
    speakFrames(options, 4);
    options.onVADMisfire();

    expect(recorder.previews).toEqual([]);
    expect(recorder.discardCount).toBe(1);
    expect(recorder.segments).toEqual([]);
  });
});

describe("createVoiceEngine model fetch authentication", () => {
  const MODEL_URL = "https://backend.test/api/v1/voice-models/vad/silero_vad_v5.onnx";

  // vad-web fetches the Silero weights on the main thread during MicVAD.new;
  // drive one such fetch and observe what the patched fetch forwards to the
  // underlying one. (Moonshine's files are fetched inside the ASR worker, which
  // patches its own realm — covered by the worker's tests.)
  const loadWithFetch = async (url: string): Promise<void> => {
    h.micVadNew.mockImplementation(async () => {
      await globalThis.fetch(url);
      return { start: h.micVadStart, pause: h.micVadPause, destroy: h.micVadDestroy };
    });
    await createVoiceEngine(createRecorder().events).start();
  };

  it("appends the session token to voice-model requests during model loading", async () => {
    h.getSessionToken.mockReturnValue("secret-token");
    await loadWithFetch(MODEL_URL);

    const [url, init] = lastCall(baseFetch) as [string, RequestInit];
    expect(url).toContain("x-session-token=secret-token");
    expect(init.credentials).toBe("include");
  });

  it("leaves non voice-model requests untouched", async () => {
    h.getSessionToken.mockReturnValue("secret-token");
    await loadWithFetch("https://backend.test/api/v1/other");

    const [url, init] = lastCall(baseFetch) as [string, RequestInit | undefined];
    expect(url).toBe("https://backend.test/api/v1/other");
    expect(init).toBeUndefined();
  });

  it("relies on the same-origin cookie (no token param) for web builds", async () => {
    h.getSessionToken.mockReturnValue(undefined);
    await loadWithFetch(MODEL_URL);

    const [url, init] = lastCall(baseFetch) as [string, RequestInit];
    expect(url).toBe(MODEL_URL);
    expect(url).not.toContain("x-session-token");
    expect(init.credentials).toBe("include");
  });

  it("restores the unpatched fetch once loading settles", async () => {
    await createVoiceEngine(createRecorder().events).start();
    expect(globalThis.fetch).toBe(baseFetch);
  });
});
