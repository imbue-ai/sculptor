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
// `import()` (or the lazily spawned ASR worker) at start() time and never join
// the initial bundle. Model weights come exclusively from the backend's managed
// voice-models endpoint; the ONNX Runtime wasm and the VAD audio worklet are
// code that ships with the app. Moonshine inference runs in a dedicated worker
// (asrWorker.ts) so it never blocks this thread — which also runs the UI and
// the VAD's frame processing.
//
// Per-utterance event protocol (surfaces rely on this):
//   - onPreview(text): show/replace the interim preview (always non-empty).
//   - onPreviewDiscard(): the utterance produced no final (misfire, too short
//     at stop, or transcription failure) — discard the preview.
//   - onSegment(text): the utterance's final text; replaces any shown preview.
//     A successful finalize does NOT emit onPreviewDiscard() first, so the
//     preview stays visible as a bridge until the final lands.

import type { MicVAD } from "@ricky0123/vad-web";

import { baseUrl } from "~/common/apiClient.ts";
import { getSessionToken, SESSION_TOKEN_HEADER_NAME } from "~/common/utils/sessionToken.ts";

import { type AsrClient, createAsrClient } from "./asrClient.ts";
import type { VoiceEngine, VoiceEngineEvents, VoiceEngineState, VoiceErrorKind } from "./engineContract.ts";
import { withVoiceModelFetchAuth } from "./fetchAuth.ts";
import { StreamingTurn } from "./streamingTurn.ts";

const VAD_WORKLET_FILE = "vad.worklet.bundle.min.js";

// How often the live preview refreshes (each refresh transcribes the window).
const PREVIEW_INTERVAL_MS = 500;
// Below ~a third of a second of audio an interim transcription is mostly noise.
const PREVIEW_MIN_SAMPLES = 4800;

/** App-served runtime code (ONNX Runtime wasm + VAD worklet), respecting the app base path. */
const appAssetBase = (): string =>
  new URL(`${import.meta.env.BASE_URL || "/"}vendor/voice/`, window.location.href).href;

/** Backend-served managed model weights (Moonshine + Silero). Never a CDN. */
const voiceModelsBase = (): string => new URL(`${baseUrl}/api/v1/voice-models/`, window.location.href).href;

// The ASR worker (owning the compiled Moonshine pipeline) is cached at module
// scope so a later start() — even from a freshly created engine — is warm. A
// dead worker (crash or failed init) is dropped and respawned on the next
// start(), reloading the pipeline.
let sharedAsrClient: AsrClient | undefined;

let sharedAsrClientCreation: Promise<AsrClient> | undefined;

// Pick the device on this thread: only use WebGPU if an adapter really exists
// (the worker itself falls back to wasm/q8 if the WebGPU load then fails).
const pickAsrDevice = async (): Promise<{ device: "webgpu" | "wasm"; dtype: "fp32" | "q8" }> => {
  try {
    const gpu = (navigator as Navigator & { gpu?: { requestAdapter(): Promise<unknown> } }).gpu;
    if (gpu && (await gpu.requestAdapter())) {
      return { device: "webgpu", dtype: "fp32" };
    }
  } catch {
    // No WebGPU: wasm below.
  }
  return { device: "wasm", dtype: "q8" };
};

const ensureAsrClient = async (): Promise<AsrClient> => {
  if (sharedAsrClient !== undefined && sharedAsrClient.isDead) {
    sharedAsrClient = undefined;
    sharedAsrClientCreation = undefined;
  }
  sharedAsrClientCreation ??= (async (): Promise<AsrClient> => {
    const { device, dtype } = await pickAsrDevice();
    const client = createAsrClient({
      modelsBaseUrl: voiceModelsBase(),
      wasmBaseUrl: `${appAssetBase()}transformers-ort/`,
      token: getSessionToken() ?? null,
      tokenParam: SESSION_TOKEN_HEADER_NAME,
      device,
      dtype,
    });
    sharedAsrClient = client;
    return client;
  })();
  const client = await sharedAsrClientCreation;
  await client.ready;
  return client;
};

// Every transcription is serialized through one module-level chain: the worker
// handles one request at a time, a preview must never race a final, and commit
// folds must land in slice order (FIFO gives that for free).
let sharedTranscribeChain: Promise<unknown> = Promise.resolve();

const transcribeSerialized = (audio: Float32Array): Promise<string> => {
  const run = async (): Promise<string> => {
    // A dead worker (crash) respawns here, so jobs already queued replay
    // against the reloaded pipeline instead of stalling until the next start.
    const client = await ensureAsrClient();
    return client.transcribe(audio);
  };
  const next = sharedTranscribeChain.then(run, run);
  sharedTranscribeChain = next.then(
    () => undefined,
    () => undefined,
  );
  return next;
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

  let activeTurn: StreamingTurn | null = null;
  // Outstanding commit folds (head slices + drain chunks); the preview lane
  // runs only while this is zero.
  let pendingCommitCount = 0;
  // The parked live-preview request: captured every interval (latest capture
  // wins, even while commits queue) and run at the first idle moment.
  let pendingInterim: { audio: Float32Array; epoch: number; turn: StreamingTurn } | null = null;
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
    pendingInterim = null;
    if (didHaveTurn) {
      events.onPreviewDiscard();
    }
  };

  const beginTurn = (): void => {
    activeTurn = new StreamingTurn();
    // The first preview waits one full interval from speech start.
    lastPreviewAt = Date.now();
  };

  // Transcribe a head slice and fold it into the turn's committed words. A
  // failed fold loses only that chunk's words; the turn keeps going and the
  // seam de-dup keeps the next fold safe.
  const commitHeadSlice = async (turn: StreamingTurn, head: Float32Array): Promise<void> => {
    const runId = currentRunId;
    pendingCommitCount += 1;
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
    } finally {
      pendingCommitCount -= 1;
      pumpPreview();
    }
  };

  // Run the parked preview only when the commit lane is idle: committed folds
  // are the product, previews are decoration, and transcribing the rolling
  // window while commits queue doubles the work and drowns the pipeline.
  const pumpPreview = (): void => {
    if (isPreviewInFlight || pendingCommitCount > 0 || pendingInterim === null) return;
    const { audio, epoch, turn } = pendingInterim;
    pendingInterim = null;
    const runId = currentRunId;
    isPreviewInFlight = true;
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
        pumpPreview();
      });
  };

  const captureInterim = (): void => {
    const turn = activeTurn;
    if (turn === null || turn.bufferedSamples < PREVIEW_MIN_SAMPLES) return;
    if (Date.now() - lastPreviewAt < PREVIEW_INTERVAL_MS) return;
    lastPreviewAt = Date.now();
    const { audio, epoch } = turn.windowAudio();
    pendingInterim = { audio, epoch, turn };
    pumpPreview();
  };

  const handleFrame = (frame: Float32Array): void => {
    const turn = activeTurn;
    if (turn === null) return;
    // vad-web reuses its frame buffers; copy before retaining.
    turn.addFrame(new Float32Array(frame));
    for (let head = turn.takeHeadSlice(); head !== null; head = turn.takeHeadSlice()) {
      void commitHeadSlice(turn, head);
    }
    captureInterim();
  };

  // End of turn: drain the window as pause-anchored chunks, fold each, and emit
  // the committed text as the final segment. A chunk that fails to transcribe
  // reports once and is skipped — the rest of the turn still lands.
  const finalizeTurn = async (turn: StreamingTurn): Promise<void> => {
    const runId = currentRunId;
    let didReportError = false;
    for (const chunk of turn.drainChunks()) {
      pendingCommitCount += 1;
      try {
        const text = await transcribeSerialized(chunk);
        if (runId !== currentRunId) return;
        turn.commitText(text);
        // A long drain gives visible progress: each fold updates the preview
        // (unless a newer turn owns it) so a stop() flush fills the composer
        // instead of appearing hung; the final then replaces it.
        if (activeTurn === null && turn.committedText.length > 0) {
          events.onPreview(turn.committedText);
        }
      } catch (error) {
        if (runId !== currentRunId) return;
        if (!didReportError) {
          didReportError = true;
          events.onError({ kind: "transcription-failed", message: describeError(error) });
        }
      } finally {
        pendingCommitCount -= 1;
        pumpPreview();
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
      // Local-Vocal's validated endpointing: ~0.8 s of silence ends an
      // utterance, shorter dips stay inside the turn, and blips under 200 ms
      // are misfires.
      positiveSpeechThreshold: 0.5,
      negativeSpeechThreshold: 0.35,
      redemptionMs: 800,
      preSpeechPadMs: 300,
      minSpeechMs: 200,
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
        // The turn's own frames are the final's audio; the VAD's padded copy
        // would re-transcribe the whole history the window model already
        // committed.
        const turn = activeTurn;
        activeTurn = null;
        if (pendingInterim?.turn === turn) {
          pendingInterim = null;
        }

        if (turn !== null) {
          pendingFinalize = finalizeTurn(turn);
        }
      },
    });
    return vadInstance;
  };

  const start = async (): Promise<void> => {
    if (isDisposed || state === "initializing" || state === "listening" || state === "stopping") return;
    activeTurn = null;
    pendingInterim = null;
    setState("initializing");
    let vad: MicVAD;
    try {
      await ensureAsrClient();
      // vad-web fetches the Silero weights on this thread; scope the auth patch
      // to that load (the worker patches its own realm for Moonshine's files).
      vad = await withVoiceModelFetchAuth(
        { modelsBase: voiceModelsBase(), token: getSessionToken() ?? null, tokenParam: SESSION_TOKEN_HEADER_NAME },
        () => ensureVad(),
      );
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
    // instead of discarding it (a junk fold discards itself).
    const turn = activeTurn;
    activeTurn = null;
    pendingInterim = null;
    releaseCapture();
    if (turn !== null) {
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
    pendingInterim = null;
    releaseCapture();
  };

  return { start, stop, dispose };
};
