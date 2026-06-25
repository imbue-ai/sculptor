// Shared helpers for the section/panel atoms. Both helpers exist so the narrow
// per-key read slices stay reference-stable: memoizedAtomByKey reuses the same
// derived atom instance per key (a fresh derived atom per render causes Jotai
// re-render loops), and shallowArrayEqual is the selectAtom equalityFn that
// suppresses re-emits when an array slice is element-wise unchanged.

import type { Atom } from "jotai";

export function memoizedAtomByKey<TKey extends string, TValue>(
  factory: (key: TKey) => Atom<TValue>,
): (key: TKey) => Atom<TValue> {
  const cache = new Map<string, Atom<TValue>>();
  return (key) => {
    let cached = cache.get(key);
    if (cached === undefined) {
      cached = factory(key);
      cache.set(key, cached);
    }
    return cached;
  };
}

export function shallowArrayEqual<T>(a: ReadonlyArray<T>, b: ReadonlyArray<T>): boolean {
  if (a === b) {
    return true;
  }

  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
}
