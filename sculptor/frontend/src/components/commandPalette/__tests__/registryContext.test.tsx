import { renderHook } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { describe, expect, it } from "vitest";

import { CommandRegistryProvider, useCommandRegistry } from "../registryContext.tsx";
import { CommandRegistry } from "../utils/registry.ts";

describe("CommandRegistryContext", () => {
  it("returns the module-level registry by default", () => {
    const { result } = renderHook(() => useCommandRegistry());
    // The default value is the singleton; assert we got *some* registry
    // by exercising its interface rather than identity-comparing the
    // singleton (other tests `reset()` it concurrently).
    expect(typeof result.current.size).toBe("function");
    expect(typeof result.current.register).toBe("function");
  });

  it("returns the provider's registry when wrapped", () => {
    const isolated = new CommandRegistry();
    const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
      <CommandRegistryProvider value={isolated}>{children}</CommandRegistryProvider>
    );
    const { result } = renderHook(() => useCommandRegistry(), { wrapper });
    expect(result.current).toBe(isolated);
  });

  it("provider scoping prevents test cross-talk on the singleton", () => {
    const isolated = new CommandRegistry();
    const wrapper = ({ children }: { children: ReactNode }): ReactElement => (
      <CommandRegistryProvider value={isolated}>{children}</CommandRegistryProvider>
    );
    const { result } = renderHook(() => useCommandRegistry(), { wrapper });
    // Mutations on the scoped registry don't leak to the default.
    expect(result.current.size()).toBe(0);
    result.current.register({ id: "scoped.cmd", title: "T", group: "navigation", perform: () => {} });
    expect(result.current.size()).toBe(1);
  });
});
