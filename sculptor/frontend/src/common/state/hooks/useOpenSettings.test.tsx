import { act, cleanup, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";

import { useOpenSettings } from "./useOpenSettings.ts";

const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
  <Provider store={createStore()}>
    <MemoryRouter>{children}</MemoryRouter>
  </Provider>
);

afterEach(() => {
  cleanup();
});

describe("useOpenSettings", () => {
  it("opens the Jujutsu page on one of its jj prompts", () => {
    const { result } = renderHook(() => ({ openSettings: useOpenSettings(), location: useLocation() }), { wrapper });

    act(() => {
      result.current.openSettings("JJ", "commit");
    });

    expect(`${result.current.location.pathname}${result.current.location.search}`).toBe(
      "/settings?section=JJ&focusPrompt=commit",
    );
  });
});
