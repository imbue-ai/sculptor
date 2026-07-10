/**
 * Pure drain-rate math for the smooth-streaming rAF loop.
 *
 * These helpers decide how many characters to reveal on a given animation
 * frame given the current buffer size, the observed delivery cadence, and how
 * much time elapsed since the previous frame. They are kept free of React and
 * DOM state so the cadence can be unit-tested directly (the hook that drives
 * the loop is otherwise hard to pin down in a test).
 */

/**
 * Cap elapsed time per rAF frame to prevent huge jumps after the browser tab
 * idles (rAF pauses in background tabs, so the first frame back can report a
 * multi-second delta).
 */
export const MAX_ELAPSED_CAP_MS = 100;

/**
 * Minimum drain window — never spread a batch over less than this even if the
 * backend delivers very rapidly. Draining faster than this reads as an
 * instant dump rather than a smooth reveal.
 */
export const MIN_DRAIN_WINDOW_MS = 150;

/**
 * Maximum drain window — if the backend stalls we don't want to stretch a tiny
 * batch over an unreasonably long period.
 */
export const MAX_DRAIN_WINDOW_MS = 1200;

/** Fallback drain window used before we have delivery-interval data. */
export const DEFAULT_DRAIN_WINDOW_MS = 400;

/**
 * Soft catch-up threshold. Once the buffer exceeds this, the effective drain
 * window progressively shrinks so the reveal speeds up and latency stays
 * bounded without dumping the whole buffer in a single frame. The further past
 * this the buffer is, the harder the window compresses, down to
 * MIN_CATCHUP_WINDOW_MS.
 */
export const CATCHUP_BUFFER_CHARS = 350;

/**
 * Floor for the compressed drain window during catch-up. Small enough to burn
 * down a large backlog quickly, but still spread across several frames so the
 * reveal stays continuous instead of snapping.
 */
export const MIN_CATCHUP_WINDOW_MS = 60;

/**
 * Runaway threshold. Only when the buffer is this large do we give up on
 * animating and hard-flush the remainder in one step. This is a safety valve
 * for pathological bursts (e.g. a huge paste-like block arriving at once), not
 * the common fast-streaming path.
 */
export const RUNAWAY_BUFFER_CHARS = 2000;

/**
 * Cap on characters revealed in a single frame. Even when the buffer is large,
 * clamping the per-frame step keeps a fast stream rendering as a fast *smooth*
 * crawl rather than a few big steps. Excess stays in the buffer and is soaked
 * up by the catch-up window compression above.
 */
export const MAX_CHARS_PER_FRAME = 12;

/** Smoothing factor for the exponential moving average of delivery intervals. */
export const DELIVERY_INTERVAL_SMOOTHING = 0.3;

/**
 * Ignore arrival gaps longer than this when computing the delivery-interval
 * EMA. Gaps this large indicate a backend stall (not normal cadence) and would
 * distort the moving average.
 */
export const MAX_ARRIVAL_GAP_MS = 3000;

/** Characters of look-ahead when snapping a reveal offset to a word boundary. */
export const WORD_BOUNDARY_LOOKAHEAD_CHARS = 8;

/** Characters treated as word boundaries for snapping (whitespace and punctuation). */
export const WORD_BOUNDARY_PATTERN = /[\s\n.,;:!?)}\]"']/;

/**
 * The outcome of evaluating one animation frame.
 *
 * - `charsToReveal`: how many characters to advance the cursor by this frame.
 * - `shouldFlush`: when true, reveal everything immediately (runaway safety
 *   valve); the loop should stop after flushing.
 */
export type DrainStep = {
  readonly charsToReveal: number;
  readonly shouldFlush: boolean;
};

/**
 * Clamp the base (non-compressed) drain window derived from the delivery-
 * interval EMA into the sane `[MIN, MAX]` band, falling back to the default
 * before any cadence has been observed.
 */
export const resolveBaseDrainWindowMs = (deliveryIntervalEmaMs: number | null): number =>
  Math.min(MAX_DRAIN_WINDOW_MS, Math.max(MIN_DRAIN_WINDOW_MS, deliveryIntervalEmaMs ?? DEFAULT_DRAIN_WINDOW_MS));

/**
 * Compress the drain window as the buffer grows past the catch-up threshold so
 * the reveal accelerates to burn down a backlog, bottoming out at
 * MIN_CATCHUP_WINDOW_MS. Below the threshold the base window is used unchanged.
 */
export const resolveEffectiveDrainWindowMs = (baseWindowMs: number, bufferSize: number): number => {
  if (bufferSize <= CATCHUP_BUFFER_CHARS) {
    return baseWindowMs;
  }
  // Linear ramp from `baseWindowMs` at CATCHUP_BUFFER_CHARS down to
  // MIN_CATCHUP_WINDOW_MS at RUNAWAY_BUFFER_CHARS.
  const span = RUNAWAY_BUFFER_CHARS - CATCHUP_BUFFER_CHARS;
  const over = Math.min(bufferSize - CATCHUP_BUFFER_CHARS, span);
  const progress = span > 0 ? over / span : 1;
  const compressed = baseWindowMs - progress * (baseWindowMs - MIN_CATCHUP_WINDOW_MS);
  return Math.max(MIN_CATCHUP_WINDOW_MS, compressed);
};

/**
 * Decide how many characters to reveal this frame.
 *
 * Returns `shouldFlush` for a runaway buffer (reveal everything at once);
 * otherwise computes a per-frame character count from the effective drain rate
 * and clamps it to `[1, MAX_CHARS_PER_FRAME]` so fast streams crawl smoothly
 * instead of stepping.
 */
export const computeDrainStep = (
  bufferSize: number,
  elapsedMs: number,
  deliveryIntervalEmaMs: number | null,
): DrainStep => {
  if (bufferSize <= 0) {
    return { charsToReveal: 0, shouldFlush: false };
  }

  if (bufferSize >= RUNAWAY_BUFFER_CHARS) {
    return { charsToReveal: bufferSize, shouldFlush: true };
  }

  const baseWindowMs = resolveBaseDrainWindowMs(deliveryIntervalEmaMs);
  const effectiveWindowMs = resolveEffectiveDrainWindowMs(baseWindowMs, bufferSize);
  const cappedElapsedMs = Math.min(Math.max(elapsedMs, 0), MAX_ELAPSED_CAP_MS);

  const charsPerMs = bufferSize / effectiveWindowMs;
  const raw = Math.ceil(charsPerMs * cappedElapsedMs);
  const clamped = Math.min(Math.max(1, raw), MAX_CHARS_PER_FRAME);

  return { charsToReveal: clamped, shouldFlush: false };
};

/**
 * Snap a target character offset to the *nearest* word boundary within a small
 * look-ahead/look-behind window, so reveals land between words instead of
 * mid-word. May round the step down to the previous boundary when it is
 * closer, but never below one character of progress.
 */
export const snapToWordBoundary = (text: string, currentOffset: number, rawCharsToReveal: number): number => {
  const targetOffset = currentOffset + rawCharsToReveal;

  // Nothing past the end to snap to.
  if (targetOffset >= text.length) {
    return rawCharsToReveal;
  }

  // Already at a boundary.
  if (WORD_BOUNDARY_PATTERN.test(text[targetOffset])) {
    return rawCharsToReveal;
  }

  // Look forward for the next boundary.
  let forwardOffset: number | null = null;
  const forwardLimit = Math.min(targetOffset + WORD_BOUNDARY_LOOKAHEAD_CHARS, text.length);
  for (let i = targetOffset + 1; i < forwardLimit; i += 1) {
    if (WORD_BOUNDARY_PATTERN.test(text[i])) {
      forwardOffset = i;
      break;
    }
  }

  // Look backward for the previous boundary (but never regress past the cursor,
  // and always make at least 1 char of progress).
  let backwardOffset: number | null = null;
  const backwardLimit = Math.max(currentOffset + 1, targetOffset - WORD_BOUNDARY_LOOKAHEAD_CHARS);
  for (let i = targetOffset - 1; i >= backwardLimit; i -= 1) {
    if (WORD_BOUNDARY_PATTERN.test(text[i])) {
      backwardOffset = i;
      break;
    }
  }

  // Choose whichever boundary is closer to the raw target.
  if (forwardOffset === null && backwardOffset === null) {
    return rawCharsToReveal;
  }

  if (forwardOffset === null) {
    return (backwardOffset as number) - currentOffset;
  }

  if (backwardOffset === null) {
    return forwardOffset - currentOffset;
  }
  const forwardDistance = forwardOffset - targetOffset;
  const backwardDistance = targetOffset - backwardOffset;
  const chosen = forwardDistance <= backwardDistance ? forwardOffset : backwardOffset;
  return chosen - currentOffset;
};

/**
 * Update the exponential moving average of the arrival-to-arrival interval
 * between backend batches. Returns the new EMA, ignoring gaps so large they
 * indicate a stall rather than normal cadence (in which case the previous EMA
 * is returned unchanged).
 */
export const updateDeliveryIntervalEma = (previousEmaMs: number | null, arrivalGapMs: number): number | null => {
  if (arrivalGapMs >= MAX_ARRIVAL_GAP_MS) {
    return previousEmaMs;
  }

  if (previousEmaMs === null) {
    return arrivalGapMs;
  }
  return previousEmaMs + DELIVERY_INTERVAL_SMOOTHING * (arrivalGapMs - previousEmaMs);
};
