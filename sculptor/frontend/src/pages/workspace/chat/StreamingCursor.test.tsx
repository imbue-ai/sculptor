import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ElementIds } from "~/api";

import { StreamingCursor } from "./StreamingCursor.tsx";

afterEach(cleanup);

describe("StreamingCursor", () => {
  it("renders a span element", () => {
    const { container } = render(<StreamingCursor />);
    const span = container.querySelector("span");
    expect(span).toBeTruthy();
  });

  it("applies the streamingCursor CSS class", () => {
    const { container } = render(<StreamingCursor />);
    const span = container.querySelector("span");
    expect(span).toBeTruthy();
    expect(span!.className).toContain("streamingCursor");
  });

  it("renders as an empty element (no text content)", () => {
    const { container } = render(<StreamingCursor />);
    const span = container.querySelector("span");
    expect(span).toBeTruthy();
    expect(span!.textContent).toBe("");
  });

  it("has the STREAMING_CURSOR data-testid", () => {
    render(<StreamingCursor />);
    expect(screen.getByTestId(ElementIds.STREAMING_CURSOR)).toBeTruthy();
  });
});
