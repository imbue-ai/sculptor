import type { Virtualizer } from "@tanstack/react-virtual";
import { describe, expect, it } from "vitest";

import {
  bottomPinOffset,
  contentBottomOffset,
  distanceFromContentBottom,
  IDLE_TAIL_PADDING,
  maxScrollOffset,
  PIN_BOTTOM_GAP,
  STREAMING_TAIL_PADDING,
  TURN_END_SHRINK_SLACK,
} from "../geometry.ts";

const container = (scrollTop: number, scrollHeight: number, clientHeight: number): HTMLElement =>
  ({ scrollTop, scrollHeight, clientHeight }) as HTMLElement;

const virtualizerWithPadding = (paddingEnd: number): Virtualizer<HTMLDivElement, Element> =>
  ({ options: { paddingEnd } }) as Virtualizer<HTMLDivElement, Element>;

describe("geometry", () => {
  it("keeps the streaming paddingEnd floor large enough for the pin gap plus the shrink slack", () => {
    expect(STREAMING_TAIL_PADDING).toBe(PIN_BOTTOM_GAP + TURN_END_SHRINK_SLACK);
  });

  it("ends the idle scroll range at the pin position (over-scroll reveals exactly the gap)", () => {
    expect(IDLE_TAIL_PADDING).toBe(PIN_BOTTOM_GAP);
  });

  it("measures the signed distance to the content bottom", () => {
    const el = container(1000, 2000, 500);
    // Content bottom at 2000 - 400 = 1600; viewport bottom at 1500.
    expect(distanceFromContentBottom(el, virtualizerWithPadding(400))).toBe(100);
    // Scrolled 100px past the content bottom, into the padding.
    el.scrollTop = 1200;
    expect(distanceFromContentBottom(el, virtualizerWithPadding(400))).toBe(-100);
  });

  it("pins the content bottom a PIN_BOTTOM_GAP above the viewport bottom", () => {
    const el = container(0, 2000, 500);
    expect(contentBottomOffset(el, virtualizerWithPadding(400))).toBe(1100);
    expect(bottomPinOffset(el, virtualizerWithPadding(400))).toBe(1100 + PIN_BOTTOM_GAP);
  });

  it("clamps the pin target to the scroll range while paddingEnd has not converged", () => {
    const el = container(0, 2000, 500);
    // paddingEnd smaller than the gap: the gap cannot fit, so the pin lands at
    // the end of the range instead of past it.
    expect(bottomPinOffset(el, virtualizerWithPadding(PIN_BOTTOM_GAP / 2))).toBe(maxScrollOffset(el));
  });

  it("never yields a negative offset for content shorter than the viewport", () => {
    const el = container(0, 300, 500);
    expect(contentBottomOffset(el, virtualizerWithPadding(100))).toBe(0);
    expect(bottomPinOffset(el, virtualizerWithPadding(100))).toBe(0);
    expect(maxScrollOffset(el)).toBe(0);
  });

  it("does not pin into the padding while the content still fits the viewport", () => {
    // Content ends at 550 - 128 = 422 < clientHeight 500, but the padding makes
    // the range scrollable (maxScrollOffset 50). The pin must stay at 0 rather
    // than scroll the top of the chat out of view to show empty space.
    const el = container(0, 550, 500);
    expect(maxScrollOffset(el)).toBe(50);
    expect(bottomPinOffset(el, virtualizerWithPadding(128))).toBe(0);
  });
});
