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
  /** Throttled interim transcription of the utterance currently being spoken.
   *  An empty string clears the preview (utterance ended, misfired, or flushed). */
  onPreview(text: string): void;
  onStateChange(state: VoiceEngineState): void;
  onError(error: VoiceError): void;
};

export type VoiceEngine = {
  start(): Promise<void>;
  stop(): Promise<void>;
  dispose(): void;
};
