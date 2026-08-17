// The streaming-transcription model for one VAD speech segment ("turn"), with
// no knowledge of the DOM, the ASR pipeline, or scheduling.
//
// Mechanism ("silence-anchored commit-and-slice"): a StreamingTurn holds
//   - the committed transcript words (grow without bound), and
//   - a rolling active-audio window (bounded to ~20 s of samples).
// The driver periodically transcribes the whole active window for the live
// preview, so per-tick work stays bounded no matter how long the turn runs.
// Once the window exceeds the cap, the turn slices off a head of audio at a
// genuine pause (a contiguous low-energy run of >= ~200 ms — a real inter-word
// gap, never a stop-consonant closure), hands that head out to be transcribed,
// and folds the resulting text into the committed words. Because the cut lands
// in silence, no word is split; a word-level seam de-dup backstop protects the
// rare forced cut (no pause found by the ~30 s hard cap). At end of turn the
// remaining window drains the same way, so the turn's transcript is simply
// `committedText` once the last chunk folds in. The live preview is always
// `committed + current window hypothesis` — the same text the final will read,
// just read earlier.
//
// Moonshine (via transformers.js) returns only {text} — no word timestamps —
// which is why the slice points come from audio energy, not token times.

const PUNCTUATION_RE = /[.,!?;:"'’]/g;

const normalizeWord = (word: string): string => word.replace(PUNCTUATION_RE, "").toLowerCase();

// A runaway ASR decoder loop repeats one phrase many times; collapse it to a
// single copy. Shortest repeating phrase wins (the loop's true period); single
// words need a higher bar so natural emphasis ("no no no") survives.
const MAX_PHRASE_WORDS = 30;
const MIN_REPEATS_MULTIWORD = 3;
const MIN_REPEATS_SINGLE_WORD = 4;

const rangesEqual = (words: Array<string>, a: number, b: number, length: number): boolean => {
  for (let k = 0; k < length; k += 1) {
    if (words[a + k] !== words[b + k]) return false;
  }
  return true;
};

export const collapseRepeats = (text: string): string => {
  const words = (text || "").split(/\s+/).filter(Boolean);
  const count = words.length;
  if (count < 2) return (text || "").trim();
  const normalized = words.map(normalizeWord);
  const out: Array<string> = [];
  let i = 0;
  while (i < count) {
    let didCollapse = false;
    const maxLength = Math.min(MAX_PHRASE_WORDS, Math.floor((count - i) / 2));
    for (let length = 1; length <= maxLength; length += 1) {
      let repeats = 1;
      let j = i + length;
      while (j + length <= count && rangesEqual(normalized, i, j, length)) {
        repeats += 1;
        j += length;
      }
      const threshold = length === 1 ? MIN_REPEATS_SINGLE_WORD : MIN_REPEATS_MULTIWORD;
      if (repeats >= threshold) {
        for (let k = i; k < i + length; k += 1) out.push(words[k]);
        i = j;
        didCollapse = true;
        break;
      }
    }

    if (!didCollapse) {
      out.push(words[i]);
      i += 1;
    }
  }
  return out.join(" ");
};

// Moonshine emits bracketed annotations on non-speech audio ("[BLANK_AUDIO]",
// "(coughs)"). Strip them; if nothing pronounceable remains, the text is junk
// (returned as ""). Any runaway decoder loop is collapsed to one copy.
export const cleanAsrText = (text: string): string => {
  const stripped = (text || "").replace(/\[[^\]]*\]|\([^)]*\)/g, " ");
  if (!/[a-z0-9]/i.test(stripped)) return "";
  return collapseRepeats(stripped.replace(/\s+/g, " ").trim());
};

// When a transcribed chunk folds onto the committed words, drop its leading
// words if they repeat the committed trailing words (normalised comparison).
// On a pause-anchored cut the chunks share no audio, so overlap is rare; the
// backstop exists for the forced (no-pause) cut, where the ASR can hear the
// boundary word in both chunks. Capped so a genuine long repetition by the
// author is never eaten.
const MAX_SEAM_OVERLAP_WORDS = 6;

export const dropSeamOverlap = (committedWords: Array<string>, newWords: Array<string>): Array<string> => {
  const maxK = Math.min(MAX_SEAM_OVERLAP_WORDS, committedWords.length, newWords.length);
  for (let k = maxK; k >= 1; k -= 1) {
    let doesMatch = true;
    for (let i = 0; i < k; i += 1) {
      if (normalizeWord(committedWords[committedWords.length - k + i]) !== normalizeWord(newWords[i])) {
        doesMatch = false;
        break;
      }
    }
    if (doesMatch) return newWords.slice(k);
  }
  return newWords;
};

export const frameRms = (frame: Float32Array): number => {
  let sum = 0;
  for (let i = 0; i < frame.length; i += 1) sum += frame[i] * frame[i];
  return Math.sqrt(sum / Math.max(1, frame.length));
};

const concatFrames = (chunks: Array<Float32Array>): Float32Array => {
  let total = 0;
  for (const chunk of chunks) total += chunk.length;
  const out = new Float32Array(total);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
};

export type StreamingTurnOptions = {
  sampleRate: number;
  /** The model-input cap: once the window exceeds this, look for a pause to
   *  slice at. Moonshine is a short-audio model; past ~20 s its decoder loops. */
  maxWindowSeconds: number;
  /** Waiting for a genuine pause may let the window grow past the cap; at this
   *  absolute bound a cut is forced (quietest frame) rather than waiting longer. */
  hardCapSeconds: number;
  /** A qualifying pause is a contiguous quiet run at least this long — a real
   *  inter-word/phrase gap. Shorter dips (a stop-consonant closure is
   *  ~50-100 ms) can sit INSIDE a word, and cutting there would split it. */
  minPauseMs: number;
  /** Never slice off a sliver: a head must be at least this long. */
  minHeadSeconds: number;
  /** The forced cut hunts for the quietest single frame this far back from the cap. */
  forcedCutSearchSeconds: number;
  /** A frame is "quiet" when its RMS is under both an absolute floor and a
   *  fraction of the loudest frame heard this turn (mic gains vary widely). */
  quietAbsoluteRms: number;
  quietPeakFraction: number;
};

export const STREAMING_TURN_DEFAULTS: StreamingTurnOptions = {
  sampleRate: 16000,
  maxWindowSeconds: 20,
  hardCapSeconds: 30,
  minPauseMs: 200,
  minHeadSeconds: 1,
  forcedCutSearchSeconds: 4,
  quietAbsoluteRms: 0.006,
  quietPeakFraction: 0.08,
};

export type WindowAudio = { audio: Float32Array; epoch: number };

/**
 * The per-turn streaming transcriber state. Pure and synchronous: the driver
 * owns the ASR pipeline and feeds results back in. Contract with the driver:
 *   - addFrame(frame) for every VAD frame of the segment;
 *   - takeHeadSlice() after feeding: non-null means "transcribe this audio and
 *     pass the text to commitText()" (results must fold in slice order — one
 *     FIFO transcription chain gives that for free);
 *   - windowAudio() -> {audio, epoch} for periodic live-preview transcription,
 *     the text fed to applyHypothesis(text, epoch) (stale epochs are ignored);
 *   - at end of turn, drainChunks() empties the window; commit each chunk's
 *     text, then committedText IS the turn's transcript.
 */
export class StreamingTurn {
  private readonly maxWindow: number;
  private readonly hardCap: number;
  private readonly minPauseSamples: number;
  private readonly minHead: number;
  private readonly forcedSearch: number;
  private readonly quietAbs: number;
  private readonly quietFraction: number;

  private committed: Array<string> = [];
  private frames: Array<Float32Array> = [];
  private frameLevels: Array<number> = [];
  private samples = 0;
  private peakRms = 0;
  private turnEpoch = 0;
  private hypothesis: Array<string> = [];
  private previousHypothesis: Array<string> = [];
  private agreedPrefix = 0;

  constructor(options?: Partial<StreamingTurnOptions>) {
    const resolved = { ...STREAMING_TURN_DEFAULTS, ...options };
    this.maxWindow = Math.round(resolved.maxWindowSeconds * resolved.sampleRate);
    this.hardCap = Math.round(resolved.hardCapSeconds * resolved.sampleRate);
    this.minPauseSamples = Math.round((resolved.minPauseMs / 1000) * resolved.sampleRate);
    this.minHead = Math.round(resolved.minHeadSeconds * resolved.sampleRate);
    this.forcedSearch = Math.round(resolved.forcedCutSearchSeconds * resolved.sampleRate);
    this.quietAbs = resolved.quietAbsoluteRms;
    this.quietFraction = resolved.quietPeakFraction;
  }

  /** Feed one frame of turn audio at the configured sample rate. The frame is
   *  retained; pass a copy if the caller reuses its buffer. */
  addFrame(frame: Float32Array): void {
    const rms = frameRms(frame);
    this.frames.push(frame);
    this.frameLevels.push(rms);
    this.samples += frame.length;
    if (rms > this.peakRms) this.peakRms = rms;
  }

  get bufferedSamples(): number {
    return this.samples;
  }

  get epoch(): number {
    return this.turnEpoch;
  }

  get committedText(): string {
    return this.committed.join(" ");
  }

  get committedWordCount(): number {
    return this.committed.length;
  }

  /** A copy of the current active window, tagged with the epoch that must
   *  accompany the resulting hypothesis (a slice in between invalidates it). */
  windowAudio(): WindowAudio {
    return { audio: concatFrames(this.frames), epoch: this.turnEpoch };
  }

  /** Fold one live hypothesis over the current window into the preview state.
   *  Never touches the committed words — those come only from commitText(). */
  applyHypothesis(text: string, epoch: number): void {
    if (epoch !== this.turnEpoch) return;
    const hypothesis = cleanAsrText(text).split(" ").filter(Boolean);
    let i = 0;
    const m = Math.min(this.previousHypothesis.length, hypothesis.length);
    while (i < m && normalizeWord(hypothesis[i]) === normalizeWord(this.previousHypothesis[i])) i += 1;
    this.agreedPrefix = i;
    this.previousHypothesis = hypothesis;
    this.hypothesis = hypothesis;
  }

  /** The live preview, at any moment and any turn length: all committed text
   *  plus the latest window hypothesis (LocalAgreement-2 marks how much of the
   *  tail two consecutive hypotheses agreed on). */
  liveParts(): { stable: string; tentative: string } {
    return {
      stable: this.committed.concat(this.hypothesis.slice(0, this.agreedPrefix)).join(" "),
      tentative: this.hypothesis.slice(this.agreedPrefix).join(" "),
    };
  }

  get liveText(): string {
    const parts = this.liveParts();
    return `${parts.stable} ${parts.tentative}`.trim();
  }

  /** Fold a transcribed audio chunk (a head slice or a drained chunk) into the
   *  committed words, junk-filtered, de-looped, and seam-de-duped. */
  commitText(rawText: string): void {
    const text = cleanAsrText(rawText);
    if (!text) return;
    const words = dropSeamOverlap(this.committed, text.split(" "));
    for (const word of words) this.committed.push(word);
  }

  /** If the window is over the cap and a safe cut exists, slice off the head:
   *  remove that audio from the window and return it for transcribe-and-commit.
   *  Returns null while no cut is due — or, past the cap but under the hard
   *  cap, while no qualifying pause exists yet (never cut inside a word). */
  takeHeadSlice(): Float32Array | null {
    if (this.samples <= this.maxWindow) return null;
    let cutFrame = this.findPauseCutFrame();
    if (cutFrame === null) {
      if (this.samples < this.hardCap) return null;
      cutFrame = this.forcedCutFrame();
    }
    return this.sliceAt(cutFrame);
  }

  /** Empty the window as a sequence of transcribe-and-commit chunks (each cut
   *  pause-anchored where possible, every chunk <= the cap except a degenerate
   *  single over-long frame). Call at end of turn; commit each chunk's text in
   *  order and committedText is then the turn's full transcript. */
  drainChunks(): Array<Float32Array> {
    const chunks: Array<Float32Array> = [];
    while (this.samples > this.maxWindow) {
      let cutFrame = this.findPauseCutFrame();
      if (cutFrame === null) cutFrame = this.forcedCutFrame();
      const head = this.sliceAt(cutFrame);
      if (!head) break;
      chunks.push(head);
    }

    if (this.samples > 0) {
      chunks.push(concatFrames(this.frames));
      this.dropWindow(this.frames.length);
    }
    return chunks;
  }

  private quietThreshold(): number {
    return Math.max(this.quietAbs, this.quietFraction * this.peakRms);
  }

  private frameOffsets(): Array<number> {
    const offsets = new Array<number>(this.frames.length + 1);
    let offset = 0;
    for (let i = 0; i < this.frames.length; i += 1) {
      offsets[i] = offset;
      offset += this.frames[i].length;
    }
    offsets[this.frames.length] = offset;
    return offsets;
  }

  /** The LATEST genuine pause whose cut point fits in [minHead, maxWindow]:
   *  a contiguous run of quiet frames spanning >= minPause. Cut at the run's
   *  middle (silence on both sides — between words by construction), walked
   *  back inside the run if the middle overshoots the cap. */
  private findPauseCutFrame(): number | null {
    const threshold = this.quietThreshold();
    const offsets = this.frameOffsets();
    const count = this.frames.length;
    let best: number | null = null;
    let runStart = -1;
    for (let i = 0; i <= count; i += 1) {
      const isQuiet = i < count && this.frameLevels[i] <= threshold;
      if (isQuiet) {
        if (runStart < 0) runStart = i;
        continue;
      }

      if (runStart >= 0) {
        const runEnd = i;
        if (offsets[runEnd] - offsets[runStart] >= this.minPauseSamples) {
          let cut = runStart + Math.floor((runEnd - runStart) / 2);
          while (cut > runStart && offsets[cut] > this.maxWindow) cut -= 1;
          const at = offsets[cut];
          if (at >= this.minHead && at <= this.maxWindow) best = cut;
        }
        runStart = -1;
      }
    }
    return best;
  }

  /** No pause by the hard cap: cut at the quietest single frame near the cap
   *  (best effort — the seam de-dup in commitText backstops this cut). */
  private forcedCutFrame(): number | null {
    const offsets = this.frameOffsets();
    const from = Math.max(this.minHead, this.maxWindow - this.forcedSearch);
    let cut: number | null = null;
    let best = Infinity;
    let lastInCap: number | null = null;
    for (let i = 0; i < this.frames.length; i += 1) {
      const at = offsets[i];
      if (at > this.maxWindow) break;
      if (at >= this.minHead) lastInCap = i;
      if (at >= from && this.frameLevels[i] < best) {
        best = this.frameLevels[i];
        cut = i;
      }
    }
    return cut !== null ? cut : lastInCap;
  }

  private sliceAt(cutFrame: number | null): Float32Array | null {
    if (cutFrame === null || cutFrame <= 0) return null;
    const head = concatFrames(this.frames.slice(0, cutFrame));
    this.dropWindow(cutFrame);
    return head;
  }

  /** Drop the first `count` frames and invalidate the window hypothesis (it
   *  described audio that is no longer the window). */
  private dropWindow(count: number): void {
    this.frames = this.frames.slice(count);
    this.frameLevels = this.frameLevels.slice(count);
    this.samples = 0;
    for (const frame of this.frames) this.samples += frame.length;
    this.turnEpoch += 1;
    this.hypothesis = [];
    this.previousHypothesis = [];
    this.agreedPrefix = 0;
  }
}
