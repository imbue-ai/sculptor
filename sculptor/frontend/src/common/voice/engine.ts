// On-device speech-to-text engine: microphone -> Silero VAD v5 (@ricky0123/vad-web)
// segments speech -> each utterance streams through a StreamingTurn
// (silence-anchored commit-and-slice, see streamingTurn.ts) and is transcribed
// by Moonshine base (onnx-community/moonshine-base-ONNX, q8, WASM) via
// @huggingface/transformers -> emits throttled interim previews while the
// utterance is in progress and the final segment text when it ends (naturally,
// or flushed by stop()).
//
// The turn model keeps per-tick transcription work bounded: previews only ever
// re-transcribe the turn's rolling ~20 s window, and audio that slides out of
// the window is transcribed once and folded into committed words — so an
// arbitrarily long utterance never re-transcribes its whole history.
//
// The speech libraries are large, so they are pulled in only via dynamic
// `import()` at start() time and never join the initial bundle. Model weights
// come exclusively from the backend's managed voice-models endpoint; the ONNX
// Runtime wasm and the VAD audio worklet are code that ships with the app.
//
// Per-utterance event protocol (surfaces rely on this):
//   - onPreview(text): show/replace the interim preview (always non-empty).
//   - onPreviewDiscard(): the utterance produced no final (misfire, too short
//     at stop, or transcription failure) — discard the preview.
//   - onSegment(text): the utterance's final text; replaces any shown preview.
//     A successful finalize does NOT emit onPreviewDiscard() first, so the
//     preview stays visible as a bridge until the final lands.

import type { MicVAD } from "@ricky0123/vad-web";

import { baseUrl } from "~/apiClient.ts";
import { getSessionToken, SESSION_TOKEN_HEADER_NAME } from "~/common/Auth.ts";

import { StreamingTurn } from "./streamingTurn.ts";
import type { VoiceEngine, VoiceEngineEvents, VoiceEngineState, VoiceErrorKind } from "./types.ts";

type AsrOutput = { text: string };
type AsrTranscriber = (audio: Float32Array) => Promise<AsrOutput | Array<AsrOutput>>;

const MOONSHINE_MODEL_ID = "onnx-community/moonshine-base-ONNX";
const VAD_WORKLET_FILE = "vad.worklet.bundle.min.js";

// How often the live preview refreshes (each refresh transcribes the window).
const PREVIEW_INTERVAL_MS = 500;
// Below ~a third of a second of audio an interim transcription is mostly noise.
const PREVIEW_MIN_SAMPLES = 4800;
// A stop()-flush shorter than this (with nothing committed) is a click, not speech.
const MIN_FLUSH_SAMPLES = 4000;
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
// session is not re-entrant, a preview must never race a final, and commit
// folds must land in slice order (FIFO gives that for free).
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

  let preroll: Array<Float32Array> = [];
  let activeTurn: StreamingTurn | null = null;
  // The finalize of the most recent naturally-ended turn, so stop() can wait
  // for THIS engine's own final — never the shared chain, which may be busy
  // with another engine's work.
  let pendingFinalize: Promise<void> | null = null;
  let lastPreviewAt = 0;
  let isPreviewInFlight = false;

  const setState = (next: VoiceEngineState): void => {
    state = next;
    events.onStateChange(next);
  };

  const fail = (kind: VoiceErrorKind, error: unknown): void => {
    setState("idle");
    events.onError({ kind, message: describeError(error) });
  };

  const abortTurn = (): void => {
    const didHaveTurn = activeTurn !== null;
    activeTurn = null;
    if (didHaveTurn) {
      events.onPreviewDiscard();
    }
  };

  const beginTurn = (): void => {
    const turn = new StreamingTurn();
    for (const frame of preroll) {
      turn.addFrame(frame);
    }
    preroll = [];
    activeTurn = turn;
    // The first preview waits one full interval from speech start.
    lastPreviewAt = Date.now();
  };

  // Transcribe a head slice and fold it into the turn's committed words. A
  // failed fold loses only that chunk's words; the turn keeps going and the
  // seam de-dup keeps the next fold safe.
  const commitHeadSlice = async (turn: StreamingTurn, head: Float32Array): Promise<void> => {
    const runId = currentRunId;
    try {
      const text = await transcribeSerialized(head);
      if (runId !== currentRunId) return;
      turn.commitText(text);
      if (turn === activeTurn) {
        events.onPreview(turn.liveText);
      }
    } catch (error) {
      if (runId === currentRunId) {
        events.onError({ kind: "transcription-failed", message: describeError(error) });
      }
    }
  };

  const maybePreview = (): void => {
    const turn = activeTurn;
    if (turn === null || isPreviewInFlight || turn.bufferedSamples < PREVIEW_MIN_SAMPLES) return;
    if (Date.now() - lastPreviewAt < PREVIEW_INTERVAL_MS) return;
    const { audio, epoch } = turn.windowAudio();
    const runId = currentRunId;
    isPreviewInFlight = true;
    lastPreviewAt = Date.now();
    transcribeSerialized(audio)
      .then((text): void => {
        if (runId !== currentRunId || turn !== activeTurn) return;
        // A slice between capture and result bumps the epoch; the stale
        // hypothesis is ignored inside the turn.
        turn.applyHypothesis(text, epoch);
        const live = turn.liveText;
        if (live.length > 0) {
          events.onPreview(live);
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
    const turn = activeTurn;
    if (turn === null) {
      preroll.push(copy);
      if (preroll.length > PREROLL_FRAMES) {
        preroll.shift();
      }
      return;
    }
    turn.addFrame(copy);
    const head = turn.takeHeadSlice();
    if (head !== null) {
      void commitHeadSlice(turn, head);
    }
    maybePreview();
  };

  // End of turn: drain the window as pause-anchored chunks, fold each, and emit
  // the committed text as the final segment. A chunk that fails to transcribe
  // reports once and is skipped — the rest of the turn still lands.
  const finalizeTurn = async (turn: StreamingTurn): Promise<void> => {
    const runId = currentRunId;
    let didReportError = false;
    for (const chunk of turn.drainChunks()) {
      try {
        const text = await transcribeSerialized(chunk);
        if (runId !== currentRunId) return;
        turn.commitText(text);
      } catch (error) {
        if (runId !== currentRunId) return;
        if (!didReportError) {
          didReportError = true;
          events.onError({ kind: "transcription-failed", message: describeError(error) });
        }
      }
    }
    if (runId !== currentRunId) return;
    const final = turn.committedText;
    if (final.length > 0) {
      events.onSegment(final);
    } else {
      events.onPreviewDiscard();
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
      onFrameProcessed: (_probabilities, frame): void => {
        handleFrame(frame);
      },
      onSpeechStart: (): void => {
        beginTurn();
      },
      onVADMisfire: (): void => {
        abortTurn();
      },
      onSpeechEnd: (_audio: Float32Array): void => {
        // The turn's own frames (preroll included) are the final's audio; the
        // VAD's padded copy would re-transcribe the whole history the window
        // model already committed.
        const turn = activeTurn;
        activeTurn = null;
        if (turn !== null) {
          pendingFinalize = finalizeTurn(turn);
        }
      },
    });
    return vadInstance;
  };

  const start = async (): Promise<void> => {
    if (isDisposed || state === "initializing" || state === "listening" || state === "stopping") return;
    preroll = [];
    activeTurn = null;
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
    // so the VAD never delivers that last utterance — flush the turn's audio
    // instead of discarding it.
    const turn = activeTurn;
    activeTurn = null;
    const shouldFlush = turn !== null && (turn.committedWordCount > 0 || turn.bufferedSamples >= MIN_FLUSH_SAMPLES);
    if (turn !== null && !shouldFlush) {
      events.onPreviewDiscard();
    }
    releaseCapture();
    if (turn !== null && shouldFlush) {
      await finalizeTurn(turn);
    } else if (pendingFinalize !== null) {
      // Let this engine's natural final that was already finalizing settle
      // before idling.
      await pendingFinalize;
    }
    setState("idle");
  };

  const dispose = (): void => {
    isDisposed = true;
    currentRunId += 1;
    // Silent cleanup — the owning surface is unmounting, so no events.
    activeTurn = null;
    preroll = [];
    releaseCapture();
  };

  return { start, stop, dispose };
};
