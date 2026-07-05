import { useAtomValue } from "jotai";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { isSmoothStreamingEnabledAtom } from "~/common/state/atoms/smoothStreaming.ts";
import { useTask } from "~/common/state/hooks/useTaskHelpers.ts";

import { StreamingEngine } from "../utils/StreamingEngine.ts";

/** Hard flush when the buffer exceeds this many characters (~1.5s at high-speed streaming). */
const MAX_BUFFER_CHARS = 500;

/** Cap elapsed time per rAF frame to prevent huge jumps after browser tab idles. */
const MAX_ELAPSED_CAP_MS = 100;

/**
 * Minimum drain window — never drain faster than this even if the backend
 * delivers very rapidly.
 */
const MIN_DRAIN_WINDOW_MS = 150;

/**
 * Maximum drain window — if the backend stalls we don't want to stretch
 * a tiny batch over an unreasonably long period.
 */
const MAX_DRAIN_WINDOW_MS = 1200;

/** Fallback drain window used before we have delivery-interval data. */
const DEFAULT_DRAIN_WINDOW_MS = 400;

/** Smoothing factor for the exponential moving average of delivery intervals. */
const DELIVERY_INTERVAL_SMOOTHING = 0.3;

/**
 * Ignore arrival gaps longer than this when computing the delivery-interval
 * EMA. Gaps this large indicate a backend stall (not normal cadence) and
 * would distort the moving average.
 */
const MAX_ARRIVAL_GAP_MS = 3000;

/** Characters of look-ahead when snapping a reveal offset to a word boundary. */
const WORD_BOUNDARY_LOOKAHEAD_CHARS = 15;

/** Characters treated as word boundaries for snapping (whitespace and punctuation). */
const WORD_BOUNDARY_PATTERN = /[\s\n.,;:!?)}\]"']/;

/**
 * The currently animated message paired with the task it belongs to, so the
 * render path can discard text from a previous task without reading a ref.
 */
type RenderedState = {
  readonly message: ChatMessage | null;
  readonly taskID: string;
};

/**
 * Snap a target character offset forward to the nearest word boundary.
 * Returns the adjusted number of characters to reveal.
 */
const snapToWordBoundary = (text: string, currentOffset: number, rawCharsToReveal: number): number => {
  const targetOffset = currentOffset + rawCharsToReveal;
  if (targetOffset >= text.length) {
    return rawCharsToReveal;
  }

  // Already at a boundary.
  if (WORD_BOUNDARY_PATTERN.test(text[targetOffset])) {
    return rawCharsToReveal;
  }

  const lookAhead = Math.min(targetOffset + WORD_BOUNDARY_LOOKAHEAD_CHARS, text.length);
  for (let i = targetOffset + 1; i < lookAhead; i += 1) {
    if (WORD_BOUNDARY_PATTERN.test(text[i])) {
      return i - currentOffset;
    }
  }

  // No boundary found within lookahead — use the raw value.
  return rawCharsToReveal;
};

/**
 * Orchestrates a StreamingEngine against live task snapshots with smooth
 * time-based text draining via requestAnimationFrame.
 *
 * When smooth streaming is enabled:
 *   - New text accumulates in the engine's buffer.
 *   - A rAF loop drains the buffer at an adaptive rate. The drain window
 *     is set to the exponential moving average of the arrival-to-arrival
 *     interval between consecutive backend batches, so text spreads
 *     evenly across the full inter-batch period — creating continuous,
 *     fluid output.
 *   - The rendered text head never lags behind the received text by more
 *     than MAX_BUFFER_CHARS (~1500 ms equivalent).
 *
 * When disabled (user toggle OFF, viewport off-screen, or per-task flag):
 *   - Text is flushed immediately (identical to previous ASAP behavior).
 *
 * Task switches and new-message transitions always flush immediately so
 * accumulated background output is never animated.
 */
export const useChatSmoothStreaming = (chatMessage: ChatMessage | null): ChatMessage | null => {
  const { agentID } = useWorkspacePageParams();
  const taskID = agentID ?? "";
  const task = useTask(taskID);
  const isSmoothStreamingEnabledForTask = task?.isSmoothStreamingSupported ?? false;
  const isSmoothStreamingEnabled = useAtomValue(isSmoothStreamingEnabledAtom) && isSmoothStreamingEnabledForTask;

  const engineRef = useRef<StreamingEngine | null>(null);
  const activeMessageIdRef = useRef<string | null>(null);
  const activeTaskIdRef = useRef<string | null>(null);
  const rafIdRef = useRef<number | null>(null);
  const lastFrameTimeRef = useRef<number>(0);
  /** Exponential moving average of the interval (ms) between batch arrivals. */
  const deliveryIntervalEmaRef = useRef<number | null>(null);
  /**
   * Timestamp of the last batch arrival that came in while the buffer was
   * empty. Used to measure the full arrival-to-arrival cadence — the true
   * period over which we should spread each batch's characters.
   */
  const lastBatchArrivalTimeRef = useRef<number>(0);
  const [renderedState, setRenderedState] = useState<RenderedState>({
    message: chatMessage ?? null,
    taskID,
  });

  const ensureEngine = useCallback((): StreamingEngine => {
    if (!engineRef.current) {
      engineRef.current = new StreamingEngine();
    }
    return engineRef.current;
  }, []);

  const stopAnimationLoop = useCallback((): void => {
    if (rafIdRef.current !== null) {
      cancelAnimationFrame(rafIdRef.current);
      rafIdRef.current = null;
    }
  }, []);

  const startAnimationLoop = useCallback((): void => {
    if (rafIdRef.current !== null) {
      return; // Already running.
    }

    lastFrameTimeRef.current = performance.now();

    const tick = (timestamp: number): void => {
      const engine = engineRef.current;
      if (!engine) {
        rafIdRef.current = null;
        return;
      }

      const bufferSize = engine.getBufferSize();
      if (bufferSize === 0) {
        rafIdRef.current = null;
        setRenderedState({ message: engine.flush(), taskID });
        return;
      }

      // Enforce the hard max-latency cap.
      if (bufferSize > MAX_BUFFER_CHARS) {
        rafIdRef.current = null;
        setRenderedState({ message: engine.flush(), taskID });
        return;
      }

      const elapsed = Math.min(timestamp - lastFrameTimeRef.current, MAX_ELAPSED_CAP_MS);
      lastFrameTimeRef.current = timestamp;

      // Use the delivery-interval EMA as the drain window so text spreads
      // evenly between backend batches, creating continuous flow.
      const drainWindowMs = Math.min(
        MAX_DRAIN_WINDOW_MS,
        Math.max(MIN_DRAIN_WINDOW_MS, deliveryIntervalEmaRef.current ?? DEFAULT_DRAIN_WINDOW_MS),
      );
      const charsPerMs = bufferSize / drainWindowMs;
      let charsToReveal = Math.max(1, Math.ceil(charsPerMs * elapsed));

      // Snap to the nearest word boundary to avoid mid-word cuts.
      const snapshot = engine.peekSnapshot();
      const cursorState = engine.peekCursor();
      if (snapshot && cursorState.blockIndex !== null && cursorState.offset !== null) {
        const block = snapshot.content[cursorState.blockIndex];
        if (block && block.type === "text") {
          charsToReveal = snapToWordBoundary(block.text, cursorState.offset, charsToReveal);
        }
      }

      setRenderedState({ message: engine.advanceCursor(charsToReveal), taskID });
      rafIdRef.current = requestAnimationFrame(tick);
    };

    rafIdRef.current = requestAnimationFrame(tick);
  }, [taskID]);

  // Initialize the engine on mount; clean up on unmount.
  useEffect(() => {
    ensureEngine();

    return (): void => {
      stopAnimationLoop();
      if (engineRef.current) {
        engineRef.current.updateLatestSnapshot(null);
      }
    };
  }, [ensureEngine, stopAnimationLoop]);

  const handleSnapshot = useCallback(
    (engine: StreamingEngine, snapshot: ChatMessage): void => {
      const isNewMessage = activeMessageIdRef.current !== snapshot.id;
      const isTaskSwitch = activeTaskIdRef.current !== null && activeTaskIdRef.current !== taskID;

      activeMessageIdRef.current = snapshot.id;
      activeTaskIdRef.current = taskID;

      // New message or task switch: flush immediately, no animation.
      if (isNewMessage || isTaskSwitch) {
        stopAnimationLoop();
        engine.updateLatestSnapshot(snapshot);
        setRenderedState({ message: engine.flush(), taskID });
        deliveryIntervalEmaRef.current = null;
        lastBatchArrivalTimeRef.current = 0;
        return;
      }

      // Smooth streaming disabled: flush immediately (ASAP mode).
      if (!isSmoothStreamingEnabled) {
        stopAnimationLoop();
        engine.updateLatestSnapshot(snapshot);
        setRenderedState({ message: engine.flush(), taskID });
        return;
      }

      const prevBufferSize = engine.getBufferSize();
      engine.updateLatestSnapshot(snapshot);
      const newBufferSize = engine.getBufferSize();
      const delta = newBufferSize - prevBufferSize;

      // Track delivery cadence: measure the full arrival-to-arrival interval
      // between consecutive batches (where each batch is the first snapshot
      // that adds text after the buffer was empty). This captures the true
      // period we need to spread characters over, including both drain time
      // and idle time between batches.
      if (delta > 0 && prevBufferSize === 0) {
        const nowMs = performance.now();
        if (lastBatchArrivalTimeRef.current > 0) {
          const arrivalGap = nowMs - lastBatchArrivalTimeRef.current;
          if (arrivalGap < MAX_ARRIVAL_GAP_MS) {
            const prev = deliveryIntervalEmaRef.current;
            deliveryIntervalEmaRef.current =
              prev === null ? arrivalGap : prev + DELIVERY_INTERVAL_SMOOTHING * (arrivalGap - prev);
          }
        }
        lastBatchArrivalTimeRef.current = nowMs;
      }

      // Start (or continue) the rAF drain loop.
      startAnimationLoop();
    },
    [taskID, isSmoothStreamingEnabled, stopAnimationLoop, startAnimationLoop],
  );

  // Reconcile each new snapshot from the backend.
  useEffect(() => {
    const engine = ensureEngine();

    if (!chatMessage) {
      // Stream completed — tear down the engine/loop so isStreaming becomes false.
      // The completed message is already in completedChatMessages by the time
      // inProgressChatMessage goes null, so we don't need to keep rendering it.
      // The "cleared" rendered value is derived from chatMessage during render
      // rather than written to state here, avoiding a setState in this effect.
      stopAnimationLoop();
      engine.updateLatestSnapshot(null);
      activeMessageIdRef.current = null;
      activeTaskIdRef.current = null;
      return;
    }

    handleSnapshot(engine, chatMessage);
    // `isSmoothStreamingEnabled` is intentionally omitted: it's already captured
    // by `handleSnapshot`, which re-creates whenever the flag changes.
  }, [chatMessage, handleSnapshot, ensureEngine, stopAnimationLoop]);

  // When smooth streaming is disabled while the loop is running, flush.
  useEffect(() => {
    if (!isSmoothStreamingEnabled && engineRef.current) {
      stopAnimationLoop();
      setRenderedState({ message: engineRef.current.flush(), taskID });
    }
  }, [isSmoothStreamingEnabled, stopAnimationLoop, taskID]);

  return useMemo(() => {
    // Stream completed: derive the cleared value directly from the prop instead
    // of from state, so the reconcile effect doesn't need to setState.
    if (!chatMessage) {
      return null;
    }

    // Synchronous guard: if we switched to a different task, don't return stale
    // animated text from the previous task. Comparing the task recorded
    // alongside the rendered message against the current taskID keeps this a
    // pure render-time derivation (no ref read).
    if (renderedState.taskID !== taskID) {
      return null;
    }
    return renderedState.message ?? null;
  }, [chatMessage, renderedState, taskID]);
};
