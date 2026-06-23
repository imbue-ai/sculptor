const TERMINAL_LABEL_PATTERN = /^Terminal (\d+)$/;

export const getNextTerminalLabel = (tabs: ReadonlyArray<{ label: string }>): string => {
  const usedNumbers = new Set<number>(
    tabs
      .map((tab): number | undefined => {
        const match = tab.label.match(TERMINAL_LABEL_PATTERN);
        return match ? parseInt(match[1], 10) : undefined;
      })
      .filter((value): value is number => value !== undefined),
  );
  let n = 1;
  while (usedNumbers.has(n)) n++;
  return `Terminal ${n}`;
};
