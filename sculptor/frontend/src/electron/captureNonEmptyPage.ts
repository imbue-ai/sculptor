// Capturing a Browser panel webview's guest page for the screenshot ->
// clipboard feature. Lives apart from main.ts (no electron imports) so the
// retry policy can be unit-tested against a structurally-typed stand-in.

export type CapturedImage = {
  isEmpty(): boolean;
};

// Electron's capturePage opts. `stayHidden` makes the page "considered visible"
// for the capture even when its window is occluded, forcing the compositor to
// produce a frame; `stayAwake` keeps the system from sleeping mid-capture.
export type CapturePageOpts = {
  stayHidden?: boolean;
  stayAwake?: boolean;
};

export type CapturablePage<T extends CapturedImage> = {
  capturePage(rect?: undefined, opts?: CapturePageOpts): Promise<T>;
};

// A guest <webview> whose window the OS compositor treats as hidden or occluded
// — the steady state under a headless/xvfb display — never paints on its own, so
// capturePage() returns an empty image no matter how long we retry. `stayHidden`
// keeps the guest compositing frames while hidden, so the capture resolves to a
// real frame instead of an empty image.
const CAPTURE_OPTS: CapturePageOpts = { stayHidden: true, stayAwake: true };

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

// Capture the guest with `stayHidden` so the compositor produces a frame even
// when the window is occluded, then retry while the image is still blank (up to
// the retry budget) to absorb the beat between the first forced frame request
// and the compositor delivering it, so the screenshot -> clipboard path never
// writes an empty image.
export const captureNonEmptyPage = async <T extends CapturedImage>(
  contents: CapturablePage<T>,
  options: CaptureNonEmptyPageOptions = {},
): Promise<T> => {
  const retries = options.retries ?? DEFAULT_RETRIES;
  const delayMs = options.delayMs ?? DEFAULT_DELAY_MS;
  const sleep = options.sleep ?? defaultSleep;

  let image = await contents.capturePage(undefined, CAPTURE_OPTS);
  for (let retry = 0; retry < retries && image.isEmpty(); retry++) {
    await sleep(delayMs);
    image = await contents.capturePage(undefined, CAPTURE_OPTS);
  }
  return image;
};
