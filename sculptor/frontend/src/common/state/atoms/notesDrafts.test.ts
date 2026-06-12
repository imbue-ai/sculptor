import { createStore } from "jotai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { notesDraftAtomFamily } from "./notesDrafts";

// notesDraftAtomFamily is module-scoped, so atoms persist across tests. Using
// a per-test counter ensures each test gets a fresh atom with no retained
// in-memory state from prior tests.
let testWorkspaceCounter = 0;
const nextWorkspaceID = (): string => {
  testWorkspaceCounter += 1;
  return `test-ws-${testWorkspaceCounter}`;
};

const storageKey = (workspaceID: string): string => `sculptor-notes-draft-${workspaceID}`;

describe("notesDraftAtomFamily", () => {
  const registeredWorkspaceIDs: Array<string> = [];

  const registerWorkspaceID = (workspaceID: string): string => {
    registeredWorkspaceIDs.push(workspaceID);
    return workspaceID;
  };

  beforeEach(() => {
    localStorage.clear();
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    for (const workspaceID of registeredWorkspaceIDs) {
      notesDraftAtomFamily.remove(workspaceID);
    }
    registeredWorkspaceIDs.length = 0;
  });

  it("keeps per-workspace state independent", () => {
    const store = createStore();
    const workspaceA = registerWorkspaceID(nextWorkspaceID());
    const workspaceB = registerWorkspaceID(nextWorkspaceID());
    const atomA = notesDraftAtomFamily(workspaceA);
    const atomB = notesDraftAtomFamily(workspaceB);

    store.set(atomA, "notes for A");
    store.set(atomB, "notes for B");

    expect(store.get(atomA)).toBe("notes for A");
    expect(store.get(atomB)).toBe("notes for B");
  });

  it("returns an empty string when no value is persisted", () => {
    const store = createStore();
    const workspaceID = registerWorkspaceID(nextWorkspaceID());
    const draftAtom = notesDraftAtomFamily(workspaceID);

    expect(store.get(draftAtom)).toBe("");
  });

  it("updates in-memory state synchronously on set", () => {
    const store = createStore();
    const workspaceID = registerWorkspaceID(nextWorkspaceID());
    const draftAtom = notesDraftAtomFamily(workspaceID);

    store.set(draftAtom, "hello");

    expect(store.get(draftAtom)).toBe("hello");
  });

  it("debounces the localStorage write by 300ms", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const store = createStore();
    const workspaceID = registerWorkspaceID(nextWorkspaceID());
    const draftAtom = notesDraftAtomFamily(workspaceID);
    const key = storageKey(workspaceID);

    store.set(draftAtom, "hello");

    expect(localStorage.getItem(key)).toBeNull();

    vi.advanceTimersByTime(300);

    expect(localStorage.getItem(key)).toBe(JSON.stringify("hello"));
    const keyCalls = setItemSpy.mock.calls.filter(([callKey]) => callKey === key);
    expect(keyCalls).toHaveLength(1);
    expect(keyCalls[0][1]).toBe(JSON.stringify("hello"));

    setItemSpy.mockRestore();
  });

  it("coalesces rapid writes within the debounce window into one write", () => {
    const setItemSpy = vi.spyOn(Storage.prototype, "setItem");
    const store = createStore();
    const workspaceID = registerWorkspaceID(nextWorkspaceID());
    const draftAtom = notesDraftAtomFamily(workspaceID);
    const key = storageKey(workspaceID);

    store.set(draftAtom, "a");
    store.set(draftAtom, "ab");
    store.set(draftAtom, "abc");

    vi.advanceTimersByTime(300);

    const keyCalls = setItemSpy.mock.calls.filter(([callKey]) => callKey === key);
    expect(keyCalls).toHaveLength(1);
    expect(keyCalls[0][1]).toBe(JSON.stringify("abc"));

    setItemSpy.mockRestore();
  });

  it("returns the same atom instance for the same workspace ID", () => {
    const workspaceID = registerWorkspaceID(nextWorkspaceID());

    expect(notesDraftAtomFamily(workspaceID)).toBe(notesDraftAtomFamily(workspaceID));
  });

  it("reads a previously persisted value from localStorage in a new store", () => {
    const workspaceID = registerWorkspaceID(nextWorkspaceID());
    localStorage.setItem(storageKey(workspaceID), JSON.stringify("previously saved"));

    const store = createStore();
    const draftAtom = notesDraftAtomFamily(workspaceID);

    expect(store.get(draftAtom)).toBe("previously saved");
  });
});
