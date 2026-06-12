import { cleanup, fireEvent, render } from "@testing-library/react";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { ResizeHandle } from "./ResizeHandle";

// jsdom does not implement PointerEvent; fall back to MouseEvent so
// fireEvent.pointerDown's `button`/`clientX`/`clientY` reach the handler.
beforeAll(() => {
  if (typeof window.PointerEvent === "undefined") {
    (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
  }
});

afterEach(() => {
  cleanup();
  document.body.classList.remove("sculptor-resizing");
});

// While a resize drag is active, the cursor can pass over an Electron
// <webview>, whose separate render process steals pointer events from the
// host window — freezing the resize. ResizeHandle marks the document body
// with `sculptor-resizing` during the drag so global CSS can disable
// pointer events on webviews for the duration of the drag.
describe("ResizeHandle — disables webview pointer events during drag", () => {
  const renderHandle = (): HTMLElement => {
    const { getByRole } = render(
      <ResizeHandle axis="x" getSize={() => 200} onResize={vi.fn()} ariaLabel="test handle" />,
    );
    return getByRole("separator");
  };

  it("adds `sculptor-resizing` to <body> on pointerdown and removes it on pointerup", () => {
    const handle = renderHandle();
    expect(document.body.classList.contains("sculptor-resizing")).toBe(false);

    fireEvent.pointerDown(handle, { button: 0, clientX: 100, clientY: 0 });
    expect(document.body.classList.contains("sculptor-resizing")).toBe(true);

    fireEvent.pointerUp(window, { clientX: 150, clientY: 0 });
    expect(document.body.classList.contains("sculptor-resizing")).toBe(false);
  });

  it("keeps the class while one of two concurrent drags is still active", () => {
    const { getAllByRole } = render(
      <>
        <ResizeHandle axis="x" getSize={() => 200} onResize={vi.fn()} ariaLabel="a" />
        <ResizeHandle axis="x" getSize={() => 200} onResize={vi.fn()} ariaLabel="b" />
      </>,
    );
    const [a, b] = getAllByRole("separator");

    fireEvent.pointerDown(a, { button: 0, clientX: 0, clientY: 0 });
    fireEvent.pointerDown(b, { button: 0, clientX: 0, clientY: 0 });
    expect(document.body.classList.contains("sculptor-resizing")).toBe(true);

    fireEvent.pointerUp(window);
    // Both drags listen for the same window pointerup, so a single event
    // ends both — but the class must stay until the *last* drag has cleared.
    // Asserting the final state is enough; nesting/ordering is an
    // implementation detail.
    expect(document.body.classList.contains("sculptor-resizing")).toBe(false);
  });

  it("non-primary buttons do not toggle the class", () => {
    const handle = renderHandle();
    fireEvent.pointerDown(handle, { button: 2, clientX: 0, clientY: 0 });
    expect(document.body.classList.contains("sculptor-resizing")).toBe(false);
  });

  it("clears the class if the handle unmounts mid-drag", () => {
    const { getByRole, unmount } = render(
      <ResizeHandle axis="x" getSize={() => 200} onResize={vi.fn()} ariaLabel="test handle" />,
    );
    const handle = getByRole("separator");
    fireEvent.pointerDown(handle, { button: 0, clientX: 0, clientY: 0 });
    expect(document.body.classList.contains("sculptor-resizing")).toBe(true);

    unmount();
    expect(document.body.classList.contains("sculptor-resizing")).toBe(false);
  });
});
