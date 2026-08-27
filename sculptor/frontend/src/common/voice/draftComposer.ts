import { appendTranscript } from "~/common/utils/voiceEntryText.ts";

export type VoiceDraftComposer = {
  /** The text to display for an interim preview. The first preview of an
   *  utterance captures `currentDraft` as the base; later previews replace the
   *  shown tail against that same base. */
  previewText(currentDraft: string, preview: string): string;
  /** The draft to commit for a final segment: base + final, seam-spaced. Ends
   *  the utterance. */
  commitText(currentDraft: string, segment: string): string;
  /** Ends a previewed utterance that produced no final; returns the base text
   *  to restore, or null when no preview was shown. */
  discard(): string | null;
};

/**
 * The one implementation of the per-utterance preview protocol every entry
 * surface follows (see the event protocol in voice/engine.ts): capture the
 * draft as base on the first preview, show base + tail while speaking, replace
 * the tail with the final on commit, restore the base on discard. Surfaces
 * supply only how to read and write their own draft. Calls are stateful —
 * invoke them from event handlers, never inside a React state updater (which
 * StrictMode runs twice).
 */
export const createVoiceDraftComposer = (): VoiceDraftComposer => {
  let base: string | null = null;
  return {
    previewText(currentDraft: string, preview: string): string {
      base ??= currentDraft;
      return appendTranscript({ draft: base, segment: preview });
    },
    commitText(currentDraft: string, segment: string): string {
      const draft = base ?? currentDraft;
      base = null;
      return appendTranscript({ draft, segment });
    },
    discard(): string | null {
      const restored = base;
      base = null;
      return restored;
    },
  };
};
