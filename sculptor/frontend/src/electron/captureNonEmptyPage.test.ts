import { describe, expect, it, vi } from "vitest";

import { captureNonEmptyPage } from "./captureNonEmptyPage";

const emptyImage = { isEmpty: (): boolean => true };
const paintedImage = { isEmpty: (): boolean => false };

describe("captureNonEmptyPage", () => {
  it("retries capturePage until the guest has painted a non-empty frame", async () => {
    // Under xvfb + software rendering the guest can return an empty image for
    // the first few frames after a navigation; writing that empty image to the
    // clipboard leaves no PNG and the screenshot test fails.
    const capturePage = vi
      .fn()
      .mockResolvedValueOnce(emptyImage)
      .mockResolvedValueOnce(emptyImage)
      .mockResolvedValueOnce(paintedImage);
    const sleep = vi.fn(() => Promise.resolve());

    const result = await captureNonEmptyPage({ capturePage }, { delayMs: 0, sleep });

    expect(result).toBe(paintedImage);
    expect(capturePage).toHaveBeenCalledTimes(3);
  });

  it("returns immediately when the first capture is already painted", async () => {
    const capturePage = vi.fn(() => Promise.resolve(paintedImage));

    const result = await captureNonEmptyPage({ capturePage });

    expect(result).toBe(paintedImage);
    expect(capturePage).toHaveBeenCalledTimes(1);
  });

  it("captures exactly once when retries is 0", async () => {
    const capturePage = vi.fn(() => Promise.resolve(emptyImage));

    const result = await captureNonEmptyPage({ capturePage }, { retries: 0 });

    expect(result).toBe(emptyImage);
    expect(capturePage).toHaveBeenCalledTimes(1);
  });

  it("gives up after the retry budget and returns the last image", async () => {
    const capturePage = vi.fn(() => Promise.resolve(emptyImage));
    const sleep = vi.fn(() => Promise.resolve());

    const result = await captureNonEmptyPage({ capturePage }, { retries: 3, delayMs: 0, sleep });

    expect(result).toBe(emptyImage);
    expect(capturePage).toHaveBeenCalledTimes(4);
  });
});
