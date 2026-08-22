import { useAtomValue } from "jotai";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import type { ChatMessage } from "~/api";
import { useWorkspacePageParams } from "~/common/NavigateUtils.ts";
import { isSmoothStreamingEnabledAtomFamily } from "~/common/state/atoms/smoothStreaming.ts";
import { useTask } from "~/common/state/hooks/useTaskHelpers.ts";

import { computeDrainStep, snapToWordBoundary, updateDeliveryIntervalEma } from "../utils/smoothStreamingDrain.ts";
import { StreamingEngine } from "../utils/StreamingEngine.ts";

/**
 * The currently animated message paired with the task it belongs to, so the
 * render path can discard text from a previous task without reading a ref.
 */
type RenderedState = {
  readonly message: ChatMessage | null;
  readonly taskID: string;
};

/**
 * Orchestrates a StreamingEngine against live task snapshots with smooth
 * time-based text draining via requestAnimationFrame.
 *
 * When smooth streaming is enabled:
 *   - New text accumulates in the engine's buffer.
 *   - A rAF loop drains the buffer at an adaptive rate. The base drain
 *     window is the exponential moving average of the arrival-to-arrival
 *     interval between consecutive backend batches, so text spreads evenly
 *     across the full inter-batch period — creating continuous, fluid
 *     output.
 *   - Each frame reveals a small, clamped number of characters
 *     (MAX_CHARS_PER_FRAME) so even a fast stream crawls smoothly instead
 *     of stepping in large chunks.
 *   - If the buffer builds up (fast generation), the effective drain window
 *     is progressively compressed so the reveal accelerates to catch up
 *     without ever dumping the whole buffer in one frame. A hard flush is
 *     reserved for pathological runaway buffers only.
 *   - The drain math lives in ../utils/smoothStreamingDrain.ts so the
 *     cadence can be unit-tested in isolation.
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
  const isSmoothStreamingEnabled =
    useAtomValue(isSmoothStreamingEnabledAtomFamily(taskID)) && isSmoothStreamingEnabledForTask;

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

      const elapsed = timestamp - lastFrameTimeRef.current;
      lastFrameTimeRef.current = timestamp;

      const step = computeDrainStep(bufferSize, elapsed, deliveryIntervalEmaRef.current);

      // Runaway safety valve: reveal everything at once and stop the loop.
      // Reserved for pathological bursts, not the common fast-streaming path.
      if (step.shouldFlush) {
        rafIdRef.current = null;
        setRenderedState({ message: engine.flush(), taskID });
        return;
      }

      // Snap to the nearest word boundary to avoid mid-word cuts.
      let charsToReveal = step.charsToReveal;
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
          deliveryIntervalEmaRef.current = updateDeliveryIntervalEma(deliveryIntervalEmaRef.current, arrivalGap);
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
