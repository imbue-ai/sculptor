// On-device speech-to-text engine: microphone -> Silero VAD v5 (@ricky0123/vad-web)
// segments speech -> each finished segment is transcribed by Moonshine base
// (onnx-community/moonshine-base-ONNX, q8, WASM) via @huggingface/transformers ->
// emits the segment text.
//
// The speech libraries are large, so they are pulled in only via dynamic
// `import()` at start() time and never join the initial bundle. Model weights
// come exclusively from the backend's managed voice-models endpoint; the ONNX
// Runtime wasm and the VAD audio worklet are code that ships with the app.

// `import type` is erased at build, so this carries no runtime dependency on the
// (large) speech libraries — they are loaded lazily via dynamic import() below.
import type { MicVAD } from "@ricky0123/vad-web";

import { baseUrl } from "~/apiClient.ts";
import { getSessionToken, SESSION_TOKEN_HEADER_NAME } from "~/common/Auth.ts";

import type { VoiceEngine, VoiceEngineEvents, VoiceEngineState, VoiceErrorKind } from "./types.ts";

type AsrOutput = { text: string };
type AsrTranscriber = (audio: Float32Array) => Promise<AsrOutput | Array<AsrOutput>>;

const MOONSHINE_MODEL_ID = "onnx-community/moonshine-base-ONNX";
const VAD_WORKLET_FILE = "vad.worklet.bundle.min.js";

/** App-served runtime code (ONNX Runtime wasm + VAD worklet), respecting the app base path. */
const appAssetBase = (): string =>
  new URL(`${import.meta.env.BASE_URL || "/"}vendor/voice/`, window.location.href).href;

/** Backend-served managed model weights (Moonshine + Silero). Never a CDN. */
const voiceModelsBase = (): string => new URL(`${baseUrl}/api/v1/voice-models/`, window.location.href).href;

// The compiled Moonshine pipeline is cached at module scope so a later start() —
// even from a freshly created engine — is warm. (Dynamic import() is itself
// memoized by the module system, so the libraries need no separate caching.)
let sharedTranscriber: AsrTranscriber | undefined;
let isFetchAuthInstalled = false;

const extractRequestUrl = (input: RequestInfo | URL): string => {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
};

const authenticateVoiceModelUrl = (url: string): string => {
  const token = getSessionToken();
  // Web builds are same-origin and ride the SameSite session cookie, so there is
  // no token to add. Packaged Electron is cross-origin (the cookie is
  // SameSite=strict), so it must pass the token as a query param instead.
  if (token === undefined) return url;
  const resolved = new URL(url, window.location.href);
  if (!resolved.searchParams.has(SESSION_TOKEN_HEADER_NAME)) {
    resolved.searchParams.set(SESSION_TOKEN_HEADER_NAME, token);
  }
  return resolved.href;
};

// The speech libraries fetch model weights with a bare fetch() that carries no
// session token, but GET /api/v1/voice-models/* sits behind the /api guard.
// Intercept only voice-model requests to attach auth; every other fetch passes
// through untouched.
const installVoiceModelFetchAuth = (modelsBase: string): void => {
  if (isFetchAuthInstalled) return;
  isFetchAuthInstalled = true;
  const originalFetch = globalThis.fetch.bind(globalThis);
  globalThis.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (!extractRequestUrl(input).startsWith(modelsBase)) {
      return originalFetch(input, init);
    }
    return originalFetch(authenticateVoiceModelUrl(extractRequestUrl(input)), { ...init, credentials: "include" });
  };
};

const ensureTranscriber = async (): Promise<AsrTranscriber> => {
  if (sharedTranscriber !== undefined) return sharedTranscriber;
  const transformers = await import("@huggingface/transformers");
  transformers.env.allowLocalModels = false;
  transformers.env.remoteHost = voiceModelsBase();
  // The default wasmPaths points at jsDelivr; serve the wasm from our own origin.
  // The ONNX backend populates `wasm` when the module loads, so it is defined here.
  const wasm = transformers.env.backends.onnx.wasm;
  if (wasm !== undefined) {
    wasm.wasmPaths = `${appAssetBase()}transformers-ort/`;
    wasm.numThreads = 1;
  }
  installVoiceModelFetchAuth(voiceModelsBase());
  // The explicit task type argument keeps `pipeline`'s return from widening into
  // the whole-task union (which TS reports as "too complex to represent").
  sharedTranscriber = await transformers.pipeline<"automatic-speech-recognition">(
    "automatic-speech-recognition",
    MOONSHINE_MODEL_ID,
    { dtype: "q8", device: "wasm" },
  );
  return sharedTranscriber;
};

// vad-web derives both the worklet URL and the Silero model URL from a single
// `baseAssetPath`, which we point at the backend so the weights load from there.
// The worklet is app-shipped code, so redirect that one request to the bundled
// copy through an AudioContext we own.
const createWorkletRedirectingAudioContext = (appWorkletUrl: string): AudioContext => {
  const audioContext = new AudioContext();
  const audioWorklet = audioContext.audioWorklet;
  const addModule = audioWorklet.addModule.bind(audioWorklet);
  audioWorklet.addModule = (moduleUrl: string | URL, options?: WorkletOptions): Promise<void> => {
    const requested = typeof moduleUrl === "string" ? moduleUrl : moduleUrl.href;
    return addModule(requested.endsWith(VAD_WORKLET_FILE) ? appWorkletUrl : moduleUrl, options);
  };
  return audioContext;
};

const getErrorName = (error: unknown): string | undefined =>
  typeof error === "object" && error !== null && "name" in error && typeof error.name === "string"
    ? error.name
    : undefined;

const describeError = (error: unknown): string =>
  error instanceof Error ? error.message : typeof error === "string" ? error : "Unknown error";

// getUserMedia rejects with these when the user blocks the mic or has no device.
const isMicrophonePermissionError = (error: unknown): boolean => {
  const name = getErrorName(error);
  return name === "NotAllowedError" || name === "NotFoundError";
};

export const createVoiceEngine = (events: VoiceEngineEvents): VoiceEngine => {
  let state: VoiceEngineState = "idle";
  let vadInstance: MicVAD | undefined;
  let audioContext: AudioContext | undefined;
  // Bumped on every stop()/dispose() so a transcription that was already in
  // flight is discarded rather than emitted after the engine stopped listening.
  let currentRunId = 0;
  let isDisposed = false;

  const setState = (next: VoiceEngineState): void => {
    state = next;
    events.onStateChange(next);
  };

  const fail = (kind: VoiceErrorKind, error: unknown): void => {
    setState("error");
    events.onError({ kind, message: describeError(error) });
  };

  const handleSegmentAudio = async (audio: Float32Array): Promise<void> => {
    const runId = currentRunId;
    const transcriber = sharedTranscriber;
    if (transcriber === undefined || state !== "listening") return;
    let output: AsrOutput | Array<AsrOutput>;
    try {
      output = await transcriber(audio);
    } catch (error) {
      // A single failed transcription surfaces an error but keeps listening.
      if (runId === currentRunId && state === "listening") {
        events.onError({ kind: "transcription-failed", message: describeError(error) });
      }
      return;
    }
    if (runId !== currentRunId || state !== "listening") return;
    const result = Array.isArray(output) ? output[0] : output;
    const text = (result?.text ?? "").trim();
    if (text.length > 0) {
      events.onSegment(text);
    }
  };

  const ensureVad = async (): Promise<MicVAD> => {
    if (vadInstance !== undefined) return vadInstance;
    const vad = await import("@ricky0123/vad-web");
    audioContext = createWorkletRedirectingAudioContext(`${appAssetBase()}vad/${VAD_WORKLET_FILE}`);
    vadInstance = await vad.MicVAD.new({
      model: "v5",
      baseAssetPath: `${voiceModelsBase()}vad/`,
      onnxWASMBasePath: `${appAssetBase()}vad-ort/`,
      audioContext,
      startOnLoad: false,
      ortConfig: (ort): void => {
        ort.env.wasm.numThreads = 1;
      },
      onSpeechEnd: (audio: Float32Array): void => {
        void handleSegmentAudio(audio);
      },
    });
    return vadInstance;
  };

  const start = async (): Promise<void> => {
    if (isDisposed || state === "initializing" || state === "listening") return;
    setState("initializing");
    let vad: MicVAD;
    try {
      await ensureTranscriber();
      vad = await ensureVad();
    } catch (error) {
      fail("init-failed", error);
      return;
    }
    if (isDisposed) return;
    try {
      await vad.start();
      // A click's transient user activation can expire during a long cold init,
      // leaving the AudioContext suspended under autoplay policy — and the VAD
      // would then silently process nothing. Resume explicitly; a refusal here
      // surfaces as init-failed instead of a dead "listening" state.
      if (audioContext !== undefined && audioContext.state === "suspended") {
        await audioContext.resume();
      }
    } catch (error) {
      fail(isMicrophonePermissionError(error) ? "mic-permission-denied" : "init-failed", error);
      return;
    }
    setState("listening");
  };

  // Fully release the microphone. vad-web's pause() keeps the MediaStream (and
  // the OS mic indicator) live, so stopping destroys the VAD and closes the
  // AudioContext instead; the next start() rebuilds them. The expensive part —
  // the Moonshine pipeline — stays cached at module scope, so restarts are warm.
  const releaseCapture = (): void => {
    if (vadInstance !== undefined) {
      void vadInstance.destroy().catch(() => undefined);
      vadInstance = undefined;
    }

    // vad-web never closes a caller-supplied AudioContext, so we own its teardown.
    if (audioContext !== undefined) {
      void audioContext.close().catch(() => undefined);
      audioContext = undefined;
    }
  };

  const stop = async (): Promise<void> => {
    if (state !== "listening") return;
    setState("stopping");
    currentRunId += 1;
    releaseCapture();
    setState("idle");
  };

  const dispose = (): void => {
    isDisposed = true;
    currentRunId += 1;
    releaseCapture();
  };

  return { start, stop, dispose };
};
