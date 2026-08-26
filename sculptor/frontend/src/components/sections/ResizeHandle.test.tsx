import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import styles from "./ResizeHandle.module.scss";
import { ResizeHandle } from "./ResizeHandle.tsx";

afterEach(cleanup);

const noop = (): void => {};

describe("ResizeHandle accessibility", () => {
  it("exposes the current value and its bounds on the separator", () => {
    render(
      <ResizeHandle
        axis="x"
        getSize={() => 200}
        onResize={noop}
        ariaLabel="Resize left section"
        ariaValueNow={20}
        ariaValueMin={5}
        ariaValueMax={80}
      />,
    );

    const handle = screen.getByRole("separator", { name: "Resize left section" });
    expect(handle).toHaveAttribute("aria-valuenow", "20");
    expect(handle).toHaveAttribute("aria-valuemin", "5");
    expect(handle).toHaveAttribute("aria-valuemax", "80");
    // An x-axis handle is a vertical divider.
    expect(handle).toHaveAttribute("aria-orientation", "vertical");
  });

  it("omits the value attributes when the caller provides none", () => {
    render(<ResizeHandle axis="y" getSize={() => 0} onResize={noop} ariaLabel="Resize split" />);

    const handle = screen.getByRole("separator", { name: "Resize split" });
    expect(handle).not.toHaveAttribute("aria-valuenow");
    expect(handle).not.toHaveAttribute("aria-valuemin");
    expect(handle).not.toHaveAttribute("aria-valuemax");
  });
});

describe("ResizeHandle edge-overlay variant", () => {
  it("floats over the edge the controlled region grows toward", () => {
    render(
      <ResizeHandle
        axis="x"
        direction={1}
        variant="edge-overlay"
        getSize={() => 0}
        onResize={noop}
        ariaLabel="Resize sidebar"
      />,
    );

    // axis "x" + direction 1: dragging right grows the region, so the handle
    // overlays its right edge.
    expect(screen.getByRole("separator", { name: "Resize sidebar" })).toHaveClass(styles.edgeOverlayRight);
  });

  it("mirrors the overlaid edge when the grow direction flips", () => {
    render(
      <ResizeHandle
        axis="y"
        direction={-1}
        variant="edge-overlay"
        getSize={() => 0}
        onResize={noop}
        ariaLabel="Resize bottom"
      />,
    );

    expect(screen.getByRole("separator", { name: "Resize bottom" })).toHaveClass(styles.edgeOverlayTop);
  });

  it("stays a plain in-flow divider by default", () => {
    render(<ResizeHandle axis="x" getSize={() => 0} onResize={noop} ariaLabel="Resize left section" />);

    const handle = screen.getByRole("separator", { name: "Resize left section" });
    expect(handle).not.toHaveClass(styles.edgeOverlayRight);
    expect(handle).not.toHaveClass(styles.edgeOverlayLeft);
  });
});

describe("ResizeHandle keyboard resizing", () => {
  it("steps the size by 10% of the parent per arrow press", () => {
    const onResize = vi.fn();
    render(
      <div>
        <ResizeHandle axis="x" getSize={() => 100} onResize={onResize} ariaLabel="Resize left section" />
      </div>,
    );

    const handle = screen.getByRole("separator", { name: "Resize left section" });
    // jsdom reports zero-size rects; give the parent a concrete width so the
    // 10%-of-parent step is non-zero.
    vi.spyOn(handle.parentElement!, "getBoundingClientRect").mockReturnValue({ width: 200 } as DOMRect);

    fireEvent.keyDown(handle, { key: "ArrowRight" });
    expect(onResize).toHaveBeenCalledWith(120);

    fireEvent.keyDown(handle, { key: "ArrowLeft" });
    expect(onResize).toHaveBeenCalledWith(80);
  });
});
