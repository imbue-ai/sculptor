import { cleanup, render } from "@testing-library/react";
import type { ReactElement } from "react";
import { useCallback } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as Utils from "../common/Utils.ts";
import { Toast, ToastProvider } from "./Toast";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// A parent that renders something unrelated alongside a single, closed <Toast>
// whose props are referentially stable across re-renders. Re-rendering the
// parent with a changed `unrelated` prop changes nothing about the Toast — the
// exact situation that happens constantly in the real app (workspace switch,
// message send, etc.) while the always-mounted toasts sit closed.
const Harness = ({ unrelated }: { unrelated: number }): ReactElement => {
  // Stable callback so React.memo can actually bail out — mirrors the
  // production fix where call sites pass stable props.
  const onOpenChange = useCallback(() => {}, []);
  return (
    <ToastProvider>
      <span>{unrelated}</span>
      <Toast open={false} onOpenChange={onOpenChange} />
    </ToastProvider>
  );
};

describe("Toast", () => {
  // `mergeClasses` is called exactly once per Toast render (for the Root
  // className), and nothing else in this isolated tree calls it, so its call
  // count is a faithful proxy for "how many times did Toast render".
  it("does not re-render when an unrelated parent update commits", () => {
    const mergeSpy = vi.spyOn(Utils, "mergeClasses");

    const { rerender } = render(<Harness unrelated={0} />);

    // Sanity check: the spy is wired up and Toast rendered at least once.
    const callsAfterMount = mergeSpy.mock.calls.length;
    expect(callsAfterMount).toBeGreaterThanOrEqual(1);

    // Commit an unrelated parent update. The closed Toast's props are unchanged.
    rerender(<Harness unrelated={1} />);

    // A memoized Toast bails out, so its render function never runs again.
    expect(mergeSpy.mock.calls.length).toBe(callsAfterMount);
  });
});
