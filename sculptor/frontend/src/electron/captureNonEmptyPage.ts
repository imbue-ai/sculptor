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
  /**
   * How many extra capture attempts to make after the mandatory first one if
   * the guest is still blank. Zero (or less) means a single capture with no
   * retries — there is no way to ask for fewer than one capture.
   */
  retries?: number;
  /** Delay between capture attempts, in milliseconds. */
  delayMs?: number;
  /** Injectable sleep so tests don't wait in real time. */
  sleep?: (ms: number) => Promise<void>;
};

// 60 retries * 250ms = 15s of retrying, comfortably inside the integration
// test's 30s clipboard-poll budget while leaving room for the OS clipboard
// round-trip.
const DEFAULT_RETRIES = 60;
const DEFAULT_DELAY_MS = 250;

const defaultSleep = (ms: number): Promise<void> => new Promise((resolve) => setTimeout(resolve, ms));

// capturePage() resolves with an empty NativeImage until the guest has
// composited a frame. Capture once, then keep retrying while the image is
// blank (up to the retry budget) so the screenshot -> clipboard path doesn't
// write an empty image.
export const captureNonEmptyPage = async <T extends CapturedImage>(
  contents: CapturablePage<T>,
  options: CaptureNonEmptyPageOptions = {},
): Promise<T> => {
  const retries = options.retries ?? DEFAULT_RETRIES;
  const delayMs = options.delayMs ?? DEFAULT_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;

  let image = await contents.capturePage();
  for (let retry = 0; retry < retries && image.isEmpty(); retry++) {
    await sleep(delayMs);
    image = await contents.capturePage();
  }
  return image;
};
