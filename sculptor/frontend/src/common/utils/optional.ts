export const optional = <T>(condition: boolean, value: T): T | undefined => {
  return condition ? value : undefined;
};
