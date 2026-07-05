import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SCROLL_PHASE_ATTR } from "../scrollStateMachine.ts";
import { useScrollStateMachine } from "../useScrollStateMachine.ts";

describe("useScrollStateMachine", () => {
  it("attaches to the container and reflects the phase on the DOM", () => {
    const el = document.createElement("div");
    const ref = { current: el };

    const { result } = renderHook(() => useScrollStateMachine(ref));

    expect(el.getAttribute(SCROLL_PHASE_ATTR)).toBe("userControlled");

    act(() => result.current.dispatch({ kind: "agentSwitched", agentId: "t1" }));
    expect(el.getAttribute(SCROLL_PHASE_ATTR)).toBe("restoring");
  });

  it("dispatches userScrolled on a wheel event, preempting a programmatic phase", () => {
    const el = document.createElement("div");
    const ref = { current: el };

    const { result } = renderHook(() => useScrollStateMachine(ref));
    act(() => result.current.dispatch({ kind: "agentSwitched", agentId: "t1" }));
    expect(result.current.getState().authority.kind).toBe("restoring");

    act(() => {
      el.dispatchEvent(new Event("wheel"));
    });
    expect(result.current.getState().authority.kind).toBe("userControlled");
  });

  it("detaches on unmount without throwing", () => {
    const el = document.createElement("div");
    const ref = { current: el };
    const { unmount } = renderHook(() => useScrollStateMachine(ref));
    expect(() => unmount()).not.toThrow();
  });
});
