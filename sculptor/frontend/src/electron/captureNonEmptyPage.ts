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

// 60 * 250ms = 15s of retries, comfortably inside the integration test's 30s
// clipboard-poll budget while leaving room for the OS clipboard round-trip.
const DEFAULT_ATTEMPTS = 60;
const DEFAULT_DELAY_MS = 250;

const defaultSleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

// capturePage() resolves with an empty NativeImage until the guest has
// composited a frame. Retry until it yields a painted image (or the budget is
// spent) so the screenshot -> clipboard path doesn't write an empty image.
export const captureNonEmptyPage = async <T extends CapturedImage>(
  contents: CapturablePage<T>,
  options: CaptureNonEmptyPageOptions = {},
): Promise<T> => {
  const attempts = options.attempts ?? DEFAULT_ATTEMPTS;
  const delayMs = options.delayMs ?? DEFAULT_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;

  let image = await contents.capturePage();
  for (let attempt = 1; attempt < attempts && image.isEmpty(); attempt++) {
    await sleep(delayMs);
    image = await contents.capturePage();
  }
  return image;
};
