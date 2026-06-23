export type DiffStats = {
  additions: number;
  deletions: number;
  filesChanged: number;
};

export const parseDiffStats = (diffText: string | null | undefined): DiffStats => {
  if (!diffText) {
    return { additions: 0, deletions: 0, filesChanged: 0 };
  }

  const lines = diffText.split("\n");
  let additions = 0;
  let deletions = 0;
  let filesChanged = 0;

  for (const line of lines) {
    if (line.startsWith("diff --git")) {
      filesChanged++;
    } else if (line.startsWith("+") && !line.startsWith("+++")) {
      additions++;
    } else if (line.startsWith("-") && !line.startsWith("---")) {
      deletions++;
    }
  }

  return { additions, deletions, filesChanged };
};
