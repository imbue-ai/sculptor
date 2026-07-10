import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { StateIcon } from "./StateIcon.tsx";

afterEach(() => cleanup());

describe("StateIcon", () => {
  it("draws the X glyph for Linear's 'canceled' state (spelled with one l), not the fallback ring", () => {
    // Regression guard: Linear's terminal state type is "canceled"; a "cancelled"
    // case would never match and fall through to the neutral ring.
    const { container } = render(<StateIcon type="canceled" color="#abc" />);
    expect(container.querySelector('path[d="M9 9l6 6M15 9l-6 6"]')).not.toBeNull();
  });

  it("draws the checkmark glyph for 'completed'", () => {
    const { container } = render(<StateIcon type="completed" color="#abc" />);
    expect(container.querySelector("path")).not.toBeNull();
  });

  it("falls back to a plain ring (no glyph path) for an unknown type", () => {
    const { container } = render(<StateIcon type="something-else" color="#abc" />);
    expect(container.querySelector("path")).toBeNull();
    expect(container.querySelector("circle")).not.toBeNull();
  });
});
