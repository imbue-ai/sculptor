const TERMINAL_LABEL_PATTERN = /^Terminal (\d+)$/;

export const getNextTerminalLabel = (tabs: ReadonlyArray<{ label: string }>): string => {
  const usedNumbers = new Set(
    tabs
      .map((t) => {
        const match = t.label.match(TERMINAL_LABEL_PATTERN);
        return match ? parseInt(match[1], 10) : null;
      })
      .filter((n): n is number => n !== null),
  );
  let n = 1;
  while (usedNumbers.has(n)) n++;
  return `Terminal ${n}`;
};
