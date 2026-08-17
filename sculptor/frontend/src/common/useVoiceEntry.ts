import { useAtomValue, useSetAtom } from "jotai";
import { useCallback, useEffect, useRef, useState } from "react";

import type { DependenciesStatus, DependencyInfo } from "~/api";
import { getDependenciesStatus, installDependency } from "~/api";
import { dependenciesStatusAtom } from "~/common/state/atoms/dependenciesStatus";
import { usePollingInterval } from "~/common/usePollingInterval";
import type { VoiceEngine, VoiceEngineState, VoiceError } from "~/common/voice/types";

// The managed-install `tool` for the on-device voice-models bundle, passed to the
// shared install endpoint by name (it is deliberately not a Dependency enum
// member on the backend).
const VOICE_MODELS_TOOL = "VOICE_MODELS";

/** The single button affordance state, folding install + engine lifecycle. */
export type VoiceButtonStatus =
  | "not-installed"
  | "installing"
  | "install-error"
  | "idle"
  | "initializing"
  | "listening"
  | "stopping"
  | "voice-error";

export type VoiceEntryView = {
  status: VoiceButtonStatus;
  tooltip: string;
  ariaLabel: string;
  /** 0–100 for the install progress ring; null when total size is unknown. */
  progressPercent: number | null;
  isActive: boolean;
  isBusy: boolean;
  isError: boolean;
  handleClick: () => void;
};

// The voice-models entry rides the shared DependenciesStatus store (WS-fed), not a
// parallel one. Missing (older/partial status) is treated as not-installed.
const selectVoiceModelsInfo = (status: DependenciesStatus | null): DependencyInfo | null => status?.voiceModels ?? null;

const TOOLTIP_MIC_BLOCKED = "Microphone access is blocked. Allow it in your browser or system settings.";

const buildTooltip = (inputs: {
  status: VoiceButtonStatus;
  progressPercent: number | null;
  installError: string | null;
  voiceError: VoiceError | null;
}): string => {
  switch (inputs.status) {
    case "not-installed":
      return "Load voice models for voice entry";
    case "installing":
      return inputs.progressPercent === null
        ? "Loading voice models…"
        : `Voice models ${inputs.progressPercent}% loaded`;
    case "install-error":
      return `${inputs.installError ?? "Voice models failed to load"} — click to retry`;
    case "idle":
      return "Start voice entry";
    case "initializing":
      return "Starting voice entry…";
    case "listening":
      return "Stop voice entry";
    case "stopping":
      return "Stopping voice entry…";
    case "voice-error":
      if (inputs.voiceError?.kind === "mic-permission-denied") {
        return TOOLTIP_MIC_BLOCKED;
      }
      return `${inputs.voiceError?.message ?? "Voice entry error"} — click to retry`;
  }
};

const ARIA_LABEL_BY_STATUS: Record<VoiceButtonStatus, string> = {
  "not-installed": "Load voice models for voice entry",
  installing: "Voice models loading",
  "install-error": "Retry loading voice models",
  idle: "Start voice entry",
  initializing: "Starting voice entry",
  listening: "Stop voice entry",
  stopping: "Stopping voice entry",
  "voice-error": "Retry voice entry",
};

export type VoiceModelsInstall = {
  info: DependencyInfo | null;
  isInstalled: boolean;
  /** True while an install runs, whether kicked off from this mount or observed
   *  from another surface via the shared status stream. */
  isInstalling: boolean;
  installError: string | null;
  /** 0–100 for the aggregate bundle download; null when the total is unknown. */
  progressPercent: number | null;
  handleInstall: () => void;
};

/**
 * Owns the managed voice-models install, mirroring the shared
 * `useManagedDependency` flow: fire-and-forget POST plus a
 * `getDependenciesStatus` poll as a WebSocket fallback, both writing the one
 * shared `dependenciesStatusAtom` — so every surface rendering install state
 * stays coherent, whichever one started the download.
 */
export const useVoiceModelsInstall = (): VoiceModelsInstall => {
  const dependenciesStatus = useAtomValue(dependenciesStatusAtom);
  const setDependenciesStatus = useSetAtom(dependenciesStatusAtom);
  const { startPolling, stopPolling } = usePollingInterval();

  const [isInstallingLocal, setIsInstallingLocal] = useState(false);
  const [installErrorLocal, setInstallErrorLocal] = useState<string | null>(null);

  const info = selectVoiceModelsInfo(dependenciesStatus);
  const isInstalled = Boolean(info?.installed);
  const installProgress = info?.installProgress ?? null;
  const installError = installErrorLocal ?? info?.installError ?? null;

  // Once the shared status confirms the bundle is installed, drop any stale
  // installing/error state during render so consumers settle without waiting
  // for an effect tick.
  if (isInstalled && (isInstallingLocal || installErrorLocal !== null)) {
    setIsInstallingLocal(false);
    setInstallErrorLocal(null);
  }

  const runInstall = useCallback(async (): Promise<void> => {
    setIsInstallingLocal(true);
    setInstallErrorLocal(null);
    try {
      // Fire-and-forget: the download opens no request transaction, so skip the
      // WS ack and track completion by polling.
      const response = await installDependency({ query: { tool: VOICE_MODELS_TOOL }, meta: { skipWsAck: true } });
      const result = response.data;
      if (result && !result.success && !result.in_progress) {
        setInstallErrorLocal(result.error ?? "Installation failed");
        setIsInstallingLocal(false);
        return;
      }
      startPolling(async () => {
        try {
          const { data: deps } = await getDependenciesStatus({ meta: { skipWsAck: true } });
          if (deps) {
            setDependenciesStatus(deps);
          }
          const polledInfo = selectVoiceModelsInfo(deps ?? null);
          if (polledInfo?.installError) {
            stopPolling();
            setInstallErrorLocal(polledInfo.installError);
            setIsInstallingLocal(false);
            return;
          }

          if (polledInfo?.installed && !polledInfo.installProgress) {
            stopPolling();
            setIsInstallingLocal(false);
          }
        } catch {
          // Keep polling; transient status-fetch failures are expected mid-download.
        }
      });
    } catch (error) {
      setInstallErrorLocal(error instanceof Error ? error.message : "Installation failed");
      setIsInstallingLocal(false);
    }
  }, [setDependenciesStatus, startPolling, stopPolling]);

  const handleInstall = useCallback((): void => {
    void runInstall();
  }, [runInstall]);

  const progressPercent =
    installProgress && installProgress.totalBytes
      ? Math.round((installProgress.bytesDownloaded / installProgress.totalBytes) * 100)
      : null;

  return {
    info,
    isInstalled,
    isInstalling: isInstallingLocal || installProgress !== null,
    installError,
    progressPercent,
    handleInstall,
  };
};

const CAPTURE_LOCKED_STATUSES: ReadonlySet<VoiceButtonStatus> = new Set(["listening", "stopping"]);

export type VoiceEntryParams = {
  onAppendTranscript: (text: string) => void;
  /** Interim transcription (non-empty) of the utterance being spoken. */
  onPreviewChange?: (preview: string) => void;
  /** The utterance produced no final; discard the shown preview. */
  onPreviewDiscard?: () => void;
  /** Fires when voice takes/releases ownership of the surface's text entry. */
  onCaptureLockChange?: (locked: boolean) => void;
};

/**
 * Owns the voice-entry mic button's full lifecycle: the managed voice-models
 * install (via `useVoiceModelsInstall`) and the on-device speech engine
 * (lazily imported, started/stopped on click, disposed on unmount). Transcribed
 * segments are handed back verbatim through `onAppendTranscript`; the caller owns
 * how they land in its draft.
 */
export const useVoiceEntry = (params: VoiceEntryParams): VoiceEntryView => {
  const install = useVoiceModelsInstall();
  const [engineState, setEngineState] = useState<VoiceEngineState>("idle");
  const [voiceError, setVoiceError] = useState<VoiceError | null>(null);

  const engineRef = useRef<VoiceEngine | null>(null);
  // The callbacks flow into the long-lived engine listeners; keep them in refs
  // so a re-created callback never restarts the engine or goes stale.
  const onAppendTranscriptRef = useRef(params.onAppendTranscript);
  const onPreviewChangeRef = useRef(params.onPreviewChange);
  const onPreviewDiscardRef = useRef(params.onPreviewDiscard);
  const onCaptureLockChangeRef = useRef(params.onCaptureLockChange);
  useEffect(() => {
    onAppendTranscriptRef.current = params.onAppendTranscript;
    onPreviewChangeRef.current = params.onPreviewChange;
    onPreviewDiscardRef.current = params.onPreviewDiscard;
    onCaptureLockChangeRef.current = params.onCaptureLockChange;
  }, [params.onAppendTranscript, params.onPreviewChange, params.onPreviewDiscard, params.onCaptureLockChange]);

  // Dispose the engine on unmount — the mic must never outlive the button.
  useEffect(() => {
    return (): void => {
      engineRef.current?.dispose();
      engineRef.current = null;
    };
  }, []);

  const startListening = useCallback(async (): Promise<void> => {
    setVoiceError(null);
    setEngineState("initializing");
    try {
      // One engine per mounted button, restarted across toggles. The engine
      // module is imported dynamically so the heavy speech runtime stays off
      // the initial bundle until dictation actually starts.
      let engine = engineRef.current;
      if (engine === null) {
        const { createVoiceEngine } = await import("~/common/voice/engine.ts");
        engine = createVoiceEngine({
          onSegment: (text: string): void => onAppendTranscriptRef.current(text),
          onPreview: (text: string): void => onPreviewChangeRef.current?.(text),
          onPreviewDiscard: (): void => onPreviewDiscardRef.current?.(),
          onStateChange: (state: VoiceEngineState): void => setEngineState(state),
          onError: (error: VoiceError): void => setVoiceError(error),
        });
        engineRef.current = engine;
      }
      await engine.start();
    } catch (error) {
      setEngineState("idle");
      setVoiceError({
        kind: "init-failed",
        message: error instanceof Error ? error.message : "Could not start voice entry",
      });
    }
  }, []);

  const stopListening = useCallback(async (): Promise<void> => {
    const engine = engineRef.current;
    if (!engine) {
      setEngineState("idle");
      return;
    }
    setEngineState("stopping");
    try {
      await engine.stop();
    } catch (error) {
      setVoiceError({
        kind: "transcription-failed",
        message: error instanceof Error ? error.message : "Voice entry stopped unexpectedly",
      });
    }
  }, []);

  // Fold install + engine lifecycle into one button status.
  let status: VoiceButtonStatus;
  if (!install.isInstalled) {
    if (install.isInstalling) {
      status = "installing";
    } else if (install.installError !== null) {
      status = "install-error";
    } else {
      status = "not-installed";
    }
  } else if (voiceError !== null) {
    status = "voice-error";
  } else {
    status = engineState;
  }

  // Voice owns the surface's text entry during capture and the trailing flush,
  // so a final append can never collide with fresh typing.
  const isCaptureLocked = CAPTURE_LOCKED_STATUSES.has(status);
  useEffect(() => {
    onCaptureLockChangeRef.current?.(isCaptureLocked);
  }, [isCaptureLocked]);

  const { handleInstall } = install;
  const handleClick = useCallback((): void => {
    switch (status) {
      case "not-installed":
      case "install-error":
        handleInstall();
        break;
      case "idle":
      case "voice-error":
        void startListening();
        break;
      case "listening":
        void stopListening();
        break;
      case "installing":
      case "initializing":
      case "stopping":
        // Inert transient states — clicks are no-ops.
        break;
    }
  }, [status, handleInstall, startListening, stopListening]);

  return {
    status,
    tooltip: buildTooltip({
      status,
      progressPercent: install.progressPercent,
      installError: install.installError,
      voiceError,
    }),
    ariaLabel: ARIA_LABEL_BY_STATUS[status],
    progressPercent: install.progressPercent,
    isActive: status === "listening",
    isBusy: status === "initializing" || status === "stopping",
    isError: status === "install-error" || status === "voice-error",
    handleClick,
  };
};
