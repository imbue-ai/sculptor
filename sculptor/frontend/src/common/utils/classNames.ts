export const mergeClasses = (...classes: ReadonlyArray<string | undefined>): string => {
  return classes.filter((c) => c).join(" ");
};
