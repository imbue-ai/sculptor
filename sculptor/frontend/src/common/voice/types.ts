// The on-device speech engine contract. The voice engine implementation
// (engine.ts) is built separately and consumed lazily via `import()` so the
// button carries no static dependency on the (large) speech runtime. This file
// is the shared shape both sides agree on.

export type VoiceEngineState = "idle" | "initializing" | "listening" | "stopping" | "error";

export type VoiceErrorKind = "mic-permission-denied" | "init-failed" | "transcription-failed";

export type VoiceError = {
  kind: VoiceErrorKind;
  message: string;
};

export type VoiceEngineEvents = {
  onSegment(text: string): void;
  /** Throttled interim transcription (always non-empty) of the utterance
   *  currently being spoken. */
  onPreview(text: string): void;
  /** The current utterance produced no final (misfire, too short at stop, or a
   *  failed transcription) — discard the shown preview. */
  onPreviewDiscard(): void;
  onStateChange(state: VoiceEngineState): void;
  onError(error: VoiceError): void;
};

export type VoiceEngine = {
  start(): Promise<void>;
  stop(): Promise<void>;
  dispose(): void;
};
