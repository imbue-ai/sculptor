import { renderHook } from "@testing-library/react";
import { createStore, Provider } from "jotai";
import type { ReactElement, ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  type CommandActionCallback,
  type CommandActionId,
  commandActionsAtom,
  useRegisterCommandAction,
} from "../commandActions.ts";

type Store = ReturnType<typeof createStore>;

const makeStore = (): Store => createStore();

const wrapperFor =
  (store: Store) =>
  ({ children }: { children: ReactNode }): ReactElement => <Provider store={store}>{children}</Provider>;

/**
 * Read the registered callback for `id` directly off the atom. Mirrors what
 * the palette runtime does in `CommandRegistrations.tsx` (`commandActions[id]?.()`).
 */
const getRegistered = (store: Store, id: CommandActionId): CommandActionCallback | undefined =>
  store.get(commandActionsAtom)[id];

/**
 * Mirror of how `CommandRegistrations.tsx` invokes a registered action.
 * Silent no-op when nothing is registered.
 */
const invokeAction = (store: Store, id: CommandActionId): void => {
  store.get(commandActionsAtom)[id]?.();
};

const renderRegister = (
  store: Store,
  id: CommandActionId,
  callback: CommandActionCallback,
): ReturnType<typeof renderHook<void, { id: CommandActionId; callback: CommandActionCallback }>> =>
  renderHook(({ id: hookId, callback: hookCb }) => useRegisterCommandAction(hookId, hookCb), {
    wrapper: wrapperFor(store),
    initialProps: { id, callback },
  });

afterEach(() => {
  vi.restoreAllMocks();
});

describe("commandActions", () => {
  describe("useRegisterCommandAction", () => {
    it("registers a callback on mount and clears it on unmount", () => {
      const store = makeStore();
      const cb = vi.fn();

      const { unmount } = renderRegister(store, "agent.previous", cb);

      // Registered: invoking via the runtime path calls cb.
      const registered = getRegistered(store, "agent.previous");
      expect(registered).toBeDefined();
      registered!();
      expect(cb).toHaveBeenCalledTimes(1);

      unmount();

      // Unregistered: the slot is gone.
      expect(getRegistered(store, "agent.previous")).toBeUndefined();
    });

    it("survives a fast unmount/remount with the same callback ref (same-ref safety)", () => {
      const store = makeStore();
      const cb = vi.fn();

      const first = renderRegister(store, "agent.previous", cb);
      expect(getRegistered(store, "agent.previous")).toBeDefined();
      first.unmount();
      expect(getRegistered(store, "agent.previous")).toBeUndefined();

      // Remount with the same callback ref. The new effect should register
      // the slot afresh, and there should be no leftover from the prior cycle.
      const second = renderRegister(store, "agent.previous", cb);
      const registered = getRegistered(store, "agent.previous");
      expect(registered).toBeDefined();
      registered!();
      expect(cb).toHaveBeenCalledTimes(1);
      second.unmount();
    });

    it("does not double-fire when re-mounted: each mount registers a single slot", () => {
      // Regression-lock for the "latest registration wins" guarantee. After
      // a remount, invoking the action calls the underlying callback exactly
      // once (not once per historical mount).
      const store = makeStore();
      const cb = vi.fn();

      const first = renderRegister(store, "agent.previous", cb);
      first.unmount();
      const second = renderRegister(store, "agent.previous", cb);

      invokeAction(store, "agent.previous");
      expect(cb).toHaveBeenCalledTimes(1);
      second.unmount();
    });

    it("registers multiple action ids in parallel without interfering", () => {
      const store = makeStore();
      const top = vi.fn();
      const bottom = vi.fn();
      const closeWs = vi.fn();

      const a = renderRegister(store, "agent.previous", top);
      const b = renderRegister(store, "chat.jumpToBottom", bottom);
      const c = renderRegister(store, "workspace.closeCurrent", closeWs);

      expect(getRegistered(store, "agent.previous")).toBeDefined();
      expect(getRegistered(store, "chat.jumpToBottom")).toBeDefined();
      expect(getRegistered(store, "workspace.closeCurrent")).toBeDefined();

      // Unmount one consumer; the other two should remain registered.
      b.unmount();
      expect(getRegistered(store, "agent.previous")).toBeDefined();
      expect(getRegistered(store, "chat.jumpToBottom")).toBeUndefined();
      expect(getRegistered(store, "workspace.closeCurrent")).toBeDefined();

      // The surviving registrations still dispatch to the right callback.
      invokeAction(store, "agent.previous");
      invokeAction(store, "workspace.closeCurrent");
      expect(top).toHaveBeenCalledTimes(1);
      expect(closeWs).toHaveBeenCalledTimes(1);
      expect(bottom).not.toHaveBeenCalled();

      a.unmount();
      c.unmount();
    });

    it("invokes the latest closure even when the callback prop changes between renders", () => {
      // The hook captures the callback in a ref so it always reads the most
      // recent prop without re-running the registration effect. This protects
      // against stale closures over component state.
      const store = makeStore();
      const cb1 = vi.fn();
      const cb2 = vi.fn();

      const { rerender } = renderRegister(store, "agent.previous", cb1);
      rerender({ id: "agent.previous", callback: cb2 });

      invokeAction(store, "agent.previous");
      expect(cb1).not.toHaveBeenCalled();
      expect(cb2).toHaveBeenCalledTimes(1);
    });

    it("when two consumers mount under the same id, the latest registration wins", () => {
      // Two simultaneous registrants is the documented "chat panel mounts in
      // two routes during navigation" case. The cleanup of the older mount
      // must NOT clobber the newer registration, thanks to the same-ref
      // identity check on the stored stable wrapper.
      const store = makeStore();
      const cb1 = vi.fn();
      const cb2 = vi.fn();

      const first = renderRegister(store, "agent.previous", cb1);
      const second = renderRegister(store, "agent.previous", cb2);

      // The latest registration wins.
      invokeAction(store, "agent.previous");
      expect(cb1).not.toHaveBeenCalled();
      expect(cb2).toHaveBeenCalledTimes(1);

      // Unmounting the older consumer must NOT clear the newer entry.
      first.unmount();
      const stillRegistered = getRegistered(store, "agent.previous");
      expect(stillRegistered).toBeDefined();
      stillRegistered!();
      expect(cb2).toHaveBeenCalledTimes(2);

      // Unmounting the newer consumer clears the slot entirely.
      second.unmount();
      expect(getRegistered(store, "agent.previous")).toBeUndefined();
    });
  });

  describe("invocation when nothing is registered", () => {
    it("is a silent no-op (no throw, no console error)", () => {
      const store = makeStore();
      const errSpy = vi.spyOn(console, "error").mockImplementation(() => {});
      const warnSpy = vi.spyOn(console, "warn").mockImplementation(() => {});

      // Sanity: nothing is registered.
      expect(store.get(commandActionsAtom)).toEqual({});

      // The runtime style: optional chaining means an unregistered slot is a
      // silent no-op. This regression-locks that behavior so a future
      // implementation change (e.g. throwing or warning) is intentional.
      expect(() => invokeAction(store, "agent.previous")).not.toThrow();

      expect(errSpy).not.toHaveBeenCalled();
      expect(warnSpy).not.toHaveBeenCalled();
    });
  });
});
