import { describe, expect, it } from "vitest";

import {
  cleanAsrText,
  collapseRepeats,
  dropSeamOverlap,
  frameRms,
  STREAMING_TURN_DEFAULTS,
  StreamingTurn,
} from "./streamingTurn.ts";

const SAMPLE_RATE = STREAMING_TURN_DEFAULTS.sampleRate;
const FRAME_SAMPLES = 512;
const MAX_WINDOW_SAMPLES = STREAMING_TURN_DEFAULTS.maxWindowSeconds * SAMPLE_RATE;

const makeFrame = (level: number): Float32Array => {
  const frame = new Float32Array(FRAME_SAMPLES);
  frame.fill(level);
  return frame;
};

const secondsToFrames = (seconds: number): number => Math.ceil((seconds * SAMPLE_RATE) / FRAME_SAMPLES);

// Feed frames of one level, collecting any head slices that come due.
const feed = (turn: StreamingTurn, level: number, frames: number, onSlice: (head: Float32Array) => void): void => {
  for (let i = 0; i < frames; i += 1) {
    turn.addFrame(makeFrame(level));
    const head = turn.takeHeadSlice();
    if (head !== null) onSlice(head);
  }
};

// A long turn with genuine pauses: loud stretches separated by 0.3 s of quiet.
const speakLongTurnWithPauses = (turn: StreamingTurn, onSlice: (head: Float32Array) => void): number => {
  const loudFrames = secondsToFrames(12);
  const quietFrames = secondsToFrames(0.3);
  feed(turn, 0.1, loudFrames, onSlice);
  feed(turn, 0, quietFrames, onSlice);
  feed(turn, 0.1, loudFrames, onSlice);
  feed(turn, 0, quietFrames, onSlice);
  feed(turn, 0.1, loudFrames, onSlice);
  return (3 * loudFrames + 2 * quietFrames) * FRAME_SAMPLES;
};

describe("StreamingTurn commit-and-slice", () => {
  it("commits without loss or duplication across window slides", () => {
    const turn = new StreamingTurn();
    const chunks: Array<Float32Array> = [];
    let counter = 0;
    const commitChunk = (chunk: Float32Array): void => {
      counter += 1;
      turn.commitText(`chunk${counter}`);
      chunks.push(chunk);
    };

    const fedSamples = speakLongTurnWithPauses(turn, commitChunk);
    const sliceCount = counter;
    for (const chunk of turn.drainChunks()) commitChunk(chunk);

    expect(sliceCount).toBeGreaterThanOrEqual(2);
    const expectedText = Array.from({ length: counter }, (_, i) => `chunk${i + 1}`).join(" ");
    expect(turn.committedText).toBe(expectedText);
    const totalSamples = chunks.reduce((total, chunk) => total + chunk.length, 0);
    expect(totalSamples).toBe(fedSamples);
    expect(turn.bufferedSamples).toBe(0);
  });

  it("keeps every chunk within the window cap when pauses exist", () => {
    const turn = new StreamingTurn();
    const chunks: Array<Float32Array> = [];
    speakLongTurnWithPauses(turn, (head) => chunks.push(head));
    chunks.push(...turn.drainChunks());

    for (const chunk of chunks) {
      expect(chunk.length).toBeLessThanOrEqual(MAX_WINDOW_SAMPLES);
    }
  });

  it("anchors cuts in real pauses so no word is split", () => {
    const turn = new StreamingTurn();
    const heads: Array<Float32Array> = [];
    speakLongTurnWithPauses(turn, (head) => heads.push(head));

    expect(heads.length).toBeGreaterThanOrEqual(1);
    for (const head of heads) {
      // The cut lands mid-pause, so the head ends in silence, not speech.
      expect(head[head.length - 1]).toBe(0);
    }
  });

  it("does not treat a short dip as a pause: no cut before the hard cap", () => {
    const turn = new StreamingTurn();
    let sliceCount = 0;
    const onSlice = (): void => {
      sliceCount += 1;
    };
    feed(turn, 0.1, secondsToFrames(10), onSlice);
    // A 100 ms dip is a stop-consonant closure, not an inter-word gap.
    feed(turn, 0, secondsToFrames(0.1), onSlice);
    feed(turn, 0.1, secondsToFrames(12), onSlice);
    expect(sliceCount).toBe(0);
    expect(turn.bufferedSamples).toBeGreaterThan(MAX_WINDOW_SAMPLES);

    feed(turn, 0.1, secondsToFrames(9), onSlice);
    expect(turn.bufferedSamples + sliceCount).toBeGreaterThan(0);
    expect(sliceCount).toBeGreaterThanOrEqual(1);
  });

  it("loses nothing under forced cuts when speech never pauses", () => {
    const turn = new StreamingTurn();
    const chunks: Array<Float32Array> = [];
    const frames = secondsToFrames(32);
    feed(turn, 0.1, frames, (head) => chunks.push(head));
    chunks.push(...turn.drainChunks());

    const totalSamples = chunks.reduce((total, chunk) => total + chunk.length, 0);
    expect(totalSamples).toBe(frames * FRAME_SAMPLES);
    expect(chunks.length).toBeGreaterThanOrEqual(2);
  });

  it("de-dups the seam case- and punctuation-insensitively when folding", () => {
    const turn = new StreamingTurn();
    turn.commitText("Hello, world.");
    turn.commitText("world again");
    expect(turn.committedText).toBe("Hello, world. again");
  });

  it("shows committed text plus the window hypothesis as the live preview", () => {
    const turn = new StreamingTurn();
    turn.commitText("first part");
    turn.applyHypothesis("second bit", turn.epoch);
    expect(turn.liveText).toBe("first part second bit");

    // LocalAgreement-2: a repeated hypothesis promotes the tail to stable.
    expect(turn.liveParts().tentative).toBe("second bit");
    turn.applyHypothesis("second bit", turn.epoch);
    expect(turn.liveParts()).toEqual({ stable: "first part second bit", tentative: "" });
  });

  it("ignores a hypothesis from before a slice", () => {
    const turn = new StreamingTurn();
    const staleEpoch = turn.epoch;
    let didSlice = false;
    speakLongTurnWithPauses(turn, () => {
      didSlice = true;
    });
    expect(didSlice).toBe(true);
    expect(turn.epoch).not.toBe(staleEpoch);

    turn.applyHypothesis("stale words", staleEpoch);
    expect(turn.liveText).toBe("");
  });

  it("never lets a hypothesis touch the committed transcript", () => {
    const turn = new StreamingTurn();
    turn.applyHypothesis("ghost words", turn.epoch);
    expect(turn.liveText).toBe("ghost words");
    expect(turn.committedText).toBe("");
  });

  it("drains the window at end of turn so committedText is the transcript", () => {
    const turn = new StreamingTurn();
    feed(turn, 0.1, secondsToFrames(3), () => undefined);
    const chunks = turn.drainChunks();
    expect(chunks.length).toBe(1);
    turn.commitText("the whole thing");
    expect(turn.committedText).toBe("the whole thing");
    expect(turn.bufferedSamples).toBe(0);
  });

  it("commits nothing for junk transcriptions", () => {
    const turn = new StreamingTurn();
    turn.commitText("[BLANK_AUDIO]");
    turn.commitText("(coughs)");
    turn.commitText("   ");
    expect(turn.committedText).toBe("");
  });
});

describe("text hygiene helpers", () => {
  it("cleanAsrText strips annotations and rejects junk", () => {
    expect(cleanAsrText("[BLANK_AUDIO]")).toBe("");
    expect(cleanAsrText("(coughs) hello there")).toBe("hello there");
    expect(cleanAsrText("...")).toBe("");
  });

  it("collapseRepeats reduces a runaway loop but keeps natural repetition", () => {
    expect(collapseRepeats("yes yes yes yes yes")).toBe("yes");
    expect(collapseRepeats("no no no")).toBe("no no no");
    expect(collapseRepeats("a b a b a b")).toBe("a b");
  });

  it("dropSeamOverlap drops only a genuine repeated seam", () => {
    expect(dropSeamOverlap(["hello", "world"], ["world", "again"])).toEqual(["again"]);
    expect(dropSeamOverlap(["hello", "world"], ["brand", "new"])).toEqual(["brand", "new"]);
  });

  it("frameRms measures a frame's level", () => {
    expect(frameRms(makeFrame(0.1))).toBeCloseTo(0.1, 5);
    expect(frameRms(makeFrame(0))).toBe(0);
  });
});
