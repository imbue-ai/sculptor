// On-device speech-to-text engine: microphone -> Silero VAD v5 (@ricky0123/vad-web)
// segments speech -> each utterance is transcribed by Moonshine base
// (onnx-community/moonshine-base-ONNX, q8, WASM) via @huggingface/transformers ->
// emits throttled interim previews while the utterance is in progress and the
// final segment text when it ends (naturally, or flushed by stop()).
//
// The speech libraries are large, so they are pulled in only via dynamic
// `import()` at start() time and never join the initial bundle. Model weights
// come exclusively from the backend's managed voice-models endpoint; the ONNX
// Runtime wasm and the VAD audio worklet are code that ships with the app.
//
// Per-utterance event protocol (surfaces rely on this):
//   - onPreview(text) with text.length > 0: show/replace the interim preview.
//   - onPreview(""): the utterance produced no final (misfire, too short at
//     stop, or transcription failure) — discard the preview.
//   - onSegment(text): the utterance's final text; replaces any shown preview.
//     A successful finalize does NOT emit onPreview("") first, so the preview
//     stays visible as a bridge until the final lands.

import type { MicVAD } from "@ricky0123/vad-web";

import { baseUrl } from "~/apiClient.ts";
import { getSessionToken, SESSION_TOKEN_HEADER_NAME } from "~/common/Auth.ts";

import type { VoiceEngine, VoiceEngineEvents, VoiceEngineState, VoiceErrorKind } from "./types.ts";

type AsrOutput = { text: string };
type AsrTranscriber = (audio: Float32Array) => Promise<AsrOutput | Array<AsrOutput>>;

const MOONSHINE_MODEL_ID = "onnx-community/moonshine-base-ONNX";
const VAD_WORKLET_FILE = "vad.worklet.bundle.min.js";

const PREVIEW_INTERVAL_MS = 900;
// Below ~half a second of audio an interim transcription is mostly noise.
const PREVIEW_MIN_SAMPLES = 8000;
// A stop()-flush shorter than this is a click or breath, not speech.
const MIN_FLUSH_SAMPLES = 4000;
// Moonshine degrades beyond ~30 s of context; keep only the newest audio.
const MAX_UTTERANCE_SAMPLES = 16000 * 30;
// Pre-speech ring kept so an utterance's first syllable survives VAD detection
// latency (~0.5 s at 512-sample/16 kHz frames), mirroring vad-web's own padding.
const PREROLL_FRAMES = 16;

/** App-served runtime code (ONNX Runtime wasm + VAD worklet), respecting the app base path. */
const appAssetBase = (): string =>
  new URL(`${import.meta.env.BASE_URL || "/"}vendor/voice/`, window.location.href).href;

/** Backend-served managed model weights (Moonshine + Silero). Never a CDN. */
const voiceModelsBase = (): string => new URL(`${baseUrl}/api/v1/voice-models/`, window.location.href).href;

// The compiled Moonshine pipeline is cached at module scope so a later start() —
// even from a freshly created engine — is warm.
let sharedTranscriber: AsrTranscriber | undefined;
let isFetchAuthInstalled = false;

// Every pipeline call is serialized through one module-level chain: the wasm
// session is not re-entrant, and a preview must never race a final (or another
// engine instance).
let sharedTranscribeChain: Promise<unknown> = Promise.resolve();

const transcribeSerialized = (audio: Float32Array): Promise<string> => {
  const run = async (): Promise<string> => {
    const transcriber = sharedTranscriber;
    if (transcriber === undefined) return "";
    const output = await transcriber(audio);
    const result = Array.isArray(output) ? output[0] : output;
    return (result?.text ?? "").trim();
  };
  const next = sharedTranscribeChain.then(run, run);
  sharedTranscribeChain = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
};

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
  // Bumped on dispose() so nothing emits into an unmounted surface. Deliberately
  // NOT bumped on stop(): a transcription still in flight then is wanted output.
  let currentRunId = 0;
  let isDisposed = false;

  // The in-progress utterance, accumulated from VAD frames so it can be
  // preview-transcribed while being spoken and flushed if the user stops
  // mid-utterance (the VAD only delivers onSpeechEnd audio after a silence gap).
  let preroll: Array<Float32Array> = [];
  let utterance: Array<Float32Array> | null = null;
  let utteranceSamples = 0;
  let utteranceId = 0;
  let lastPreviewAt = 0;
  let isPreviewInFlight = false;

  const setState = (next: VoiceEngineState): void => {
    state = next;
    events.onStateChange(next);
  };

  const fail = (kind: VoiceErrorKind, error: unknown): void => {
    setState("error");
    events.onError({ kind, message: describeError(error) });
  };

  const concatUtterance = (): Float32Array => {
    const chunks = utterance ?? [];
    const joined = new Float32Array(utteranceSamples);
    let offset = 0;
    for (const chunk of chunks) {
      joined.set(chunk, offset);
      offset += chunk.length;
    }
    return joined;
  };

  const clearUtterance = (): void => {
    utterance = null;
    utteranceSamples = 0;
    utteranceId += 1;
  };

  const abortUtterance = (): void => {
    const didHaveUtterance = utterance !== null;
    clearUtterance();
    if (didHaveUtterance) {
      events.onPreview("");
    }
  };

  const beginUtterance = (): void => {
    utterance = [...preroll];
    utteranceSamples = utterance.reduce((total, chunk) => total + chunk.length, 0);
    preroll = [];
    utteranceId += 1;
    // The first preview waits one full interval from speech start.
    lastPreviewAt = Date.now();
  };

  const maybePreview = (): void => {
    if (isPreviewInFlight || utterance === null || utteranceSamples < PREVIEW_MIN_SAMPLES) return;
    if (Date.now() - lastPreviewAt < PREVIEW_INTERVAL_MS) return;
    const id = utteranceId;
    const runId = currentRunId;
    isPreviewInFlight = true;
    lastPreviewAt = Date.now();
    transcribeSerialized(concatUtterance())
      .then((text): void => {
        // Stale previews (utterance ended or engine disposed meanwhile) are dropped.
        if (runId === currentRunId && id === utteranceId && text.length > 0) {
          events.onPreview(text);
        }
      })
      .catch((): void => undefined)
      .finally((): void => {
        isPreviewInFlight = false;
      });
  };

  const handleFrame = (frame: Float32Array): void => {
    // vad-web reuses its frame buffers; copy before retaining.
    const copy = new Float32Array(frame);
    if (utterance === null) {
      preroll.push(copy);
      if (preroll.length > PREROLL_FRAMES) {
        preroll.shift();
      }
      return;
    }
    utterance.push(copy);
    utteranceSamples += copy.length;
    while (utteranceSamples > MAX_UTTERANCE_SAMPLES && utterance.length > 1) {
      utteranceSamples -= utterance[0].length;
      utterance.shift();
    }
    maybePreview();
  };

  const emitFinal = async (audio: Float32Array): Promise<void> => {
    const runId = currentRunId;
    let text: string;
    try {
      text = await transcribeSerialized(audio);
    } catch (error) {
      if (runId === currentRunId) {
        // A failed finalize surfaces an error and discards the shown preview.
        events.onError({ kind: "transcription-failed", message: describeError(error) });
        events.onPreview("");
      }
      return;
    }
    if (runId !== currentRunId) return;
    if (text.length > 0) {
      events.onSegment(text);
    } else {
      events.onPreview("");
    }
  };

  const finalizeUtterance = (audio: Float32Array): void => {
    // Clear silently: the shown preview stays visible until the final replaces it.
    clearUtterance();
    void emitFinal(audio);
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
      onFrameProcessed: (_probabilities, frame): void => {
        handleFrame(frame);
      },
      onSpeechStart: (): void => {
        beginUtterance();
      },
      onVADMisfire: (): void => {
        abortUtterance();
      },
      onSpeechEnd: (audio: Float32Array): void => {
        // Prefer the VAD's own audio for the natural-end final: it carries the
        // library's canonical pre/post padding.
        finalizeUtterance(audio);
      },
    });
    return vadInstance;
  };

  const start = async (): Promise<void> => {
    if (isDisposed || state === "initializing" || state === "listening" || state === "stopping") return;
    preroll = [];
    clearUtterance();
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
      // would then silently process nothing.
      if (audioContext !== undefined && audioContext.state === "suspended") {
        await audioContext.resume();
      }
    } catch (error) {
      fail(isMicrophonePermissionError(error) ? "mic-permission-denied" : "init-failed", error);
      return;
    }
    setState("listening");
  };

  // Fully release the microphone: vad-web's pause() keeps the MediaStream (and
  // the OS mic indicator) live, so stopping destroys the VAD and closes the
  // AudioContext instead; the next start() rebuilds them.
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
    // The user usually clicks stop right after speaking, before any silence gap,
    // so the VAD never delivers that last utterance — flush our accumulated copy
    // instead of discarding it.
    const flushAudio = utterance !== null && utteranceSamples >= MIN_FLUSH_SAMPLES ? concatUtterance() : null;
    if (flushAudio !== null) {
      clearUtterance();
    } else {
      abortUtterance();
    }
    releaseCapture();
    if (flushAudio !== null) {
      await emitFinal(flushAudio);
    } else {
      // Let a natural final that was already transcribing settle before idling.
      await sharedTranscribeChain.then(
        () => undefined,
        () => undefined,
      );
    }
    setState("idle");
  };

  const dispose = (): void => {
    isDisposed = true;
    currentRunId += 1;
    // Silent cleanup — the owning surface is unmounting, so no events.
    utterance = null;
    utteranceSamples = 0;
    releaseCapture();
  };

  return { start, stop, dispose };
};
