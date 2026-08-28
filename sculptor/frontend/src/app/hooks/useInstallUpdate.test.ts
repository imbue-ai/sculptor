import { act, renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { createElement } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { isInstallingUpdateAtom } from "~/common/state/atoms/autoUpdate.ts";

import { useInstallUpdate } from "./useInstallUpdate";

vi.mock("posthog-js", () => ({ posthog: { capture: vi.fn() } }));

const flushMicrotasks = async (): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, 0));
};

const savedSculptor = window.sculptor;

beforeEach(() => {
  vi.clearAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
  window.sculptor = savedSculptor;
});

describe("useInstallUpdate", () => {
  it("clears isInstalling when the installUpdate IPC promise rejects", async () => {
    // Regression: a rejected installUpdate() used to be unhandled, leaving
    // isInstalling stuck true forever and disabling the install button.
    const mockInstallUpdate = vi.fn().mockRejectedValue(new Error("install failed"));
    window.sculptor = { installUpdate: mockInstallUpdate } as unknown as typeof window.sculptor;
    vi.spyOn(console, "error").mockImplementation(() => {});

    const store = createStore();
    const wrapper = ({ children }: { children: ReactNode }): ReactElement =>
      createElement(Provider, { store }, children);

    const { result } = renderHook(() => useInstallUpdate(), { wrapper });

    expect(result.current.isInstalling).toBe(false);

    await act(async () => {
      result.current.install();
      await flushMicrotasks();
    });

    expect(mockInstallUpdate).toHaveBeenCalledTimes(1);
    // The fix's .catch must reset the flag; the old code left it stuck true.
    expect(result.current.isInstalling).toBe(false);
    expect(store.get(isInstallingUpdateAtom)).toBe(false);
  });
});
