// Element-wise array equality, used as the selectAtom equalityFn for the array
// slices in the section atoms: it suppresses re-emits when a rebuilt slice is
// element-wise unchanged, keeping subscribers reference-stable.
export const shallowArrayEqual = <T>(a: ReadonlyArray<T>, b: ReadonlyArray<T>): boolean => {
  if (a === b) {
    return true;
  }

  if (a.length !== b.length) {
    return false;
  }
  return a.every((value, index) => value === b[index]);
};
