// Capturing a Browser panel webview's guest page for the screenshot ->
// clipboard feature. Lives apart from main.ts (no electron imports) so the
// retry policy can be unit-tested against a structurally-typed stand-in.

export type CapturedImage = {
  isEmpty(): boolean;
};

export type CapturablePage<T extends CapturedImage> = {
  capturePage(): Promise<T>;
};

export type CaptureNonEmptyPageOptions = {
  /** Maximum number of capturePage() calls before giving up. */
  attempts?: number;
  /** Delay between capture attempts, in milliseconds. */
  delayMs?: number;
  /** Injectable sleep so tests don't wait in real time. */
  sleep?: (ms: number) => Promise<void>;
};

export const captureNonEmptyPage = async <T extends CapturedImage>(
  contents: CapturablePage<T>,
  _options: CaptureNonEmptyPageOptions = {},
): Promise<T> => {
  return contents.capturePage();
};
