import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { atomWithDebouncedStorage } from "./atomWithDebouncedStorage";

describe("atomWithDebouncedStorage", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("uses initialValue when localStorage is empty", () => {
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", "default");

    expect(store.get(testAtom)).toBe("default");
  });

  it("reads initial value from localStorage", () => {
    localStorage.setItem("test-key", JSON.stringify("persisted"));
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", "default");

    expect(store.get(testAtom)).toBe("persisted");
  });

  it("updates in-memory state immediately", () => {
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", "initial");

    store.set(testAtom, "updated");

    expect(store.get(testAtom)).toBe("updated");
  });

  it("debounces localStorage writes", () => {
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", "initial", 100);

    store.set(testAtom, "updated");

    expect(localStorage.getItem("test-key")).toBeNull();

    vi.advanceTimersByTime(100);

    expect(localStorage.getItem("test-key")).toBe(JSON.stringify("updated"));
  });

  it("coalesces rapid writes into a single localStorage write", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", 0, 100);

    store.set(testAtom, 1);
    store.set(testAtom, 2);
    store.set(testAtom, 3);

    vi.advanceTimersByTime(100);

    const calls = spy.mock.calls.filter(([key]) => key === "test-key");
    expect(calls).toHaveLength(1);
    expect(calls[0][1]).toBe(JSON.stringify(3));

    spy.mockRestore();
  });

  it("supports functional updates", () => {
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", 0, 100);

    store.set(testAtom, (prev) => prev + 1);
    store.set(testAtom, (prev) => prev + 10);

    expect(store.get(testAtom)).toBe(11);

    vi.advanceTimersByTime(100);

    expect(localStorage.getItem("test-key")).toBe(JSON.stringify(11));
  });

  it("supports object values with functional updates", () => {
    const store = createStore();
    const testAtom = atomWithDebouncedStorage<Record<string, number>>("test-key", {}, 100);

    store.set(testAtom, (prev) => ({ ...prev, a: 1 }));
    store.set(testAtom, (prev) => ({ ...prev, b: 2 }));

    expect(store.get(testAtom)).toEqual({ a: 1, b: 2 });

    vi.advanceTimersByTime(100);

    expect(JSON.parse(localStorage.getItem("test-key")!)).toEqual({ a: 1, b: 2 });
  });

  it("falls back to initialValue when localStorage contains invalid JSON", () => {
    localStorage.setItem("test-key", "not-valid-json{{{");
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("test-key", "fallback");

    expect(store.get(testAtom)).toBe("fallback");
  });
});

describe("atomWithDebouncedStorage beforeunload flush", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("flushes pending writes on beforeunload", () => {
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("flush-key", "initial", 5000);

    store.set(testAtom, "pending-value");

    expect(localStorage.getItem("flush-key")).toBeNull();

    window.dispatchEvent(new Event("beforeunload"));

    expect(localStorage.getItem("flush-key")).toBe(JSON.stringify("pending-value"));
  });

  it("does not double-write after flush when timer fires", () => {
    const spy = vi.spyOn(Storage.prototype, "setItem");
    const store = createStore();
    const testAtom = atomWithDebouncedStorage("flush-key", "initial", 100);

    store.set(testAtom, "value");
    window.dispatchEvent(new Event("beforeunload"));

    const callsAfterFlush = spy.mock.calls.filter(([key]) => key === "flush-key").length;

    vi.advanceTimersByTime(200);

    const callsAfterTimer = spy.mock.calls.filter(([key]) => key === "flush-key").length;
    expect(callsAfterTimer).toBe(callsAfterFlush);

    spy.mockRestore();
  });
});
